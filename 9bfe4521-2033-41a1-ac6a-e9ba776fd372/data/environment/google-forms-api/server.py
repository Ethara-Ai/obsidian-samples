"""FastAPI server wrapping google_forms_data as REST endpoints.

Mirrors the Google Forms API v1 (forms.googleapis.com/v1) for the five
operations the connector needs: get a form, create a form, batchUpdate to add
or change a question (createItem and updateItem), list a form's responses, and
get one response. Every operation needs a bearer token from POST /oauth/token,
and each one checks its own scope, so a connected account is not by itself
permission to edit a form or read who answered it. Errors use Google's own
envelope, including request validation failures and query parameters the
method does not take, which Google refuses rather than ignores.
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

import google_forms_data
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
auth = google_forms_data.auth
GoogleError = google_forms_data.GoogleError

app = FastAPI(title="Google Forms API (Mock)", version="v1")
install_tracker(app)
install_admin_plane(app, store=google_forms_data._store)
# Drive reads and changes this mock's files live, through the peer routes (_linked_peer.py).
_linked_peer.install(app, "google-forms-api", google_forms_data)
auth.install(app)

SHARED_PLANES = ("/admin", "/audit")
SCALAR_TYPES = (("int", "TYPE_INT32"), ("bool", "TYPE_BOOL"), ("string", "TYPE_STRING"), ("float", "TYPE_DOUBLE"))
# Real Forms request, item and question kinds this service does not implement: named,
# so the refusal says so instead of calling a genuine Forms field unknown.
UNSUPPORTED = {
    **dict.fromkeys(("updateFormInfo", "updateSettings", "deleteItem", "moveItem", "updatePublishSettings"),
                    "batchUpdate request kind; supported requests: createItem, updateItem"),
    **dict.fromkeys(("questionGroupItem", "imageItem", "videoItem"),
                    "item kind; supported items: questionItem, pageBreakItem, textItem"),
    **dict.fromkeys(("timeQuestion", "fileUploadQuestion", "ratingQuestion", "rowQuestion"),
                    "question kind; supported questions: choiceQuestion, textQuestion, scaleQuestion, "
                    "dateQuestion"),
    **dict.fromkeys(("grading", "isOther", "goToAction", "goToSectionId", "image"), "setting"),
}
CREATE_ONLY_INFO = {"description", "items", "settings", "formId", "revisionId", "responderUri", "linkedSheetId",
                    "publishSettings"}


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
        path = _google_path(parent)
        if name in UNSUPPORTED:
            return GoogleError(400, f"Invalid {path or 'request'}: {name} is not supported by this service "
                                    f"(a Forms {UNSUPPORTED[name]}).", field=path)
        if request.method == "POST" and request.url.path.rstrip("/") == V + "/forms" and name in CREATE_ONLY_INFO:
            return GoogleError(400, "Only info.title and info.documentTitle can be set when creating a form. Create "
                                    "the form, then add items and settings with forms.batchUpdate.", field=path or name)
        message = (f'Invalid JSON payload received. Unknown name "{name}"'
                   + (f" at '{path}'" if path else "") + ": Cannot find field.")
        return GoogleError(400, message, field=path)
    path = _google_path(parts)
    shown = json.dumps(value, default=str)
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


@app.get("/health")
def health():
    return {"status": "ok"}


def _reply(result):
    if isinstance(result, GoogleError):
        return _render(result)
    return result


def _account(request: Request) -> str:
    return request.state.oauth["account_id"]


# --- forms.get ------------------------------------------------------------------------------

@app.get(V + "/forms/{formId}", dependencies=[auth.require("forms.body.readonly", implied_by=("forms.body",)), STRICT])
def get_form(formId: str, request: Request):
    return _reply(google_forms_data.get_form(formId, _account(request)))


# --- forms.create ---------------------------------------------------------------------------

class CreateInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = None
    documentTitle: Optional[str] = None


class CreateFormBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    info: Optional[CreateInfo] = None


@app.post(V + "/forms", dependencies=[auth.require("forms.body"), STRICT])
def create_form(request: Request, body: Optional[CreateFormBody] = None):
    info = body.info.model_dump(exclude_none=True) if body and body.info else {}
    return _reply(google_forms_data.create_form(_account(request), info))


# --- forms.batchUpdate ------------------------------------------------------------------------

class Option(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Optional[str] = None


class ChoiceQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Optional[Literal["RADIO", "CHECKBOX", "DROP_DOWN"]] = None
    options: Optional[List[Option]] = None
    shuffle: Optional[bool] = None


class TextQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paragraph: Optional[bool] = None


class ScaleQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    low: Optional[int] = None
    high: Optional[int] = None
    lowLabel: Optional[str] = None
    highLabel: Optional[str] = None


class DateQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    includeTime: Optional[bool] = None
    includeYear: Optional[bool] = None


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questionId: Optional[str] = None
    required: Optional[bool] = None
    choiceQuestion: Optional[ChoiceQuestion] = None
    textQuestion: Optional[TextQuestion] = None
    scaleQuestion: Optional[ScaleQuestion] = None
    dateQuestion: Optional[DateQuestion] = None


class QuestionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: Optional[Question] = None


class EmptyItem(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid")

    itemId: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    questionItem: Optional[QuestionItem] = None
    pageBreakItem: Optional[EmptyItem] = None
    textItem: Optional[EmptyItem] = None


class Location(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: Optional[int] = None


class CreateItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item: Optional[Item] = None
    location: Optional[Location] = None


class UpdateItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item: Optional[Item] = None
    location: Optional[Location] = None
    updateMask: Optional[str] = None


class FormRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    createItem: Optional[CreateItemRequest] = None
    updateItem: Optional[UpdateItemRequest] = None


class WriteControl(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requiredRevisionId: Optional[str] = None
    targetRevisionId: Optional[str] = None


class BatchUpdateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    includeFormInResponse: Optional[bool] = None
    requests: Optional[List[FormRequest]] = None
    writeControl: Optional[WriteControl] = None


@app.post(V + "/forms/{formId}:batchUpdate", dependencies=[auth.require("forms.body"), STRICT])
def batch_update(formId: str, request: Request, body: Optional[BatchUpdateBody] = None):
    requests = [r.model_dump(exclude_none=True) for r in (body.requests or [])] if body else []
    control = body.writeControl.model_dump(exclude_none=True) if body and body.writeControl else None
    return _reply(google_forms_data.batch_update(formId, _account(request), requests,
                                                 include_form=bool(body and body.includeFormInResponse),
                                                 write_control=control))


# --- forms.responses.list / forms.responses.get ------------------------------------------------

@app.get(V + "/forms/{formId}/responses", dependencies=[auth.require("forms.responses.readonly"), STRICT])
def list_responses(formId: str, request: Request, filter: Optional[str] = None, pageSize: int = 5000,
                   pageToken: Optional[str] = None):
    return _reply(google_forms_data.list_responses(formId, _account(request), filter=filter, page_size=pageSize,
                                                   page_token=pageToken))


@app.get(V + "/forms/{formId}/responses/{responseId}",
         dependencies=[auth.require("forms.responses.readonly"), STRICT])
def get_response(formId: str, responseId: str, request: Request):
    return _reply(google_forms_data.get_response(formId, responseId, _account(request)))
