"""FastAPI server wrapping google_slides_data as REST endpoints.

Mirrors the Google Slides API v1 (slides.googleapis.com/v1) for the four
operations the connector needs: get a presentation, create a presentation, get
one page, and batchUpdate with createSlide, insertText and replaceAllText.
Every operation needs a bearer token from POST /oauth/token, and each one
checks its own scope, so a connected account is not by itself permission to
edit. Errors use Google's own envelope, including request validation failures
and query parameters the method does not take, which Google refuses rather
than ignores.
"""

import json
import re
from typing import List, Literal, Optional

from fastapi import Depends, FastAPI, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

import google_slides_data
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
auth = google_slides_data.auth
GoogleError = google_slides_data.GoogleError

app = FastAPI(title="Google Slides API (Mock)", version="v1")
install_tracker(app)
install_admin_plane(app, store=google_slides_data._store)
# Drive reads and changes this mock's files live, through the peer routes (_linked_peer.py).
_linked_peer.install(app, "google-slides-api", google_slides_data)
auth.install(app)

SHARED_PLANES = ("/admin", "/audit")
SCALAR_TYPES = (("int", "TYPE_INT32"), ("bool", "TYPE_BOOL"), ("string", "TYPE_STRING"), ("float", "TYPE_DOUBLE"))
# Real batchUpdate request kinds this service does not implement: named, so the
# refusal says so instead of calling a genuine Slides request an unknown field.
UNSUPPORTED_REQUESTS = {
    "createShape", "createTable", "createLine", "createImage", "createVideo", "createSheetsChart",
    "insertTableRows", "insertTableColumns", "deleteTableRow", "deleteTableColumn", "replaceAllShapesWithImage",
    "deleteObject", "updatePageElementTransform", "updateSlidesPosition", "deleteText", "duplicateObject",
    "updateShapeProperties", "updateImageProperties", "updateVideoProperties", "updatePageProperties",
    "updateTableCellProperties", "updateLineProperties", "createParagraphBullets", "replaceAllShapesWithSheetsChart",
    "deleteParagraphBullets", "updateParagraphStyle", "updateTextStyle", "updateTableBorderProperties",
    "updateTableColumnProperties", "updateTableRowProperties", "mergeTableCells", "unmergeTableCells",
    "groupObjects", "ungroupObjects", "updatePageElementAltText", "replaceImage", "updateSlideProperties",
    "updatePageElementsZOrder", "updateLineCategory", "rerouteLine", "refreshSheetsChart",
}
CREATE_FIELDS = {"slides", "pageSize", "masters", "layouts", "notesMaster", "locale", "revisionId"}


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


def _validation_error(request: Request, exc: RequestValidationError) -> GoogleError:
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
                                    "Supported requests: createSlide, insertText, replaceAllText.",
                               field=f"requests[{parent[1]}]")
        if not parent and request.url.path.rstrip("/") == V + "/presentations" and name in CREATE_FIELDS:
            return GoogleError(400, f"presentations.create takes only title and presentationId; '{name}' cannot be "
                                    "set. Create the presentation, then add slides with "
                                    "presentations.batchUpdate.", field=name)
        path = _google_path(parent)
        message = (f'Invalid JSON payload received. Unknown name "{name}"'
                   + (f" at '{path}'" if path else "") + ": Cannot find field.")
        return GoogleError(400, message, field=path)
    path = _google_path(parts)
    shown = json.dumps(value, default=str)
    if kind == "literal_error":
        return GoogleError(400, f"Invalid value at '{path}' (type.googleapis.com/google.apps.slides.v1."
                                f"PredefinedLayout), {shown}", field=path)
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
    return _render(_validation_error(request, exc))


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
# Google's edit scope includes reading: only presentations.readonly is read-only.
CAN_READ = auth.require("presentations.readonly", implied_by=("presentations",))


@app.get("/health")
def health():
    return {"status": "ok"}


def _reply(result):
    if isinstance(result, GoogleError):
        return _render(result)
    return result


def _account(request: Request) -> str:
    return request.state.oauth["account_id"]


# --- presentations.get / presentations.pages.get ---------------------------------------------

@app.get(V + "/presentations/{presentationId}", dependencies=[CAN_READ, STRICT])
def get_presentation(presentationId: str, request: Request):
    return _reply(google_slides_data.get_presentation(presentationId, _account(request)))


@app.get(V + "/presentations/{presentationId}/pages/{pageObjectId}", dependencies=[CAN_READ, STRICT])
def get_page(presentationId: str, pageObjectId: str, request: Request):
    return _reply(google_slides_data.get_page(presentationId, pageObjectId, _account(request)))


# --- presentations.create ----------------------------------------------------------------------

class CreatePresentationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    presentationId: Optional[str] = None
    title: Optional[str] = None


@app.post(V + "/presentations", dependencies=[auth.require("presentations"), STRICT])
def create_presentation(request: Request, body: Optional[CreatePresentationBody] = None):
    return _reply(google_slides_data.create_presentation(_account(request), title=body.title if body else None,
                                                         presentation_id=body.presentationId if body else None))


# --- presentations.batchUpdate -----------------------------------------------------------------

class LayoutReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    predefinedLayout: Optional[Literal["BLANK", "CAPTION_ONLY", "TITLE", "TITLE_AND_BODY", "TITLE_AND_TWO_COLUMNS",
                                       "TITLE_ONLY", "SECTION_HEADER", "SECTION_TITLE_AND_DESCRIPTION",
                                       "ONE_COLUMN_TEXT", "MAIN_POINT", "BIG_NUMBER"]] = None
    layoutId: Optional[str] = None


class Placeholder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Optional[str] = None
    index: Optional[int] = None


class PlaceholderIdMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layoutPlaceholder: Optional[Placeholder] = None
    layoutPlaceholderObjectId: Optional[str] = None
    objectId: Optional[str] = None


class CreateSlideRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objectId: Optional[str] = None
    insertionIndex: Optional[int] = None
    slideLayoutReference: Optional[LayoutReference] = None
    placeholderIdMappings: Optional[List[PlaceholderIdMapping]] = None


class TableCellLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rowIndex: Optional[int] = None
    columnIndex: Optional[int] = None


class InsertTextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objectId: Optional[str] = None
    cellLocation: Optional[TableCellLocation] = None
    text: Optional[str] = None
    insertionIndex: Optional[int] = None


class SubstringMatchCriteria(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: Optional[str] = None
    matchCase: Optional[bool] = None


class ReplaceAllTextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    containsText: Optional[SubstringMatchCriteria] = None
    replaceText: Optional[str] = None
    pageObjectIds: Optional[List[str]] = None


class SlidesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    createSlide: Optional[CreateSlideRequest] = None
    insertText: Optional[InsertTextRequest] = None
    replaceAllText: Optional[ReplaceAllTextRequest] = None


class WriteControl(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requiredRevisionId: Optional[str] = None


class BatchUpdateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requests: Optional[List[SlidesRequest]] = None
    writeControl: Optional[WriteControl] = None


@app.post(V + "/presentations/{presentationId}:batchUpdate", dependencies=[auth.require("presentations"), STRICT])
def batch_update(presentationId: str, request: Request, body: Optional[BatchUpdateBody] = None):
    requests = [r.model_dump(exclude_none=True) for r in (body.requests or [])] if body else []
    control = body.writeControl.model_dump(exclude_none=True) if body and body.writeControl else None
    return _reply(google_slides_data.batch_update(presentationId, _account(request), requests, control))
