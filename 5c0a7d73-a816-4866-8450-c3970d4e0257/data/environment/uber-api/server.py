"""FastAPI server wrapping uber_data as REST endpoints.

Mirrors the Uber Rides API (api.uber.com/v1.2) for the seven operations the
connector needs: products at a location, price estimate, time estimate, request
a ride, ride status, cancel a ride, and ride history. ``current`` works as a
request id on the status and cancel routes, as it does on Uber. Every operation
needs a bearer token from POST /oauth/token, and each one checks its own scope,
so seeing prices is not by itself permission to book a car. Errors use Uber's
{message, code} body, and request validation failures its 422
``validation_failed`` body with one entry per field.
"""

from typing import Optional

from fastapi import FastAPI, Query, Request, Response
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

import uber_data
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

V = "/v1.2"
auth = uber_data.auth
UberError = uber_data.UberError

app = FastAPI(title="Uber Rides API (Mock)", version="v1.2")
install_tracker(app)
install_admin_plane(app, store=uber_data._store)
auth.install(app)

SHARED_PLANES = ("/admin", "/audit")
LAT = {"ge": -90, "le": 90}
LNG = {"ge": -180, "le": 180}


def _render(error: UberError) -> JSONResponse:
    return JSONResponse(status_code=error.status, content=error.body)


def _field_message(err) -> str:
    kind, ctx = err.get("type", ""), err.get("ctx") or {}
    if kind == "missing":
        return "Required"
    if kind == "extra_forbidden":
        return "Unknown field."
    if kind in ("greater_than_equal", "less_than_equal"):
        name = str((err.get("loc") or [""])[-1])
        low, high = (-90.0, 90.0) if "latitude" in name else (-180.0, 180.0) if "longitude" in name else (
            ctx.get("ge"), ctx.get("le"))
        if "latitude" in name or "longitude" in name:
            return f"Must be between {low} and {high}."
        return f"Must be at least {ctx['ge']}." if "ge" in ctx else f"Must be at most {ctx['le']}."
    if kind.startswith(("float", "int")):
        return "Not a valid number."
    if kind.startswith("string"):
        return "Not a valid string."
    return "Invalid value."


@app.exception_handler(RequestValidationError)
async def _invalid_request(request: Request, exc: RequestValidationError):
    if request.url.path.startswith(SHARED_PLANES):
        return await request_validation_exception_handler(request, exc)
    errors = exc.errors()
    if errors and errors[0].get("type") == "json_invalid":
        return _render(UberError(400, "invalid_json", "The request body is not valid JSON."))
    fields = {}
    for err in errors:
        name = ".".join(str(p) for p in (err.get("loc") or [])[1:]) or "body"
        fields.setdefault(name, _field_message(err))
    return _render(uber_data.validation_failed(fields))


@app.exception_handler(StarletteHTTPException)
async def _http_error(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith(SHARED_PLANES) or exc.status_code not in (404, 405):
        return await http_exception_handler(request, exc)
    if exc.status_code == 405:
        return _render(UberError(405, "method_not_allowed", f"{request.method} is not allowed on {request.url.path}."))
    return _render(UberError(404, "not_found", f"The resource {request.url.path} was not found."))


@app.get("/health")
def health():
    return {"status": "ok"}


def _reply(result, status_code=200):
    if isinstance(result, UberError):
        return _render(result)
    if status_code != 200:
        return JSONResponse(status_code=status_code, content=result)
    return result


def _account(request: Request) -> str:
    return request.state.oauth["account_id"]


# --- products and estimates ---------------------------------------------------------------------

@app.get(V + "/products", dependencies=[auth.require("ride_request.estimate")])
def list_products(latitude: float = Query(..., **LAT), longitude: float = Query(..., **LNG)):
    return _reply(uber_data.list_products(latitude, longitude))


@app.get(V + "/estimates/price", dependencies=[auth.require("ride_request.estimate")])
def price_estimates(
    start_latitude: float = Query(..., **LAT),
    start_longitude: float = Query(..., **LNG),
    end_latitude: float = Query(..., **LAT),
    end_longitude: float = Query(..., **LNG),
):
    return _reply(uber_data.price_estimates(start_latitude, start_longitude, end_latitude, end_longitude))


@app.get(V + "/estimates/time", dependencies=[auth.require("ride_request.estimate")])
def time_estimates(
    start_latitude: float = Query(..., **LAT),
    start_longitude: float = Query(..., **LNG),
    product_id: Optional[str] = None,
):
    return _reply(uber_data.time_estimates(start_latitude, start_longitude, product_id=product_id))


# --- rides ---------------------------------------------------------------------------------------------

class RideRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str
    start_latitude: float = Field(..., **LAT)
    start_longitude: float = Field(..., **LNG)
    end_latitude: float = Field(..., **LAT)
    end_longitude: float = Field(..., **LNG)
    surge_confirmation_id: Optional[str] = None


@app.post(V + "/requests", status_code=202, dependencies=[auth.require("request")])
def request_ride(body: RideRequestBody, request: Request):
    return _reply(uber_data.request_ride(_account(request), body.product_id, body.start_latitude,
                                         body.start_longitude, body.end_latitude, body.end_longitude,
                                         surge_confirmation_id=body.surge_confirmation_id), status_code=202)


@app.get(V + "/requests/{request_id}", dependencies=[auth.require("all_trips")])
def get_ride(request_id: str, request: Request):
    return _reply(uber_data.get_ride(request_id, _account(request)))


@app.delete(V + "/requests/{request_id}", status_code=204, dependencies=[auth.require("request")])
def cancel_ride(request_id: str, request: Request):
    result = uber_data.cancel_ride(request_id, _account(request))
    if isinstance(result, UberError):
        return _render(result)
    return Response(status_code=204)


# --- history --------------------------------------------------------------------------------------------

@app.get(V + "/history", dependencies=[auth.require("history")])
def ride_history(request: Request, offset: int = Query(0, ge=0), limit: int = Query(5, ge=1, le=50)):
    return _reply(uber_data.history(_account(request), offset=offset, limit=limit))
