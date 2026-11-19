"""FastAPI server wrapping phone_data as REST endpoints.

The client names a Phone connector without describing it, so this mock serves an
assumed operation set in a plain REST shape of its own (see README.md): list
recent calls, place a call (which records an outgoing call), list text
conversations, list the messages in a conversation, and send a text message.
Every operation needs a bearer token from POST /oauth/token and checks its own
scope, so reading the call log is not by itself permission to call or text.
Errors use this mock's body ({"error": {"code", "message", "param"}}), request
validation failures included, and a query parameter the operation does not take
is a 400 rather than ignored.
"""

import json
from typing import Optional

from fastapi import Depends, FastAPI, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

import phone_data
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
auth = phone_data.auth
PhoneError = phone_data.PhoneError

app = FastAPI(title="Phone API (Mock)", version="v1")
install_tracker(app)
install_admin_plane(app, store=phone_data._store)
auth.install(app)

SHARED_PLANES = ("/admin", "/audit")
EXPECTED = (("bool", "must be true or false"), ("int", "must be an integer"), ("string", "must be a string"))


class PhoneApiError(Exception):
    def __init__(self, error: PhoneError):
        super().__init__(error.body["error"]["message"])
        self.error = error


def _render(error: PhoneError) -> JSONResponse:
    return JSONResponse(status_code=error.status, content=error.body)


def _validation_error(exc: RequestValidationError) -> PhoneError:
    err = exc.errors()[0]
    loc = [str(p) for p in (err.get("loc") or ())]
    name = ".".join(loc[1:]) or (loc[0] if loc else "request")
    kind = err.get("type", "")
    if kind == "json_invalid":
        return phone_data.invalid("body", "The request body must be valid JSON.")
    if kind == "missing":
        return phone_data.invalid(name, f"{name} is required.")
    if kind == "extra_forbidden":
        return phone_data.invalid(name, f"{name} is not a field this operation takes.")
    message = next((text for prefix, text in EXPECTED if kind.startswith(prefix)), "is not valid")
    return phone_data.invalid(name, f"{name} {message}, got {json.dumps(err.get('input'), default=str)}.")


@app.exception_handler(PhoneApiError)
async def _phone_api_error(_request: Request, exc: PhoneApiError):
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
    if exc.status_code == 405:
        return _render(PhoneError(405, "method_not_allowed", f"{request.method} is not allowed on this path."))
    return _render(PhoneError(404, "not_found", f"No route matches {request.url.path}."))


def known_query(request: Request):
    """Refuse a query parameter the operation does not declare instead of ignoring it."""
    route = request.scope.get("route")
    allowed = {p.alias for p in route.dependant.query_params} if route is not None else set()
    for name in request.query_params.keys():
        if name not in allowed:
            raise PhoneApiError(phone_data.invalid(
                name, f"{name} is not a parameter this operation takes; this mock refuses it rather than ignore it, "
                      "so a misspelt filter cannot pass for one that worked."))


STRICT = Depends(known_query)


@app.get("/health")
def health():
    return {"status": "ok"}


def _reply(result, status=200):
    if isinstance(result, PhoneError):
        return _render(result)
    return JSONResponse(status_code=status, content=result)


def _account(request: Request) -> str:
    return request.state.oauth["account_id"]


# --- calls --------------------------------------------------------------------------------------

@app.get(V + "/calls", dependencies=[auth.require("calls.read"), STRICT])
def list_calls(request: Request, direction: Optional[str] = None, status: Optional[str] = None,
               since: Optional[str] = None, until: Optional[str] = None, limit: int = 25,
               cursor: Optional[str] = None):
    return _reply(phone_data.list_calls(_account(request), direction=direction, status=status, since=since,
                                        until=until, limit=limit, cursor=cursor))


class PlaceCallBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to: str


@app.post(V + "/calls", status_code=201, dependencies=[auth.require("calls.write"), STRICT])
def place_call(body: PlaceCallBody, request: Request):
    return _reply(phone_data.place_call(_account(request), body.to), status=201)


# --- texts ----------------------------------------------------------------------------------------

@app.get(V + "/conversations", dependencies=[auth.require("messages.read"), STRICT])
def list_conversations(request: Request, unread_only: bool = False, limit: int = 25, cursor: Optional[str] = None):
    return _reply(phone_data.list_conversations(_account(request), unread_only=unread_only, limit=limit,
                                                cursor=cursor))


@app.get(V + "/conversations/{conversation_id}/messages", dependencies=[auth.require("messages.read"), STRICT])
def list_messages(conversation_id: str, request: Request, limit: int = 25, cursor: Optional[str] = None):
    return _reply(phone_data.list_messages(conversation_id, _account(request), limit=limit, cursor=cursor))


class SendTextBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to: str
    body: str


@app.post(V + "/messages", status_code=201, dependencies=[auth.require("messages.send"), STRICT])
def send_text(body: SendTextBody, request: Request):
    return _reply(phone_data.send_text(_account(request), body.to, body.body), status=201)
