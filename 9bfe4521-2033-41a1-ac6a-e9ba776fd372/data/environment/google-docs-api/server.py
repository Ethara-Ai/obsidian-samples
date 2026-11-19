"""FastAPI server wrapping google_docs_data as REST endpoints.

Mirrors the Google Docs API v1 (docs.googleapis.com/v1) for the three
operations the connector needs: get a document, create a document, and
batchUpdate with insertText, replaceAllText, deleteContentRange,
updateParagraphStyle, updateTextStyle, createParagraphBullets,
deleteParagraphBullets and insertTable. Every operation needs a bearer
token from POST /oauth/token, and each one checks its own scope, so a connected
account is not by itself permission to edit. Errors use Google's own envelope,
including request validation failures and query parameters the method does not
take, which Google refuses rather than ignores.
"""

import json
import re
from typing import Any, List, Literal, Optional

from fastapi import Depends, FastAPI, Query, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

import google_docs_data
import _linked_peer
try:
    from tracking_middleware import install_tracker
    from admin_plane import install_admin_plane
except ModuleNotFoundError as _shared_plane_err:  # standalone run without the shared module on sys.path
    import logging as _logging
    _logging.error("SHARED PLANE MISSING - audit + admin disabled: %s", _shared_plane_err)
    def install_tracker(app):  # no-op fallback: audit endpoints disabled
        return None

    def install_admin_plane(app, store=None, one_shot_registry=None):
        return None

V = "/v1"
auth = google_docs_data.auth
GoogleError = google_docs_data.GoogleError

app = FastAPI(title="Google Docs API (Mock)", version="v1")
install_tracker(app)
install_admin_plane(app, store=google_docs_data._store)
# Drive reads and changes this mock's files live, through the peer routes (_linked_peer.py).
_linked_peer.install(app, "google-docs-api", google_docs_data)
auth.install(app)

SHARED_PLANES = ("/admin", "/audit")
ENUM_TYPES = {"suggestionsViewMode": "SuggestionsViewMode"}
SCALAR_TYPES = (("int", "TYPE_INT32"), ("bool", "TYPE_BOOL"), ("string", "TYPE_STRING"), ("float", "TYPE_DOUBLE"))
# Real batchUpdate request kinds this service does not implement: named, so the
# refusal says so instead of calling a genuine Docs request an unknown field.
UNSUPPORTED_REQUESTS = {
    "insertInlineImage", "insertTableRow", "insertTableColumn",
    "deleteTableRow", "deleteTableColumn", "insertPageBreak", "deletePositionedObject", "updateTableColumnProperties",
    "updateTableCellStyle", "updateTableRowStyle", "replaceImage", "updateDocumentStyle", "mergeTableCells",
    "unmergeTableCells", "createHeader", "createFooter", "createFootnote", "replaceNamedRangeContent",
    "updateSectionStyle", "insertSectionBreak", "deleteHeader", "deleteFooter", "pinTableHeaderRows",
    "createNamedRange", "deleteNamedRange", "insertPerson", "updateDocumentTabProperties", "addDocumentTab",
    "deleteTab", "insertDate",
}
SUPPORTED_REQUESTS = ", ".join(google_docs_data.REQUESTS)
OUTPUT_ONLY_DOCUMENT_FIELDS = {
    "documentId", "body", "headers", "footers", "footnotes", "documentStyle", "suggestedDocumentStyleChanges",
    "namedStyles", "suggestedNamedStylesChanges", "lists", "namedRanges", "revisionId", "suggestionsViewMode",
    "inlineObjects", "positionedObjects", "tabs",
}


class GoogleApiError(Exception):
    def __init__(self, error: GoogleError):
        super().__init__(error.body["error"]["message"])
        self.error = error


def _render(error: GoogleError) -> JSONResponse:
    return JSONResponse(status_code=error.status, content=error.body)


def _google_path(parts) -> str:
    out = ""
    for part in parts:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += ("." if out else "") + re.sub(r"(?<!^)(?=[A-Z])", "_", str(part)).lower()
    return out


