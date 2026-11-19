"""FastAPI server wrapping duffel_data as REST endpoints.

Mirrors the Duffel API (api.duffel.com, version v2) for the nine connector
operations the client lists. Every operation needs a bearer token from
POST /oauth/token, and each one checks its own scope, so a connected account is
not by itself permission to book or cancel.
"""

from typing import List, Literal, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

import duffel_data
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

auth = duffel_data.auth

app = FastAPI(title="Duffel API (Mock)", version="v2")
install_tracker(app)
install_admin_plane(app, store=duffel_data._store)
auth.install(app)


@app.get("/health")
def health():
    return {"status": "ok"}


def _reply(result, status_code=200):
    if isinstance(result, duffel_data.DuffelError):
        return JSONResponse(status_code=result.status, content=result.body)
    if status_code != 200:
        return JSONResponse(status_code=status_code, content=result)
    return result


def _account(request: Request) -> str:
    return request.state.oauth["account_id"]


# --- .search ---------------------------------------------------------------------------

class SliceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin: str
    destination: str
    departure_date: str


class PassengerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Optional[Literal["adult", "child", "infant_without_seat"]] = None
    age: Optional[int] = None


class OfferRequestData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slices: List[SliceIn] = Field(min_length=1, max_length=4)
    passengers: List[PassengerIn] = Field(min_length=1)
    cabin_class: Optional[Literal["economy", "premium_economy", "business", "first"]] = None


class OfferRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: OfferRequestData


@app.post("/air/offer_requests", status_code=201, dependencies=[auth.require("air.offers.read")])
def create_offer_request(body: OfferRequestBody, request: Request):
    d = body.data
    return _reply(duffel_data.create_offer_request(
        _account(request), [s.model_dump() for s in d.slices],
        [p.model_dump() for p in d.passengers], cabin_class=d.cabin_class), status_code=201)


# --- .seat-options -----------------------------------------------------------------------

@app.get("/air/seat_maps", dependencies=[auth.require("air.offers.read")])
def get_seat_maps(offer_id: str, request: Request):
    return _reply(duffel_data.get_seat_maps(offer_id, _account(request)))


# --- .validate-booking ---------------------------------------------------------------------

@app.get("/air/offers/{offer_id}", dependencies=[auth.require("air.offers.read")])
def get_offer(offer_id: str, request: Request):
    return _reply(duffel_data.get_offer(offer_id, _account(request)))


# --- .book -------------------------------------------------------------------------------------

class OrderPassengerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: Literal["mr", "ms", "mrs", "miss", "dr"]
    given_name: str
    family_name: str
    born_on: str
    gender: Literal["m", "f"]
    email: str
    phone_number: str


class PaymentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["balance"]
    amount: str
    currency: str


class ServiceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    quantity: int = 1


class OrderData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_offers: List[str] = Field(min_length=1)
    passengers: List[OrderPassengerIn] = Field(min_length=1)
    payments: List[PaymentIn] = Field(min_length=1)
    services: Optional[List[ServiceIn]] = None


class OrderBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: OrderData


@app.post("/air/orders", status_code=201, dependencies=[auth.require("air.orders.write")])
def create_order(body: OrderBody, request: Request):
    d = body.data
    return _reply(duffel_data.create_order(
        _account(request), d.selected_offers, [p.model_dump() for p in d.passengers],
        [p.model_dump() for p in d.payments],
        services=[s.model_dump() for s in d.services] if d.services is not None else None),
        status_code=201)


# --- .booking-status ------------------------------------------------------------------------------

@app.get("/air/orders/{order_id}", dependencies=[auth.require("air.orders.read")])
def get_order(order_id: str, request: Request):
    return _reply(duffel_data.get_order(order_id, _account(request)))


# --- .cancellation-quote / .cancel-booking ---------------------------------------------------------

class CancellationData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str


class CancellationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: CancellationData


@app.post("/air/order_cancellations", status_code=201, dependencies=[auth.require("air.orders.cancel")])
def create_order_cancellation(body: CancellationBody, request: Request):
    return _reply(duffel_data.quote_cancellation(_account(request), body.data.order_id), status_code=201)


@app.post("/air/order_cancellations/{cancellation_id}/actions/confirm",
          dependencies=[auth.require("air.orders.cancel")])
def confirm_order_cancellation(cancellation_id: str, request: Request):
    return _reply(duffel_data.confirm_cancellation(_account(request), cancellation_id))


# --- .stays-search / .stays-fetch-rates ---------------------------------------------------------------

class CoordinatesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latitude: float
    longitude: float


class LocationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    radius: float
    geographic_coordinates: CoordinatesIn


class GuestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["adult", "child"]
    age: Optional[int] = None


class StaySearchData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location: LocationIn
    check_in_date: str
    check_out_date: str
    rooms: int = 1
    guests: List[GuestIn] = Field(min_length=1)


class StaySearchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: StaySearchData


@app.post("/stays/search", dependencies=[auth.require("stays.read")])
def search_stays(body: StaySearchBody, request: Request):
    d = body.data
    c = d.location.geographic_coordinates
    return _reply(duffel_data.search_stays(
        _account(request), c.latitude, c.longitude, d.location.radius, d.check_in_date,
        d.check_out_date, d.rooms, [g.model_dump() for g in d.guests]))


@app.post("/stays/search_results/{search_result_id}/actions/fetch_all_rates",
          dependencies=[auth.require("stays.read")])
def fetch_all_rates(search_result_id: str, request: Request):
    return _reply(duffel_data.fetch_all_rates(_account(request), search_result_id))
