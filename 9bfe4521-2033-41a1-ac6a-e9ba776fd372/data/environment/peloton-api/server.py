"""FastAPI server wrapping peloton_data as REST endpoints.

Peloton publishes no official public API, so this mock follows the member API
Peloton's apps call and open-source clients document (see README.md) for the
five operations the connector needs: get the profile, list workouts with a date
filter, get one workout, get a workout's performance summary, and list
available classes with discipline and duration filters. Every operation needs a
bearer token from POST /oauth/token and checks its own scope. Errors use
Peloton's {"status", "error_code", "subcode", "message", "details"} body,
request validation failures included, and a query parameter the operation does
not take is a 400 rather than ignored.
"""

import json
from typing import Optional

from fastapi import Depends, FastAPI, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

import peloton_data
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

auth = peloton_data.auth
PelotonError = peloton_data.PelotonError

app = FastAPI(title="Peloton API (Mock)", version="1")
install_tracker(app)
install_admin_plane(app, store=peloton_data._store)
auth.install(app)

SHARED_PLANES = ("/admin", "/audit")


class PelotonApiError(Exception):
    def __init__(self, error: PelotonError):
        super().__init__(error.body["message"])
        self.error = error


def _render(error: PelotonError) -> JSONResponse:
    return JSONResponse(status_code=error.status, content=error.body)


def _validation_error(exc: RequestValidationError) -> PelotonError:
    err = exc.errors()[0]
    loc = [str(p) for p in (err.get("loc") or ())]
    name = ".".join(loc[1:]) or "body"
    if err.get("type") == "int_parsing":
        return peloton_data.invalid(f"{name} must be an integer", name)
    return peloton_data.invalid(f"{name} is invalid: {json.dumps(err.get('input'), default=str)}", name)


@app.exception_handler(PelotonApiError)
async def _peloton_api_error(_request: Request, exc: PelotonApiError):
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
        return _render(PelotonError(405, "Method not allowed"))
    return _render(peloton_data.not_found("Not found"))


def known_query(request: Request):
    """Refuse a query parameter the operation does not declare instead of ignoring it."""
    route = request.scope.get("route")
    allowed = {p.alias for p in route.dependant.query_params} if route is not None else set()
    for name in request.query_params.keys():
        if name not in allowed:
            raise PelotonApiError(peloton_data.invalid(
                f"{name} is not a parameter this operation takes; this mock refuses it rather than ignore it", name))


STRICT = Depends(known_query)


@app.get("/health")
def health():
    return {"status": "ok"}


def _reply(result):
    if isinstance(result, PelotonError):
        return _render(result)
    return result


def _account(request: Request) -> str:
    return request.state.oauth["account_id"]


@app.get("/api/me", dependencies=[auth.require("profile.read"), STRICT])
def me(request: Request):
    return _reply(peloton_data.profile(_account(request)))


@app.get("/api/user/{user_id}/workouts", dependencies=[auth.require("workouts.read"), STRICT])
def list_workouts(user_id: str, request: Request, joins: Optional[str] = None, limit: int = 20, page: int = 0,
                  start_date: Optional[str] = None, end_date: Optional[str] = None):
    return _reply(peloton_data.list_workouts(user_id, _account(request), joins=joins, limit=limit, page=page,
                                             start_date=start_date, end_date=end_date))


@app.get("/api/workout/{workout_id}", dependencies=[auth.require("workouts.read"), STRICT])
def get_workout(workout_id: str, request: Request, joins: Optional[str] = None):
    return _reply(peloton_data.get_workout(workout_id, _account(request), joins=joins))


@app.get("/api/workout/{workout_id}/performance_graph", dependencies=[auth.require("workouts.read"), STRICT])
def performance_graph(workout_id: str, request: Request, every_n: int = 5):
    return _reply(peloton_data.performance_graph(workout_id, _account(request), every_n=every_n))


@app.get("/api/v2/ride/archived", dependencies=[auth.require("classes.read"), STRICT])
def archived_classes(browse_category: Optional[str] = None, duration: Optional[str] = None,
                     instructor_id: Optional[str] = None, limit: int = 18, page: int = 0):
    return _reply(peloton_data.archived_classes(browse_category=browse_category, duration=duration,
                                                instructor_id=instructor_id, limit=limit, page=page))
