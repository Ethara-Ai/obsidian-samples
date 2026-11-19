"""FastAPI server wrapping function_health_data as REST endpoints.

Function Health publishes no public API, so this mock serves a plain REST shape
of its own (see README.md) for the four operations the connector needs: list
lab visits, list a visit's biomarker results with their in-range or
out-of-range status, get one biomarker's history over time, and list
recommendations. Every operation needs a bearer token from POST /oauth/token
and checks its own scope. Errors use {"error": {"code", "message", "param"}},
request validation failures included, and a query parameter the operation
does not take is a 400 rather than ignored.
"""

import json
from typing import Optional

from fastapi import Depends, FastAPI, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

import function_health_data
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

auth = function_health_data.auth
FunctionHealthError = function_health_data.FunctionHealthError

app = FastAPI(title="Function Health API (Mock)", version="1")
install_tracker(app)
install_admin_plane(app, store=function_health_data._store)
auth.install(app)

SHARED_PLANES = ("/admin", "/audit")


class FunctionHealthApiError(Exception):
    def __init__(self, error: FunctionHealthError):
        super().__init__(error.body["error"]["message"])
        self.error = error


def _render(error: FunctionHealthError) -> JSONResponse:
    return JSONResponse(status_code=error.status, content=error.body)


def _validation_error(exc: RequestValidationError) -> FunctionHealthError:
    err = exc.errors()[0]
    loc = [str(p) for p in (err.get("loc") or ())]
    name = ".".join(loc[1:]) or "body"
    if err.get("type") == "int_parsing":
        return function_health_data.invalid(f"{name} must be an integer", name)
    return function_health_data.invalid(f"{name} is invalid: {json.dumps(err.get('input'), default=str)}", name)


@app.exception_handler(FunctionHealthApiError)
async def _function_health_api_error(_request: Request, exc: FunctionHealthApiError):
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
        return _render(FunctionHealthError(405, "method_not_allowed", "method not allowed"))
    return _render(function_health_data.not_found("not found"))


def known_query(request: Request):
    """Refuse a query parameter the operation does not declare instead of ignoring it."""
    route = request.scope.get("route")
    allowed = {p.alias for p in route.dependant.query_params} if route is not None else set()
    for name in request.query_params.keys():
        if name not in allowed:
            raise FunctionHealthApiError(function_health_data.invalid(
                f"{name} is not a parameter this operation takes; this mock refuses it rather than ignore it", name))


STRICT = Depends(known_query)


@app.get("/health")
def health():
    return {"status": "ok"}


def _reply(result):
    if isinstance(result, FunctionHealthError):
        return _render(result)
    return result


def _account(request: Request) -> str:
    return request.state.oauth["account_id"]


@app.get("/v1/visits", dependencies=[auth.require("visits.read"), STRICT])
def list_visits(request: Request, status: Optional[str] = None, limit: int = 20, cursor: Optional[str] = None):
    return _reply(function_health_data.list_visits(_account(request), status=status, limit=limit, cursor=cursor))


@app.get("/v1/visits/{visit_id}/results", dependencies=[auth.require("results.read"), STRICT])
def visit_results(visit_id: str, request: Request, status: Optional[str] = None, category: Optional[str] = None,
                  limit: int = 100, cursor: Optional[str] = None):
    return _reply(function_health_data.visit_results(visit_id, _account(request), status=status, category=category,
                                                     limit=limit, cursor=cursor))


@app.get("/v1/biomarkers/{biomarker_id}/history", dependencies=[auth.require("results.read"), STRICT])
def biomarker_history(biomarker_id: str, request: Request, start_date: Optional[str] = None,
                      end_date: Optional[str] = None):
    return _reply(function_health_data.biomarker_history(biomarker_id, _account(request), start_date=start_date,
                                                         end_date=end_date))


@app.get("/v1/recommendations", dependencies=[auth.require("recommendations.read"), STRICT])
def list_recommendations(request: Request, category: Optional[str] = None, visit_id: Optional[str] = None,
                         status: Optional[str] = None):
    return _reply(function_health_data.list_recommendations(_account(request), category=category, visit_id=visit_id,
                                                            status=status))
