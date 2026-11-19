"""FastAPI server wrapping ring_data as REST endpoints.

Ring publishes no official public API, so this mock follows the client API
Ring's apps call and open-source clients document (see README.md) for the five
operations the connector needs: list devices, get a device's health, list a
device's event history (rings and motion) with a date filter, get a
recording's details, and set the alarm mode. Every operation needs a bearer
token from POST /oauth/token and checks its own scope, so seeing the cameras is
not by itself permission to disarm the alarm. Errors use {"error"}, request
validation failures included, and a query parameter the operation does not take
is a 400 rather than ignored.
"""

import json
from typing import Literal, Optional

from fastapi import Depends, FastAPI, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

import ring_data
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

C = "/clients_api"
auth = ring_data.auth
RingError = ring_data.RingError

app = FastAPI(title="Ring API (Mock)", version="11")
install_tracker(app)
install_admin_plane(app, store=ring_data._store)
auth.install(app)

SHARED_PLANES = ("/admin", "/audit")


class RingApiError(Exception):
    def __init__(self, error: RingError):
        super().__init__(error.body["error"])
        self.error = error


def _render(error: RingError) -> JSONResponse:
    return JSONResponse(status_code=error.status, content=error.body)


def _validation_error(exc: RequestValidationError) -> RingError:
    errors = exc.errors()
    err = next((e for e in errors if e.get("type") == "extra_forbidden"), errors[0])
    loc = [str(p) for p in (err.get("loc") or ())]
    name = ".".join(loc[1:]) or "body"
    kind = err.get("type", "")
    if kind == "json_invalid":
        return ring_data.invalid("request body is not valid JSON")
    if kind == "extra_forbidden":
        return ring_data.invalid(f"{name} is not a parameter this operation takes")
    if kind == "missing":
        return ring_data.invalid(f"{name} is required")
    if kind == "literal_error":
        return ring_data.invalid(f"{name} must be home, away or disarmed")
    return ring_data.invalid(f"{name} is invalid: {json.dumps(err.get('input'), default=str)}")


@app.exception_handler(RingApiError)
async def _ring_api_error(_request: Request, exc: RingApiError):
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
        return _render(RingError(405, "method not allowed"))
    return _render(RingError(404, "not found"))


def known_query(request: Request):
    """Refuse a query parameter the operation does not declare instead of ignoring it."""
    route = request.scope.get("route")
    allowed = {p.alias for p in route.dependant.query_params} if route is not None else set()
    for name in request.query_params.keys():
        if name not in allowed:
            raise RingApiError(ring_data.invalid(
                f"{name} is not a parameter this operation takes; this mock refuses it rather than ignore it"))


STRICT = Depends(known_query)


@app.get("/health")
def health():
    return {"status": "ok"}


def _reply(result):
    if isinstance(result, RingError):
        return _render(result)
    return result


def _account(request: Request) -> str:
    return request.state.oauth["account_id"]


@app.get(C + "/ring_devices", dependencies=[auth.require("devices.read"), STRICT])
def list_devices(request: Request):
    return ring_data.list_devices(_account(request))


@app.get(C + "/doorbots/{device_id}/health", dependencies=[auth.require("devices.read"), STRICT])
def device_health(device_id: str, request: Request):
    return _reply(ring_data.device_health(device_id, _account(request)))


@app.get(C + "/doorbots/{device_id}/history", dependencies=[auth.require("history.read"), STRICT])
def history(device_id: str, request: Request, limit: int = 20, older_than: Optional[str] = None,
            kind: Optional[str] = None, since: Optional[str] = None, until: Optional[str] = None):
    return _reply(ring_data.history(device_id, _account(request), limit=limit, older_than=older_than, kind=kind,
                                    since=since, until=until))


@app.get(C + "/dings/{ding_id}/recording", dependencies=[auth.require("history.read"), STRICT])
def recording(ding_id: str, request: Request):
    return _reply(ring_data.recording(ding_id, _account(request)))


class ModeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["home", "away", "disarmed"]


@app.put("/api/v1/mode/location/{location_id}", dependencies=[auth.require("alarm.control"), STRICT])
def set_mode(location_id: str, body: ModeBody, request: Request):
    return _reply(ring_data.set_mode(location_id, _account(request), body.mode))