def _validation_error(exc: RequestValidationError) -> GoogleError:
    err = exc.errors()[0]
    loc = list(err.get("loc") or [])
    where, parts = (loc[0], loc[1:]) if loc else ("body", [])
    kind, value = err.get("type", ""), err.get("input")
    if kind == "json_invalid":
        return GoogleError(400, "Invalid JSON payload received. Unexpected token.", field="")
    if kind == "extra_forbidden" and parts:
        name, parent = str(parts[-1]), parts[:-1]
        if len(parent) == 2 and parent[0] == "requests" and name in UNSUPPORTED_REQUESTS:
            return GoogleError(400, f"Invalid requests[{parent[1]}]: {name} is not supported by this service. "
                                    f"Supported requests: {SUPPORTED_REQUESTS}.", field=f"requests[{parent[1]}]")
        if not parent and name in OUTPUT_ONLY_DOCUMENT_FIELDS:
            return GoogleError(400, f"documents.create takes only title; '{name}' is output only. Create the "
                                    "document, then add content with documents.batchUpdate.", field=name)
        path = _google_path(parent)
        message = (f'Invalid JSON payload received. Unknown name "{name}"'
                   + (f" at '{path}'" if path else "") + ": Cannot find field.")
        return GoogleError(400, message, field=path)
    path = _google_path(parts)
    shown = json.dumps(value, default=str)
    if where == "query" and parts and parts[0] in ENUM_TYPES:
        return GoogleError(400, f"Invalid value at '{path}' (type.googleapis.com/google.apps.docs.v1."
                                f"{ENUM_TYPES[parts[0]]}), {shown}", field=path)
    scalar = next((name for prefix, name in SCALAR_TYPES if kind.startswith(prefix)), None)
    if scalar:
        return GoogleError(400, f"Invalid value at '{path}' ({scalar}), {shown}", field=path)
    return GoogleError(400, f"Invalid value at '{path}', {shown}", field=path)


@app.exception_handler(GoogleApiError)
async def _google_api_error(_request: Request, exc: GoogleApiError):
    return _render(exc.error)


@app.exception_handler(RequestValidationError)
async def _invalid_request(request: Request, exc: RequestValidationError):
    if request.url.path.startswith(SHARED_PLANES):
        return await request_validation_exception_handler(request, exc)
    return _render(_validation_error(exc))


