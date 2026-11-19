"""Data access module for the Uber Rides API mock service.

Serves exactly the seven Uber operations the connector needs -- products at a
location, price estimate, time estimate, request a ride, ride status, cancel a
ride, ride history -- for the rider one connected account is. Products and
estimates are computed from the city each point falls in: distance is the
great-circle distance times a road factor, duration follows the city's average
speed, and a fare is the product's base, per-mile and per-minute rates plus the
booking fee, times the product's surge multiplier.

Requesting a surged product first answers 409 ``surge`` with a confirmation id,
as Uber does; resending the request with that ``surge_confirmation_id`` books
it. A ride is matched with a driver as soon as it is requested, so its status
starts at ``accepted``. Mock simplifications (also stated in
api_test_results.md): rides do not progress on their own (the admin plane moves
them), there are no shared products, places or payment methods, and history
items carry the trip fare, which the real API serves from a separate receipt
endpoint.
"""

import math
import secrets
import sys
import uuid
from pathlib import Path

DATA_DIR = Path(__file__).parent

sys.path.insert(0, str(DATA_DIR.parent))
import _mock_clock  # noqa: E402
from _mutable_store import get_store, read_seed_with_ctx, strict_float, strict_int  # noqa: E402
from _connector_auth import ConnectorAuth  # noqa: E402

_API = "uber-api"
_store = get_store(_API)

ROAD_FACTOR = 1.25
MAX_TRIP_MILES = 100
SAME_POINT_MILES = 0.05
SURGE_CONFIRMATION_TTL = 120
FREE_CANCEL_SECONDS = 120
ACTIVE = ("processing", "accepted", "arriving", "in_progress")
ENDED = ("completed", "rider_canceled", "driver_canceled", "no_drivers_available")


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _coerce_city_row(r):
    out = _strip_ctx(r)
    for key in ("latitude", "longitude", "radius_miles", "avg_speed_mph"):
        out[key] = strict_float(out, key)
    return out


def _coerce_product_row(r):
    out = _strip_ctx(r)
    for key in ("base", "minimum", "cost_per_minute", "cost_per_distance", "booking_fee", "cancellation_fee",
                "surge_multiplier"):
        out[key] = strict_float(out, key)
    out["capacity"] = strict_int(out, "capacity")
    out["eta_minutes"] = strict_int(out, "eta_minutes")
    return out


def _coerce_ride_row(r):
    out = _strip_ctx(r)
    for key in ("request_time", "start_time", "end_time"):
        out[key] = strict_int(out, key)
    for key in ("start_latitude", "start_longitude", "end_latitude", "end_longitude", "distance", "fare",
                "surge_multiplier"):
        out[key] = strict_float(out, key)
    out["driver_id"] = out.get("driver_id") or ""
    return out


_store.register("cities", primary_key="id",
                initial_loader=lambda: [_coerce_city_row(r) for r in _load("cities.json", "cities")],
                row_coercer=_coerce_city_row)
_store.register("products", primary_key="product_id",
                initial_loader=lambda: [_coerce_product_row(r) for r in _load("products.json", "products")],
                row_coercer=_coerce_product_row)
_store.register("drivers", primary_key="driver_id",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("drivers.json", "drivers")])
_store.register("rides", primary_key="request_id",
                initial_loader=lambda: [_coerce_ride_row(r) for r in _load("rides.json", "rides")],
                row_coercer=_coerce_ride_row)
_store.register("riders", primary_key="id",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("riders.json", "riders")])
_store.register("surge_confirmations", primary_key="surge_confirmation_id", initial_loader=lambda: [])

auth = ConnectorAuth(_API, store=_store, data_dir=DATA_DIR)


class UberError:
    """An Uber error body and the HTTP status it is served with."""

    def __init__(self, status, code, message, fields=None, body=None):
        self.status = status
        self.body = body if body is not None else {"message": message, "code": code}
        if fields:
            self.body["fields"] = fields


