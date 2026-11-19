"""FastAPI server wrapping home_assistant_data as REST endpoints.

Mirrors the Home Assistant REST API (/api) for the five operations the
connector needs: read the configuration, list every entity's state, get one
entity's state, call a service on entities, and read entities' history for a
period. Every operation needs a bearer token from POST /oauth/token and checks
its own scope, so reading the house is not by itself permission to unlock a
door. Errors use Home Assistant's body ({"message"}), invalid JSON and service
data included, and a query parameter the operation does not take is a 400
rather than ignored. The scope names are this mock's own; Home Assistant's
long-lived tokens carry none.
"""

import json
from typing import Optional

from fastapi import Depends, FastAPI, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

import home_assistant_data
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

V = "/api"
auth = home_assistant_data.auth
HassError = home_assistant_data.HassError

app = FastAPI(title="Home Assistant API (Mock)", version="2026.9.3")
install_tracker(app)
install_admin_plane(app, store=home_assistant_data._store)
auth.install(app)

SHARED_PLANES = ("/admin", "/audit")


class HassApiError(Exception):
    def __init__(self, error: HassError):
        super().__init__(error.body["message"])
        self.error = error


def _render(error: HassError) -> JSONResponse:
    return JSONResponse(status_code=error.status, content=error.body)


@app.exception_handler(HassApiError)
async def _hass_api_error(_request: Request, exc: HassApiError):
    return _render(exc.error)


@app.exception_handler(RequestValidationError)
async def _invalid_request(request: Request, exc: RequestValidationError):
    if request.url.path.startswith(SHARED_PLANES):
        return await request_validation_exception_handler(request, exc)
    return _render(home_assistant_data.bad("Invalid request."))


@app.exception_handler(StarletteHTTPException)
async def _http_error(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith(SHARED_PLANES) or exc.status_code not in (404, 405):
        return await http_exception_handler(request, exc)
    if exc.status_code == 405:
        return _render(HassError(405, "Method Not Allowed"))
    return _render(HassError(404, "Not Found"))


def known_query(request: Request):
    """Refuse a query parameter the operation does not declare instead of ignoring it."""
    route = request.scope.get("route")
    allowed = {p.alias for p in route.dependant.query_params} if route is not None else set()
    for name in request.query_params.keys():
        if name not in allowed:
            raise HassApiError(home_assistant_data.bad(
                f"{name} is not a parameter this operation takes; this mock refuses it rather than ignore it, "
                "so a misspelt filter cannot pass for one that worked"))


STRICT = Depends(known_query)


@app.get("/health")
def health():
    return {"status": "ok"}


def _reply(result):
    if isinstance(result, HassError):
        return _render(result)
    return result


def _account(request: Request) -> str:
    return request.state.oauth["account_id"]


@app.get(V + "/config", dependencies=[auth.require("homeassistant:read"), STRICT])
def get_config(request: Request):
    return _reply(home_assistant_data.get_config(_account(request)))


@app.get(V + "/states", dependencies=[auth.require("homeassistant:read"), STRICT])
def list_states(request: Request):
    return home_assistant_data.list_states(_account(request))


@app.get(V + "/states/{entity_id}", dependencies=[auth.require("homeassistant:read"), STRICT])
def get_state(entity_id: str, request: Request):
    return _reply(home_assistant_data.get_state(entity_id, _account(request)))


@app.post(V + "/services/{domain}/{service}", dependencies=[auth.require("homeassistant:control"), STRICT])
async def call_service(domain: str, service: str, request: Request):
    raw = await request.body()
    data = {}
    if raw.strip():
        try:
            data = json.loads(raw)
        except ValueError:
            return _render(home_assistant_data.bad("Data should be valid JSON."))
        if not isinstance(data, dict):
            return _render(home_assistant_data.bad("Data should be valid JSON."))
    return _reply(home_assistant_data.call_service(domain, service, _account(request), data))


@app.get(V + "/history/period/{timestamp}", dependencies=[auth.require("homeassistant:read"), STRICT])
def history(timestamp: str, request: Request, filter_entity_id: Optional[str] = None, end_time: Optional[str] = None,
            minimal_response: Optional[str] = None, no_attributes: Optional[str] = None,
            significant_changes_only: Optional[str] = None):
    return _reply(home_assistant_data.history(
        _account(request), timestamp, filter_entity_id=filter_entity_id, end_time=end_time,
        minimal_response=minimal_response is not None, no_attributes=no_attributes is not None,
        significant_changes_only=significant_changes_only is not None))