@app.exception_handler(StarletteHTTPException)
async def _http_error(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith(SHARED_PLANES) or exc.status_code not in (404, 405):
        return await http_exception_handler(request, exc)
    return _render(GoogleError(404, "Requested entity was not found."))


def known_query(request: Request):
    """Refuse a query parameter the method does not declare, as Google does, instead of ignoring it."""
    route = request.scope.get("route")
    allowed = {p.alias for p in route.dependant.query_params} if route is not None else set()
    for name in request.query_params.keys():
        if name not in allowed:
            message = (f'Invalid JSON payload received. Unknown name "{name}": Cannot bind query parameter. '
                       f"Field '{name}' could not be found in request message.")
            raise GoogleApiError(GoogleError(400, message, field=""))


STRICT = Depends(known_query)


@app.get("/health")
def health():
    return {"status": "ok"}


def _reply(result, fields=None):
    if isinstance(result, GoogleError):
        return _render(result)
    return google_docs_data.apply_fields(result, fields)


def _mask(fields: Optional[str]):
    tree = google_docs_data.parse_fields(fields)
    if isinstance(tree, GoogleError):
        raise GoogleApiError(tree)
    return tree


def _account(request: Request) -> str:
    return request.state.oauth["account_id"]


# --- documents.get --------------------------------------------------------------------------

@app.get(V + "/documents/{documentId}", dependencies=[auth.require("documents.readonly", implied_by=("documents",)), STRICT])
def get_document(
    documentId: str,
    request: Request,
    includeTabsContent: bool = False,
    suggestionsViewMode: Literal["DEFAULT_FOR_CURRENT_ACCESS", "SUGGESTIONS_INLINE",
                                 "PREVIEW_SUGGESTIONS_ACCEPTED", "PREVIEW_WITHOUT_SUGGESTIONS"] = Query(
        "DEFAULT_FOR_CURRENT_ACCESS"),
    fields: Optional[str] = None,
):
    tree = _mask(fields)
    return _reply(google_docs_data.get_document(documentId, _account(request), include_tabs=includeTabsContent,
                                                view_mode=suggestionsViewMode), tree)


# --- documents.create -----------------------------------------------------------------------

class CreateDocumentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = None


@app.post(V + "/documents", dependencies=[auth.require("documents"), STRICT])
def create_document(request: Request, body: Optional[CreateDocumentBody] = None, fields: Optional[str] = None):
    tree = _mask(fields)
    return _reply(google_docs_data.create_document(_account(request), title=body.title if body else None), tree)


# --- documents.batchUpdate ------------------------------------------------------------------

class Location(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: Optional[int] = None
    segmentId: Optional[str] = None
    tabId: Optional[str] = None


class EndOfSegmentLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segmentId: Optional[str] = None
    tabId: Optional[str] = None


class InsertTextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: Optional[str] = None
    location: Optional[Location] = None
    endOfSegmentLocation: Optional[EndOfSegmentLocation] = None


class SubstringMatchCriteria(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: Optional[str] = None
    matchCase: Optional[bool] = None


class TabsCriteria(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tabIds: Optional[List[str]] = None


class ReplaceAllTextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    containsText: Optional[SubstringMatchCriteria] = None
    replaceText: Optional[str] = None
    tabsCriteria: Optional[TabsCriteria] = None


class Range(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segmentId: Optional[str] = None
    startIndex: Optional[int] = None
    endIndex: Optional[int] = None
    tabId: Optional[str] = None


class DeleteContentRangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    range: Optional[Range] = None


# Every field of Google's ParagraphStyle and TextStyle is accepted; the ones this service does not
# apply are refused by the data module only when the request's fields mask selects them, since Google
# updates only the fields the mask names.
class ParagraphStyle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    namedStyleType: Optional[Literal[google_docs_data.NAMED_STYLE_TYPES]] = None
    alignment: Optional[Literal[google_docs_data.ALIGNMENTS]] = None
    headingId: Optional[Any] = None
    lineSpacing: Optional[Any] = None
    direction: Optional[Any] = None
    spacingMode: Optional[Any] = None
    spaceAbove: Optional[Any] = None
    spaceBelow: Optional[Any] = None
    borderBetween: Optional[Any] = None
    borderTop: Optional[Any] = None
    borderBottom: Optional[Any] = None
    borderLeft: Optional[Any] = None
    borderRight: Optional[Any] = None
    indentFirstLine: Optional[Any] = None
    indentStart: Optional[Any] = None
    indentEnd: Optional[Any] = None
    tabStops: Optional[Any] = None
    keepLinesTogether: Optional[Any] = None
    keepWithNext: Optional[Any] = None
    avoidWidowAndOrphan: Optional[Any] = None
    shading: Optional[Any] = None
    pageBreakBefore: Optional[Any] = None


class TextStyle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bold: Optional[bool] = None
    italic: Optional[bool] = None
    underline: Optional[bool] = None
    strikethrough: Optional[bool] = None
    smallCaps: Optional[Any] = None
    backgroundColor: Optional[Any] = None
    foregroundColor: Optional[Any] = None
    fontSize: Optional[Any] = None
    weightedFontFamily: Optional[Any] = None
    baselineOffset: Optional[Any] = None
    link: Optional[Any] = None


class UpdateParagraphStyleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    range: Optional[Range] = None
    paragraphStyle: Optional[ParagraphStyle] = None
    fields: Optional[str] = None


class UpdateTextStyleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    range: Optional[Range] = None
    textStyle: Optional[TextStyle] = None
    fields: Optional[str] = None


class CreateParagraphBulletsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    range: Optional[Range] = None
    bulletPreset: Optional[Literal[google_docs_data.BULLET_PRESETS]] = None


class DeleteParagraphBulletsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    range: Optional[Range] = None


class InsertTableRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: Optional[int] = None
    columns: Optional[int] = None
    location: Optional[Location] = None
    endOfSegmentLocation: Optional[EndOfSegmentLocation] = None


class DocumentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    insertText: Optional[InsertTextRequest] = None
    replaceAllText: Optional[ReplaceAllTextRequest] = None
    deleteContentRange: Optional[DeleteContentRangeRequest] = None
    updateParagraphStyle: Optional[UpdateParagraphStyleRequest] = None
    updateTextStyle: Optional[UpdateTextStyleRequest] = None
    createParagraphBullets: Optional[CreateParagraphBulletsRequest] = None
    deleteParagraphBullets: Optional[DeleteParagraphBulletsRequest] = None
    insertTable: Optional[InsertTableRequest] = None


class WriteControl(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requiredRevisionId: Optional[str] = None
    targetRevisionId: Optional[str] = None


class BatchUpdateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requests: Optional[List[DocumentRequest]] = None
    writeControl: Optional[WriteControl] = None


@app.post(V + "/documents/{documentId}:batchUpdate", dependencies=[auth.require("documents"), STRICT])
def batch_update(documentId: str, request: Request, body: Optional[BatchUpdateBody] = None,
                 fields: Optional[str] = None):
    tree = _mask(fields)
    requests = [r.model_dump(exclude_none=True) for r in (body.requests or [])] if body else []
    control = body.writeControl.model_dump(exclude_none=True) if body and body.writeControl else None
    return _reply(google_docs_data.batch_update(documentId, _account(request), requests, control), tree)