def validation_failed(fields):
    return UberError(422, "validation_failed", "Invalid request.", fields=fields)


def _now():
    return int(_mock_clock.time())


def _miles(lat1, lon1, lat2, lon2):
    p1, l1, p2, l2 = map(math.radians, (lat1, lon1, lat2, lon2))
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin((l2 - l1) / 2) ** 2
    return 2 * 3958.8 * math.asin(math.sqrt(h))


def _city_at(lat, lng):
    best = None
    for city in _store.table("cities").rows():
        d = _miles(lat, lng, city["latitude"], city["longitude"])
        if d <= city["radius_miles"] and (best is None or d < best[0]):
            best = (d, city)
    return best[1] if best else None


def _products(city):
    return sorted(_store.table("products").find(lambda p: p["city_id"] == city["id"]),
                  key=lambda p: (p["eta_minutes"], p["display_name"]))


def _trip(city, lat1, lng1, lat2, lng2):
    distance = round(_miles(lat1, lng1, lat2, lng2) * ROAD_FACTOR, 2)
    seconds = int(distance / city["avg_speed_mph"] * 3600) + 240
    return distance, seconds


def _fare(product, distance, seconds, surge):
    raw = product["base"] + product["cost_per_distance"] * distance + product["cost_per_minute"] * seconds / 60
    return max(product["minimum"], raw) * surge + product["booking_fee"]


def _eta_seconds(product, city, lat, lng):
    return product["eta_minutes"] * 60 + int(_miles(lat, lng, city["latitude"], city["longitude"]) * 25)


def _product_view(p):
    return {
        "product_id": p["product_id"], "display_name": p["display_name"], "description": p["description"],
        "short_description": p["short_description"], "capacity": p["capacity"], "image": p["image"],
        "shared": bool(p["shared"]), "upfront_fare_enabled": bool(p["upfront_fare_enabled"]),
        "cash_enabled": bool(p["cash_enabled"]), "product_group": p["product_group"],
        "price_details": {
            "base": p["base"], "minimum": p["minimum"], "cost_per_minute": p["cost_per_minute"],
            "cost_per_distance": p["cost_per_distance"], "distance_unit": "mile",
            "cancellation_fee": p["cancellation_fee"], "currency_code": "USD",
            "service_fees": [{"name": "Booking fee", "fee": p["booking_fee"]}],
        },
    }


# --- products and estimates ----------------------------------------------------------------

def list_products(lat, lng):
    city = _city_at(lat, lng)
    return {"products": [_product_view(p) for p in _products(city)] if city else []}


def price_estimates(lat1, lng1, lat2, lng2):
    city = _city_at(lat1, lng1)
    if city is None:
        return {"prices": []}
    distance, seconds = _trip(city, lat1, lng1, lat2, lng2)
    if distance > MAX_TRIP_MILES:
        return UberError(422, "distance_exceeded", f"Distance between two points exceeds {MAX_TRIP_MILES} miles.")
    prices = []
    for p in _products(city):
        fare = _fare(p, distance, seconds, p["surge_multiplier"])
        low, high = int(round(fare * 0.92)), int(math.ceil(fare * 1.18))
        prices.append({"product_id": p["product_id"], "display_name": p["display_name"],
                       "localized_display_name": p["display_name"], "currency_code": "USD",
                       "estimate": f"${low}-{high}" if high > low else f"${low}", "low_estimate": low,
                       "high_estimate": high, "duration": seconds, "distance": distance,
                       "surge_multiplier": p["surge_multiplier"]})
    return {"prices": prices}


def time_estimates(lat, lng, product_id=None):
    city = _city_at(lat, lng)
    if city is None:
        return {"times": []}
    products = _products(city)
    if product_id is not None:
        products = [p for p in products if p["product_id"] == product_id]
    return {"times": [{"product_id": p["product_id"], "display_name": p["display_name"],
                       "localized_display_name": p["display_name"], "estimate": _eta_seconds(p, city, lat, lng)}
                      for p in products]}


