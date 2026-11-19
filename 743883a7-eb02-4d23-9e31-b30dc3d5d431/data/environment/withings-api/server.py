"""FastAPI server wrapping withings_data as REST endpoints.

Follows the Withings public API's action-style requests: each webservice is one
POST whose form fields carry `action` and its parameters, answered with
`{"status", "body"}`. Four operations: body measures for a date range
(/measure getmeas), daily activity (/v2/measure getactivity), sleep summaries
(/v2/sleep getsummary) and devices (/v2/user getdevice). Every webservice
needs a bearer token from POST /oauth/token and checks its own scope. Errors
are Withings' own: HTTP 200 with a nonzero `status` and an `error` message,
for request validation failures, a form field the action does not take, and a
query parameter too.
"""

import json
from urllib.parse import parse_qs

from fastapi import Depends, FastAPI, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

import withings_data
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

auth = withings_data.auth
WithingsError = withings_data.WithingsError

app = FastAPI(title="Withings API (Mock)", version="2")
install_tracker(app)
install_admin_plane(app, store=withings_data._store)
auth.install(app)

SHARED_PLANES = ("/admin", "/audit")


class WithingsApiError(Exception):
    def __init__(self, error: WithingsError):
        super().__init__(error.body["error"])
        self.error = error


def _render(error: WithingsError) -> JSONResponse:
    return JSONResponse(status_code=error.status, content=error.body)


@app.exception_handler(WithingsApiError)
async def _withings_api_error(_request: Request, exc: WithingsApiError):
    return _render(exc.error)


@app.exception_handler(RequestValidationError)
async def _invalid_request(request: Request, exc: RequestValidationError):
    if request.url.path.startswith(SHARED_PLANES):
        return await request_validation_exception_handler(request, exc)
    err = exc.errors()[0]
    return _render(withings_data.invalid(f"{err.get('msg', 'invalid request')}: {json.dumps(err.get('input'), default=str)}"))


@app.exception_handler(StarletteHTTPException)
async def _http_error(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith(SHARED_PLANES) or exc.status_code not in (404, 405):
        return await http_exception_handler(request, exc)
    if exc.status_code == 405:
        return _render(withings_data.wrong_action("Wrong action or wrong webservice: send a POST with form fields", 405))
    return _render(withings_data.wrong_action(http_status=404))


def known_query(request: Request):
    """Refuse a query parameter: a Withings action takes its parameters as form fields."""
    for name in request.query_params.keys():
        raise WithingsApiError(withings_data.invalid(
            f"{name} is not a query parameter; send action and its parameters as form fields in the POST body"))


STRICT = Depends(known_query)


@app.get("/health")
def health():
    return {"status": "ok"}


async def _form(request: Request):
    """The form fields of an application/x-www-form-urlencoded body, or the Withings error for anything else."""
    raw = await request.body()
    kind = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if raw.strip() and kind != "application/x-www-form-urlencoded":
        return withings_data.invalid("send action and its parameters as application/x-www-form-urlencoded form fields")
    try:
        fields = parse_qs(raw.decode("utf-8"), keep_blank_values=True, strict_parsing=bool(raw.strip()))
    except (UnicodeDecodeError, ValueError):
        return withings_data.invalid("the form body could not be parsed")
    repeated = sorted(k for k, v in fields.items() if len(v) > 1)
    if repeated:
        return withings_data.invalid(f"{', '.join(repeated)} is sent more than once")
    return {k: v[0] for k, v in fields.items()}


async def _serve(path: str, request: Request):
    params = await _form(request)
    if isinstance(params, WithingsError):
        return _render(params)
    result = withings_data.dispatch(path, request.state.oauth["account_id"], params)
    if isinstance(result, WithingsError):
        return _render(result)
    return result


@app.post("/measure", dependencies=[auth.require("user.metrics"), STRICT])
async def measure(request: Request):
    return await _serve("/measure", request)


@app.post("/v2/measure", dependencies=[auth.require("user.activity"), STRICT])
async def measure_v2(request: Request):
    return await _serve("/v2/measure", request)


@app.post("/v2/sleep", dependencies=[auth.require("user.activity"), STRICT])
async def sleep(request: Request):
    return await _serve("/v2/sleep", request)


@app.post("/v2/user", dependencies=[auth.require("user.info"), STRICT])
async def user(request: Request):
    return await _serve("/v2/user", request)
