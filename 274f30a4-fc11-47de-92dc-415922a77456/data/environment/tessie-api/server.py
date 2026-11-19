"""FastAPI server wrapping tessie_data as REST endpoints.

Follows Tessie's REST API (api.tessie.com) for the operations the connector
needs: list vehicles, get a vehicle's state, get battery and charging status,
get its location, lock and unlock, start and stop climate, start and stop
charging, and list past drives. Every operation needs a bearer token from
POST /oauth/token and checks its own scope (the Tesla Fleet API's scope names;
see README.md), so reading the battery is not by itself permission to unlock
the car. Errors use {"error"}, request validation failures included, a query
parameter the operation does not take is a 400 rather than ignored, and a
command refuses a request body.
"""

import json
from typing import Optional

from fastapi import Depends, FastAPI, Query, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

import tessie_data
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

auth = tessie_data.auth
TessieError = tessie_data.TessieError

app = FastAPI(title="Tessie API (Mock)", version="1")
install_tracker(app)
install_admin_plane(app, store=tessie_data._store)
auth.install(app)

SHARED_PLANES = ("/admin", "/audit")
TIMESTAMPS = ("from", "to")


class TessieApiError(Exception):
    def __init__(self, error: TessieError):
        super().__init__(error.body["error"])
        self.error = error


def _render(error: TessieError) -> JSONResponse:
    return JSONResponse(status_code=error.status, content=error.body)


def _validation_error(exc: RequestValidationError) -> TessieError:
    err = exc.errors()[0]
    loc = [str(p) for p in (err.get("loc") or ())]
    name = ".".join(loc[1:]) or "body"
    kind = err.get("type", "")
    if kind == "int_parsing" and name in TIMESTAMPS:
        return tessie_data.invalid(f"{name} must be a Unix timestamp in seconds")
    if kind == "int_parsing":
        return tessie_data.invalid(f"{name} must be an integer")
    if kind == "float_parsing":
        return tessie_data.invalid(f"{name} must be a number")
    if kind == "bool_parsing":
        return tessie_data.invalid(f"{name} must be true or false")
    return tessie_data.invalid(f"{name} is invalid: {json.dumps(err.get('input'), default=str)}")


@app.exception_handler(TessieApiError)
async def _tessie_api_error(_request: Request, exc: TessieApiError):
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
        return _render(TessieError(405, "Method not allowed"))
    return _render(TessieError(404, "Not found"))


def known_query(request: Request):
    """Refuse a query parameter the operation does not declare instead of ignoring it."""
    route = request.scope.get("route")
    allowed = {p.alias for p in route.dependant.query_params} if route is not None else set()
    for name in request.query_params.keys():
        if name not in allowed:
            raise TessieApiError(tessie_data.invalid(
                f"{name} is not a parameter this operation takes; this mock refuses it rather than ignore it"))


STRICT = Depends(known_query)


@app.get("/health")
def health():
    return {"status": "ok"}


def _reply(result):
    if isinstance(result, TessieError):
        return _render(result)
    return result


def _account(request: Request) -> str:
    return request.state.oauth["account_id"]


def _sees_location(request: Request) -> bool:
    scopes = request.state.oauth.get("scopes") or []
    if isinstance(scopes, str):
        scopes = scopes.split()
    return tessie_data.LOCATION_SCOPE in scopes


@app.get("/vehicles", dependencies=[auth.require("vehicle_device_data"), STRICT])
def list_vehicles(request: Request, only_active: bool = False):
    return tessie_data.list_vehicles(_account(request), _sees_location(request), only_active=only_active)


@app.get("/{vin}/state", dependencies=[auth.require("vehicle_device_data"), STRICT])
def vehicle_state(vin: str, request: Request):
    return _reply(tessie_data.vehicle_state(vin, _account(request), _sees_location(request)))


@app.get("/{vin}/battery", dependencies=[auth.require("vehicle_device_data"), STRICT])
def battery(vin: str, request: Request):
    return _reply(tessie_data.battery(vin, _account(request)))


@app.get("/{vin}/location", dependencies=[auth.require("vehicle_location"), STRICT])
def location(vin: str, request: Request):
    return _reply(tessie_data.location(vin, _account(request)))


@app.get("/{vin}/drives", dependencies=[auth.require("vehicle_location"), STRICT])
def drives(vin: str, request: Request, from_: Optional[int] = Query(None, alias="from"), to: Optional[int] = None,
           tag: Optional[str] = None, driver_profile: Optional[str] = None, minimum_distance: Optional[float] = None,
           limit: Optional[int] = None):
    return _reply(tessie_data.drives(vin, _account(request), start=from_, end=to, tag=tag,
                                     driver_profile=driver_profile, minimum_distance=minimum_distance, limit=limit))


async def _command(vin: str, request: Request, name: str):
    raw = (await request.body()).strip()
    if raw and raw != b"{}":
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = None
        fields = sorted(parsed) if isinstance(parsed, dict) else []
        named = f"; remove {', '.join(fields)}" if fields else ""
        return _render(tessie_data.invalid(f"{name} takes no request body{named}"))
    return _reply(tessie_data.command(vin, _account(request), name))


@app.post("/{vin}/command/lock", dependencies=[auth.require("vehicle_cmds"), STRICT])
async def lock(vin: str, request: Request):
    return await _command(vin, request, "lock")


@app.post("/{vin}/command/unlock", dependencies=[auth.require("vehicle_cmds"), STRICT])
async def unlock(vin: str, request: Request):
    return await _command(vin, request, "unlock")


@app.post("/{vin}/command/start_climate", dependencies=[auth.require("vehicle_cmds"), STRICT])
async def start_climate(vin: str, request: Request):
    return await _command(vin, request, "start_climate")


@app.post("/{vin}/command/stop_climate", dependencies=[auth.require("vehicle_cmds"), STRICT])
async def stop_climate(vin: str, request: Request):
    return await _command(vin, request, "stop_climate")


@app.post("/{vin}/command/start_charging", dependencies=[auth.require("vehicle_charging_cmds"), STRICT])
async def start_charging(vin: str, request: Request):
    return await _command(vin, request, "start_charging")


@app.post("/{vin}/command/stop_charging", dependencies=[auth.require("vehicle_charging_cmds"), STRICT])
async def stop_charging(vin: str, request: Request):
    return await _command(vin, request, "stop_charging")