# --- rides ------------------------------------------------------------------------------------

def _driver_free(driver_id):
    return _store.table("rides").find_one(lambda r: r["driver_id"] == driver_id and r["status"] in ACTIVE) is None


def _ride_view(ride):
    product = _store.table("products").get(ride["product_id"]) or {}
    driver = _store.table("drivers").get(ride["driver_id"]) if ride["driver_id"] else None
    view = {"request_id": ride["request_id"], "product_id": ride["product_id"], "status": ride["status"],
            "surge_multiplier": ride["surge_multiplier"], "shared": False,
            "driver": None, "vehicle": None, "location": None,
            "pickup": {"latitude": ride["start_latitude"], "longitude": ride["start_longitude"]},
            "destination": {"latitude": ride["end_latitude"], "longitude": ride["end_longitude"]}}
    if driver:
        view["driver"] = {"phone_number": driver["phone_number"], "sms_number": driver["sms_number"],
                          "rating": driver["rating"], "picture_url": driver["picture_url"], "name": driver["name"]}
        view["vehicle"] = {"make": driver["vehicle_make"], "model": driver["vehicle_model"],
                           "license_plate": driver["license_plate"], "picture_url": driver["vehicle_picture_url"]}
    if ride["status"] in ACTIVE:
        city = _store.table("cities").get(ride["city_id"])
        eta = max(1, round(_eta_seconds(product, city, ride["start_latitude"], ride["start_longitude"]) / 60)) \
            if product and city else None
        if eta is not None:
            offset = eta * 0.004
            view["location"] = {"latitude": round(ride["start_latitude"] + offset, 6),
                                "longitude": round(ride["start_longitude"] - offset, 6), "bearing": 180}
            view["pickup"]["eta"] = eta
            view["destination"]["eta"] = eta + max(1, round((ride["end_time"] - ride["start_time"]) / 60))
    return view


def _rider_ride(request_id, account_id):
    if request_id == "current":
        ride = _store.table("rides").find_one(lambda r: r["rider_account_id"] == account_id and r["status"] in ACTIVE)
        if ride is None:
            return UberError(404, "no_current_trip", "User is not currently on a trip.")
        return ride
    ride = _store.table("rides").get(request_id)
    if ride is None or ride["rider_account_id"] != account_id:
        return UberError(404, "not_found", f"Request {request_id} was not found.")
    return ride


def get_ride(request_id, account_id):
    ride = _rider_ride(request_id, account_id)
    if isinstance(ride, UberError):
        return ride
    return _ride_view(ride)


