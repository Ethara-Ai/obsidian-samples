"""FastAPI server wrapping granola_data as REST endpoints.

Granola publishes no widely documented public REST API, so this mock serves a
plain REST shape of its own (see README.md) for the three operations the
connector needs: list meeting notes with a date filter, get one note with its
summary, action items and transcript, and search notes by text. Every operation
needs a bearer token from POST /oauth/token and checks its own scope. Errors use
this mock's body ({"error": {"code", "message", "param"}}), request validation
failures included, and a query parameter the operation does not take is a 400
rather than ignored.
"""

import json
from typing import Optional

from fastapi import Depends, FastAPI, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

import granola_data
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
auth = granola_data.auth
GranolaError = granola_data.GranolaError

app = FastAPI(title="Granola API (Mock)", version="v1")
install_tracker(app)
install_admin_plane(app, store=granola_data._store)
auth.install(app)

SHARED_PLANES = ("/admin", "/audit")
EXPECTED = (("bool", "must be true or false"), ("int", "must be an integer"), ("string", "must be a string"))


class GranolaApiError(Exception):
    def __init__(self, error: GranolaError):
        super().__init__(error.body["error"]["message"])
        self.error = error


def _render(error: GranolaError) -> JSONResponse:
    return JSONResponse(status_code=error.status, content=error.body)


def _validation_error(exc: RequestValidationError) -> GranolaError:
    err = exc.errors()[0]
    loc = [str(p) for p in (err.get("loc") or ())]
    name = ".".join(loc[1:]) or (loc[0] if loc else "request")
    kind = err.get("type", "")
    if kind == "missing":
        return granola_data.invalid(name, f"{name} is required.")
    message = next((text for prefix, text in EXPECTED if kind.startswith(prefix)), "is not valid")
    return granola_data.invalid(name, f"{name} {message}, got {json.dumps(err.get('input'), default=str)}.")


@app.exception_handler(GranolaApiError)
async def _granola_api_error(_request: Request, exc: GranolaApiError):
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
        return _render(GranolaError(405, "method_not_allowed", f"{request.method} is not allowed on this path."))
    return _render(GranolaError(404, "not_found", f"No route matches {request.url.path}."))


def known_query(request: Request):
    """Refuse a query parameter the operation does not declare instead of ignoring it."""
    route = request.scope.get("route")
    allowed = {p.alias for p in route.dependant.query_params} if route is not None else set()
    for name in request.query_params.keys():
        if name not in allowed:
            raise GranolaApiError(granola_data.invalid(
                name, f"{name} is not a parameter this operation takes; this mock refuses it rather than ignore it, "
                      "so a misspelt filter cannot pass for one that worked."))


STRICT = Depends(known_query)


@app.get("/health")
def health():
    return {"status": "ok"}


def _reply(result):
    if isinstance(result, GranolaError):
        return _render(result)
    return result


def _account(request: Request) -> str:
    return request.state.oauth["account_id"]


@app.get(V + "/notes", dependencies=[auth.require("notes:read"), STRICT])
def list_notes(request: Request, start_date: Optional[str] = None, end_date: Optional[str] = None,
               limit: int = 20, cursor: Optional[str] = None):
    return _reply(granola_data.list_notes(_account(request), start_date=start_date, end_date=end_date, limit=limit,
                                          cursor=cursor))


@app.get(V + "/notes/search", dependencies=[auth.require("notes:search"), STRICT])
def search_notes(request: Request, q: Optional[str] = None, limit: int = 20, cursor: Optional[str] = None):
    return _reply(granola_data.search_notes(_account(request), q, limit=limit, cursor=cursor))


@app.get(V + "/notes/{note_id}", dependencies=[auth.require("notes:read"), STRICT])
def get_note(note_id: str, request: Request):
    return _reply(granola_data.get_note(note_id, _account(request)))
