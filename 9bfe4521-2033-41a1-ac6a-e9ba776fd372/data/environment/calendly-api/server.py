"""FastAPI server wrapping calendly_data as REST endpoints.

Mirrors the Calendly API v2 (api.calendly.com) for the operations the
connector needs: get the current user, list event types, list scheduled events
with status and date filters, get one scheduled event, list an event's
invitees, and cancel a scheduled event. Every operation needs a bearer token
from POST /oauth/token and checks its own scope, so a connected account is not
by itself permission to cancel. Errors use Calendly's body ({"title",
"message", "details"}), request validation failures included, and a query
parameter the operation does not take is a 400 rather than ignored.
"""

from typing import Optional

from fastapi import Depends, FastAPI, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

import calendly_data
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

auth = calendly_data.auth
CalendlyError = calendly_data.CalendlyError

app = FastAPI(title="Calendly API (Mock)", version="v2")
install_tracker(app)
install_admin_plane(app, store=calendly_data._store)
auth.install(app)

SHARED_PLANES = ("/admin", "/audit")
EXPECTED = (("bool", "must be true or false"), ("int", "must be an integer"), ("string", "must be a string"))


class CalendlyApiError(Exception):
    def __init__(self, error: CalendlyError):
        super().__init__(error.body["message"])
        self.error = error


def _render(error: CalendlyError) -> JSONResponse:
    return JSONResponse(status_code=error.status, content=error.body)


def _validation_error(exc: RequestValidationError) -> CalendlyError:
    err = exc.errors()[0]
    loc = [str(p) for p in (err.get("loc") or ())]
    kind = err.get("type", "")
    if kind == "json_invalid":
        return calendly_data.invalid("body", "must be valid JSON")
    parameter = ".".join(loc[1:]) or (loc[0] if loc else "body")
    if kind == "extra_forbidden":
        return calendly_data.invalid(parameter, "is not a valid parameter")
    if kind == "missing":
        return calendly_data.invalid(parameter, "is required")
    message = next((text for prefix, text in EXPECTED if kind.startswith(prefix)), "is invalid")
    return calendly_data.invalid(parameter, message)


@app.exception_handler(CalendlyApiError)
async def _calendly_api_error(_request: Request, exc: CalendlyApiError):
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
    return _render(calendly_data.not_found())


def known_query(request: Request):
    """Refuse a query parameter the operation does not declare instead of ignoring it."""
    route = request.scope.get("route")
    allowed = {p.alias for p in route.dependant.query_params} if route is not None else set()
    for name in request.query_params.keys():
        if name not in allowed:
            raise CalendlyApiError(calendly_data.invalid(
                name, "is not a parameter this operation takes; this mock refuses it rather than ignore it, so a "
                      "misspelt filter cannot pass for one that worked"))


STRICT = Depends(known_query)


@app.get("/health")
def health():
    return {"status": "ok"}


def _reply(result, status=200):
    if isinstance(result, CalendlyError):
        return _render(result)
    return JSONResponse(status_code=status, content=result)


def _account(request: Request) -> str:
    return request.state.oauth["account_id"]


def _link(request: Request) -> str:
    return str(request.url.replace(query=""))


@app.get("/users/me", dependencies=[auth.require("users:read"), STRICT])
def current_user(request: Request):
    return _reply(calendly_data.current_user(_account(request)))


@app.get("/event_types", dependencies=[auth.require("event_types:read"), STRICT])
def list_event_types(request: Request, user: Optional[str] = None, organization: Optional[str] = None,
                     active: Optional[bool] = None, sort: Optional[str] = None, count: Optional[int] = None,
                     page_token: Optional[str] = None):
    return _reply(calendly_data.list_event_types(
        _account(request), _link(request), user=user, organization=organization, active=active, sort=sort,
        count=count, page_token=page_token))


@app.get("/scheduled_events", dependencies=[auth.require("scheduled_events:read"), STRICT])
def list_scheduled_events(request: Request, user: Optional[str] = None, organization: Optional[str] = None,
                          invitee_email: Optional[str] = None, status: Optional[str] = None,
                          min_start_time: Optional[str] = None, max_start_time: Optional[str] = None,
                          sort: Optional[str] = None, count: Optional[int] = None,
                          page_token: Optional[str] = None):
    return _reply(calendly_data.list_scheduled_events(
        _account(request), _link(request), user=user, organization=organization, invitee_email=invitee_email,
        status=status, min_start_time=min_start_time, max_start_time=max_start_time, sort=sort, count=count,
        page_token=page_token))


@app.get("/scheduled_events/{uuid}", dependencies=[auth.require("scheduled_events:read"), STRICT])
def get_scheduled_event(uuid: str, request: Request):
    return _reply(calendly_data.get_scheduled_event(uuid, _account(request)))


@app.get("/scheduled_events/{uuid}/invitees", dependencies=[auth.require("scheduled_events:read"), STRICT])
def list_invitees(uuid: str, request: Request, status: Optional[str] = None, sort: Optional[str] = None,
                  email: Optional[str] = None, count: Optional[int] = None, page_token: Optional[str] = None):
    return _reply(calendly_data.list_invitees(uuid, _account(request), _link(request), status=status, sort=sort,
                                              email=email, count=count, page_token=page_token))


class CancelBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Optional[str] = None


@app.post("/scheduled_events/{uuid}/cancellation", status_code=201,
          dependencies=[auth.require("scheduled_events:write"), STRICT])
def cancel_event(uuid: str, request: Request, body: Optional[CancelBody] = None):
    return _reply(calendly_data.cancel_event(uuid, _account(request), reason=body.reason if body else None),
                  status=201)