def request_ride(account_id, product_id, lat1, lng1, lat2, lng2, surge_confirmation_id=None):
    product = _store.table("products").get(product_id)
    if product is None:
        return UberError(404, "no_product_found", f"No product found for product_id {product_id}.")
    city = _store.table("cities").get(product["city_id"])
    if _city_at(lat1, lng1) is None or _city_at(lat1, lng1)["id"] != city["id"]:
        return UberError(422, "outside_service_area",
                         f"The pickup location is outside the {product['display_name']} service area in "
                         f"{city['display_name']}.")
    distance, seconds = _trip(city, lat1, lng1, lat2, lng2)
    if distance / ROAD_FACTOR < SAME_POINT_MILES:
        return UberError(422, "same_pickup_dropoff", "Pickup and dropoff can't be the same.")
    if distance > MAX_TRIP_MILES:
        return UberError(422, "distance_exceeded", f"Distance between two points exceeds {MAX_TRIP_MILES} miles.")
    if _store.table("rides").find_one(lambda r: r["rider_account_id"] == account_id and r["status"] in ACTIVE):
        return UberError(409, "current_trip_exists", "User is already on an active trip.")
    surge = product["surge_multiplier"]
    if surge > 1.0:
        confirmation = _store.table("surge_confirmations").get(surge_confirmation_id or "")
        valid = (confirmation is not None and confirmation["product_id"] == product_id
                 and confirmation["account_id"] == account_id and not confirmation["used"]
                 and confirmation["expires_at"] > _now())
        if not valid:
            confirmation_id = "sc_" + secrets.token_hex(10)
            expires = _now() + SURGE_CONFIRMATION_TTL
            _store.table("surge_confirmations").upsert({"surge_confirmation_id": confirmation_id,
                                                        "product_id": product_id, "account_id": account_id,
                                                        "multiplier": surge, "expires_at": expires, "used": False})
            return UberError(409, "surge", "", body={
                "meta": {"surge_confirmation": {
                    "href": f"https://api.uber.com/v1.2/surge-confirmations/{confirmation_id}",
                    "expires_at": expires, "multiplier": surge, "surge_confirmation_id": confirmation_id}},
                "errors": [{"status": 409, "code": "surge",
                            "title": "Surge pricing is currently in effect for this product."}]})
        _store.table("surge_confirmations").patch(surge_confirmation_id, {"used": True})
    driver = next((d for d in _store.table("drivers").find(
        lambda d: d["city_id"] == city["id"] and d["product_group"] == product["product_group"])
        if _driver_free(d["driver_id"])), None)
    if driver is None:
        return UberError(409, "no_drivers_available", "No drivers are available right now. Please try again.")
    now = _now()
    eta = _eta_seconds(product, city, lat1, lng1)
    ride = {"request_id": str(uuid.uuid4()), "rider_account_id": account_id, "product_id": product_id,
            "city_id": city["id"], "status": "accepted", "request_time": now, "start_time": now + eta,
            "end_time": now + eta + seconds, "start_latitude": lat1, "start_longitude": lng1,
            "end_latitude": lat2, "end_longitude": lng2, "distance": distance,
            "fare": round(_fare(product, distance, seconds, surge), 2), "currency_code": "USD",
            "surge_multiplier": surge, "driver_id": driver["driver_id"]}
    _store.table("rides").upsert(ride)
    return _ride_view(ride)


def cancel_ride(request_id, account_id):
    ride = _rider_ride(request_id, account_id)
    if isinstance(ride, UberError):
        return ride
    if ride["status"] not in ACTIVE:
        return UberError(409, "trip_not_active", f"Request {ride['request_id']} is {ride['status']} and can no "
                                                 "longer be canceled.")
    now = _now()
    product = _store.table("products").get(ride["product_id"]) or {}
    fee = product.get("cancellation_fee", 0.0) if now - ride["request_time"] > FREE_CANCEL_SECONDS else 0.0
    _store.table("rides").patch(ride["request_id"], {"status": "rider_canceled", "start_time": now,
                                                     "end_time": now, "distance": 0.0, "fare": fee})
    return None


def history(account_id, offset=0, limit=5):
    rows = sorted(_store.table("rides").find(lambda r: r["rider_account_id"] == account_id and r["status"] in ENDED),
                  key=lambda r: r["request_time"], reverse=True)
    items = []
    for r in rows[offset:offset + limit]:
        city = _store.table("cities").get(r["city_id"]) or {}
        items.append({"status": r["status"], "distance": r["distance"], "product_id": r["product_id"],
                      "start_time": r["start_time"], "end_time": r["end_time"], "request_id": r["request_id"],
                      "request_time": r["request_time"],
                      "start_city": {"latitude": city.get("latitude"), "display_name": city.get("display_name"),
                                     "longitude": city.get("longitude")},
                      "fare": {"value": r["fare"], "currency_code": r["currency_code"],
                               "display": f"${r['fare']:,.2f}"}})
    return {"count": len(rows), "history": items, "limit": limit, "offset": offset}


_store.eager_load()
