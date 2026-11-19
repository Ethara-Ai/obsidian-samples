"""FastAPI server wrapping opentable_data as REST endpoints.

Mirrors the OpenTable partner platform for the five operations the connector
needs: search restaurants, check availability, create a reservation (lock an
available slot, then book it), get a reservation, and cancel one. Every
operation needs a bearer token from POST /oauth/token, and each one checks its
own scope, so looking at availability is not by itself permission to book.
OpenTable does not publish its partner error schema, so every error, request
validation failures included, uses this service's {status, code, message} body.
"""

from typing import Optional

from fastapi import FastAPI, Query, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

import opentable_data
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

V = "/v2"
auth = opentable_data.auth
OpenTableError = opentable_data.OpenTableError

app = FastAPI(title="OpenTable API (Mock)", version="v2")
install_tracker(app)
install_admin_plane(app, store=opentable_data._store)
auth.install(app)

SHARED_PLANES = ("/admin", "/audit")


def _render(error: OpenTableError) -> JSONResponse:
    return JSONResponse(status_code=error.status, content=error.body)


def _validation_error(exc: RequestValidationError) -> OpenTableError:
    err = exc.errors()[0]
    loc = [str(p) for p in (err.get("loc") or [])]
    field = ".".join(loc[1:])
    kind, ctx = err.get("type", ""), err.get("ctx") or {}
    if kind == "json_invalid":
        return opentable_data.invalid("The request body is not valid JSON")
    if kind == "missing":
        return opentable_data.invalid(f"{field} is required", field)
    if kind == "extra_forbidden":
        return opentable_data.invalid(f"{field} is not a recognized field", field)
    if kind in ("greater_than_equal", "less_than_equal", "greater_than", "less_than"):
        bound = next((f"{word} {ctx[key]}" for key, word in (("ge", "at least"), ("le", "at most"),
                                                              ("gt", "greater than"), ("lt", "less than"))
                      if key in ctx), "in range")
        return opentable_data.invalid(f"{field} must be {bound}", field)
    if kind.startswith("int"):
        return opentable_data.invalid(f"{field} must be an integer", field)
    if kind.startswith("bool"):
        return opentable_data.invalid(f"{field} must be true or false", field)
    if kind.startswith("string"):
        return opentable_data.invalid(f"{field} must be a string", field)
    return opentable_data.invalid(f"{field} is not valid", field)


@app.exception_handler(RequestValidationError)
async def _invalid_request(request: Request, exc: RequestValidationError):
    if request.url.path.startswith(SHARED_PLANES):
        return await request_validation_exception_handler(request, exc)
    return _render(_validation_error(exc))


@app.exception_handler(StarletteHTTPException)
async def _http_error(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith(SHARED_PLANES) or exc.status_code not in (404, 405):
        return await http_exception_handler(request, exc)
    code = "NOT_FOUND" if exc.status_code == 404 else "METHOD_NOT_ALLOWED"
    return _render(OpenTableError(exc.status_code, code, f"No route for {request.method} {request.url.path}"))


@app.get("/health")
def health():
    return {"status": "ok"}


def _reply(result, status_code=200):
    if isinstance(result, OpenTableError):
        return _render(result)
    if status_code != 200:
        return JSONResponse(status_code=status_code, content=result)
    return result


def _account(request: Request) -> str:
    return request.state.oauth["account_id"]


# --- search --------------------------------------------------------------------------------------

@app.get(V + "/directory/restaurants", dependencies=[auth.require("directory.read")])
def search_restaurants(
    term: Optional[str] = None,
    city: Optional[str] = None,
    cuisine: Optional[str] = None,
    price_band: Optional[int] = Query(None, ge=1, le=4),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    return opentable_data.search_restaurants(term=term, city=city, cuisine=cuisine, price_band=price_band,
                                             offset=offset, limit=limit)


# --- availability ----------------------------------------------------------------------------------

@app.get(V + "/availability/{rid}", dependencies=[auth.require("availability.read")])
def check_availability(
    rid: int,
    start_date_time: str,
    party_size: int = Query(..., ge=1),
    forward_minutes: int = Query(150, ge=0, le=opentable_data.MAX_WINDOW_MINUTES),
    backward_minutes: int = Query(30, ge=0, le=opentable_data.MAX_WINDOW_MINUTES),
    require_attributes: Optional[str] = None,
):
    return _reply(opentable_data.check_availability(rid, start_date_time, party_size,
                                                    forward_minutes=forward_minutes,
                                                    backward_minutes=backward_minutes,
                                                    require_attributes=require_attributes))


# --- booking --------------------------------------------------------------------------------------------

class SlotLockBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    party_size: int
    date_time: str
    slot_hash: str
    reservation_attribute: str = "default"


@app.post(V + "/booking/{rid}/slot_locks", status_code=201, dependencies=[auth.require("reservations.write")])
def create_slot_lock(rid: int, body: SlotLockBody, request: Request):
    return _reply(opentable_data.create_slot_lock(rid, _account(request), body.party_size, body.date_time,
                                                  body.slot_hash, body.reservation_attribute), status_code=201)


class ReservationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reservation_token: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email_address: Optional[str] = None
    phone_number: Optional[str] = None
    special_request: Optional[str] = None
    occasion: Optional[str] = None


@app.post(V + "/booking/{rid}/reservations", status_code=201, dependencies=[auth.require("reservations.write")])
def create_reservation(rid: int, body: ReservationBody, request: Request):
    return _reply(opentable_data.create_reservation(
        rid, _account(request), body.reservation_token, first_name=body.first_name, last_name=body.last_name,
        email_address=body.email_address, phone_number=body.phone_number, special_request=body.special_request,
        occasion=body.occasion), status_code=201)


@app.get(V + "/booking/{rid}/reservations/{confirmation_number}", dependencies=[auth.require("reservations.read")])
def get_reservation(rid: int, confirmation_number: str, request: Request):
    return _reply(opentable_data.get_reservation(rid, _account(request), confirmation_number))


@app.delete(V + "/booking/{rid}/reservations/{confirmation_number}",
            dependencies=[auth.require("reservations.write")])
def cancel_reservation(rid: int, confirmation_number: str, request: Request):
    return _reply(opentable_data.cancel_reservation(rid, _account(request), confirmation_number))
