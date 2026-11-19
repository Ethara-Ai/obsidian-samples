"""Data access module for the OpenTable mock service.

Serves exactly the five OpenTable operations the connector needs -- search
restaurants, check availability for a restaurant, date, time and party size,
create a reservation, get a reservation, cancel a reservation -- for the diner
one connected account is. The routes follow OpenTable's partner platform:
availability at /v2/availability/{rid}, and a reservation booked in two steps,
a slot lock on an available time, then the reservation that consumes it.

Availability is computed, not stored. Each restaurant releases a number of
tables per seating area and table size to online booking, a party is seated at
a table that seats it with at most two empty chairs, a table stays occupied for
the party's turn time (90 to 150 minutes), and every confirmed reservation and
live slot lock holds one table. OpenTable does not publish its partner JSON
schemas or error body, so the field names and the error body here are this
service's own, stated in api_test_results.md.
"""

import hashlib
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent

sys.path.insert(0, str(DATA_DIR.parent))
import _mock_clock  # noqa: E402
from _mutable_store import get_store, read_seed_with_ctx, strict_float, strict_int  # noqa: E402
from _connector_auth import ConnectorAuth  # noqa: E402

_API = "opentable-api"
_store = get_store(_API)

DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
PRICE_RANGES = {1: "$15 and under", 2: "$30 and under", 3: "$31 to $50", 4: "$50 and over"}
OCCASIONS = ("birthday", "anniversary", "date_night", "business_meal", "celebration")
LOCK_TTL = timedelta(minutes=10)
MAX_WINDOW_MINUTES = 240
REQUEST_LIMIT = 500


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _coerce_restaurant_row(r):
    out = _strip_ctx(r)
    for key in ("rid", "price_band", "reviews_count", "max_online_party_size", "slot_interval_minutes"):
        out[key] = strict_int(out, key)
    for key in ("latitude", "longitude", "rating"):
        out[key] = strict_float(out, key)
    return out


def _coerce_reservation_row(r):
    out = _strip_ctx(r)
    for key in ("rid", "party_size", "table_size"):
        out[key] = strict_int(out, key)
    out["confirmation_number"] = str(out["confirmation_number"])
    for key in ("diner_account_id", "special_request", "occasion", "cancelled_at"):
        out[key] = out.get(key) or ""
    return out


_store.register("restaurants", primary_key="rid",
                initial_loader=lambda: [_coerce_restaurant_row(r) for r in _load("restaurants.json", "restaurants")],
                row_coercer=_coerce_restaurant_row)
_store.register("reservations", primary_key="confirmation_number",
                initial_loader=lambda: [_coerce_reservation_row(r)
                                        for r in _load("reservations.json", "reservations")],
                row_coercer=_coerce_reservation_row)
_store.register("diners", primary_key="id",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("diners.json", "diners")])
_store.register("slot_locks", primary_key="reservation_token", initial_loader=lambda: [])

auth = ConnectorAuth(_API, store=_store, data_dir=DATA_DIR)


class OpenTableError:
    """This service's error body ({status, code, message}) and the HTTP status it is served with."""

    def __init__(self, status, code, message, field=None):
        self.status = status
        self.body = {"status": status, "code": code, "message": message}
        if field:
            self.body["field"] = field


def invalid(message, field=None):
    return OpenTableError(400, "INVALID_PARAMETER", message, field)


def _no_restaurant(rid):
    return OpenTableError(404, "RESTAURANT_NOT_FOUND", f"No restaurant with rid {rid} is available for online booking.")


def _no_reservation(rid, number):
    return OpenTableError(404, "RESERVATION_NOT_FOUND",
                          f"No reservation {number} at restaurant {rid} belongs to this diner.")


def _now():
    return _mock_clock.now(timezone.utc)


def _iso_utc(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_local(text, field):
    try:
        moment = datetime.strptime(text, "%Y-%m-%dT%H:%M")
    except (TypeError, ValueError):
        try:
            moment = datetime.strptime(text, "%Y-%m-%dT%H:%M:%S")
        except (TypeError, ValueError):
            return invalid(f"{field} must be a local date and time such as 2026-10-16T19:00", field)
    return moment.replace(second=0)


def _local(moment):
    return moment.strftime("%Y-%m-%dT%H:%M")


def _restaurant(rid):
    return _store.table("restaurants").get(rid)


def _turn(party):
    return timedelta(minutes=90 if party <= 2 else 105 if party <= 4 else 120 if party <= 6 else 150)


def slot_hash(rid, when, party):
    digest = hashlib.sha1(f"{rid}|{when}|{party}".encode()).hexdigest()
    return str(int(digest, 16) % 10**10).zfill(10)


def _clock(text):
    hour, minute = (int(x) for x in text.split(":"))
    return hour, minute


def _label(text):
    hour, minute = _clock(text)
    return f"{(hour - 1) % 12 + 1}:{minute:02d} {'AM' if hour < 12 else 'PM'}"


def _restaurant_view(r):
    return {
        "rid": r["rid"], "name": r["name"],
        "address": {"line1": r["street"], "city": r["city"], "state": r["state"], "postal_code": r["postal_code"],
                    "country": r["country"]},
        "neighborhood": r["neighborhood"], "cuisine": r["cuisine"], "cuisines": list(r["cuisines"]),
        "price_band": r["price_band"], "price_range": PRICE_RANGES.get(r["price_band"], ""),
        "dining_style": r["dining_style"], "dress_code": r["dress_code"], "phone": r["phone"],
        "latitude": r["latitude"], "longitude": r["longitude"], "rating": r["rating"],
        "reviews_count": r["reviews_count"], "max_online_party_size": r["max_online_party_size"],
        "seating_options": sorted(r["tables"]),
        "hours": {day: [f"{_label(a)} - {_label(b)}" for a, b in r["hours"].get(day, [])] for day in DAYS},
        "cancellation_policy": r["cancellation_policy"],
        "profile_url": f"https://www.opentable.com/restaurant/profile/{r['rid']}",
    }


def _reservation_view(row, restaurant):
    return {
        "confirmation_number": row["confirmation_number"], "rid": row["rid"],
        "restaurant_name": restaurant["name"] if restaurant else "", "status": row["status"],
        "date_time": row["date_time"], "party_size": row["party_size"], "seating": row["seating"],
        "diner": {k: row[k] for k in ("first_name", "last_name", "email_address", "phone_number")},
        "special_request": row["special_request"], "occasion": row["occasion"] or None,
        "created_at": row["created_at"], "cancelled_at": row["cancelled_at"] or None,
        "manage_url": f"https://www.opentable.com/book/view?rid={row['rid']}&confnumber={row['confirmation_number']}",
    }


# --- search ---------------------------------------------------------------------------------

def search_restaurants(term=None, city=None, cuisine=None, price_band=None, offset=0, limit=20):
    rows = _store.table("restaurants").rows()
    if term:
        needle = term.lower()
        rows = [r for r in rows if needle in r["name"].lower() or needle in r["neighborhood"].lower()
                or any(needle in c.lower() for c in r["cuisines"])]
    if city:
        rows = [r for r in rows if r["city"].lower() == city.lower()]
    if cuisine:
        rows = [r for r in rows if cuisine.lower() in (c.lower() for c in r["cuisines"])]
    if price_band is not None:
        rows = [r for r in rows if r["price_band"] == price_band]
    rows.sort(key=lambda r: (r["name"].lower(), r["rid"]))
    return {"total_count": len(rows), "offset": offset, "limit": limit,
            "restaurants": [_restaurant_view(r) for r in rows[offset:offset + limit]]}


# --- availability ------------------------------------------------------------------------------

def _holds(rid, seating, size):
    """(start, end) of every table of ``size`` in ``seating`` that a reservation or a live lock holds."""
    out = []
    for row in _store.table("reservations").find(lambda x: x["rid"] == rid and x["seating"] == seating
                                                 and x["table_size"] == size and x["status"] != "Cancelled"):
        start = datetime.strptime(row["date_time"], "%Y-%m-%dT%H:%M")
        out.append((start, start + _turn(row["party_size"])))
    now = _now()
    for lock in _store.table("slot_locks").find(lambda x: x["rid"] == rid and x["seating"] == seating
                                                and x["table_size"] == size and not x["used"]):
        if datetime.strptime(lock["expires_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) > now:
            start = datetime.strptime(lock["date_time"], "%Y-%m-%dT%H:%M")
            out.append((start, start + _turn(lock["party_size"])))
    return out


def _free_table(restaurant, seating, when, party):
    """The table size a party can take at ``when`` in ``seating``, or None when every fitting table is held."""
    tables = restaurant["tables"].get(seating) or {}
    end = when + _turn(party)
    for size in sorted(int(s) for s in tables):
        if not party <= size <= party + 2:
            continue
        held = sum(1 for a, b in _holds(restaurant["rid"], seating, size) if a < end and when < b)
        if held < int(tables[str(size)]):
            return size
    return None


def _open_slots(restaurant, day):
    step = timedelta(minutes=restaurant["slot_interval_minutes"])
    for first, last in restaurant["hours"].get(DAYS[day.weekday()], []):
        moment = datetime.combine(day, datetime.min.time()).replace(hour=_clock(first)[0], minute=_clock(first)[1])
        end = moment.replace(hour=_clock(last)[0], minute=_clock(last)[1])
        while moment <= end:
            yield moment
            moment += step


def check_availability(rid, start_date_time, party_size, forward_minutes=150, backward_minutes=30,
                       require_attributes=None):
    restaurant = _restaurant(rid)
    if restaurant is None:
        return _no_restaurant(rid)
    start = _parse_local(start_date_time, "start_date_time")
    if isinstance(start, OpenTableError):
        return start
    if party_size > restaurant["max_online_party_size"]:
        return OpenTableError(400, "PARTY_SIZE_NOT_SUPPORTED",
                              f"Online booking at {restaurant['name']} takes parties of up to "
                              f"{restaurant['max_online_party_size']}; call {restaurant['phone']} for larger groups.",
                              "party_size")
    wanted = [a.strip() for a in (require_attributes or "").split(",") if a.strip()]
    unknown = [a for a in wanted if a not in restaurant["tables"]]
    if unknown:
        return invalid(f"require_attributes {', '.join(unknown)} is not offered at {restaurant['name']}; it offers "
                       f"{', '.join(sorted(restaurant['tables']))}", "require_attributes")
    seatings = wanted or sorted(restaurant["tables"])
    low, high = start - timedelta(minutes=backward_minutes), start + timedelta(minutes=forward_minutes)
    times = []
    days = sorted({low.date(), high.date()})
    for day in days:
        for moment in _open_slots(restaurant, day):
            if not low <= moment <= high:
                continue
            open_here = [s for s in seatings if _free_table(restaurant, s, moment, party_size) is not None]
            if open_here:
                when = _local(moment)
                times.append({"date_time": when, "time_offset_minutes": int((moment - start).total_seconds() // 60),
                              "attributes": open_here, "slot_hash": slot_hash(rid, when, party_size)})
    return {"rid": rid, "restaurant_name": restaurant["name"], "date_time": _local(start), "party_size": party_size,
            "times_available": times}


# --- booking: slot lock, then reservation ----------------------------------------------------------

def create_slot_lock(rid, account_id, party_size, date_time, hash_value, attribute="default"):
    restaurant = _restaurant(rid)
    if restaurant is None:
        return _no_restaurant(rid)
    moment = _parse_local(date_time, "date_time")
    if isinstance(moment, OpenTableError):
        return moment
    when = _local(moment)
    if party_size > restaurant["max_online_party_size"]:
        return OpenTableError(400, "PARTY_SIZE_NOT_SUPPORTED",
                              f"Online booking at {restaurant['name']} takes parties of up to "
                              f"{restaurant['max_online_party_size']}.", "party_size")
    if hash_value != slot_hash(rid, when, party_size):
        return invalid("slot_hash does not match this restaurant, date_time and party_size; take it from the "
                       "availability response", "slot_hash")
    if attribute not in restaurant["tables"]:
        return invalid(f"reservation_attribute {attribute} is not offered at {restaurant['name']}",
                       "reservation_attribute")
    if moment not in set(_open_slots(restaurant, moment.date())):
        return OpenTableError(409, "SLOT_UNAVAILABLE", f"{when} is not a bookable time at {restaurant['name']}.")
    size = _free_table(restaurant, attribute, moment, party_size)
    if size is None:
        return OpenTableError(409, "SLOT_UNAVAILABLE",
                              f"{when} for {party_size} ({attribute}) is no longer available at {restaurant['name']}.")
    lock = {"reservation_token": "ot_lock_" + secrets.token_urlsafe(18), "rid": rid, "account_id": account_id,
            "date_time": when, "party_size": party_size, "seating": attribute, "table_size": size,
            "expires_at": _iso_utc(_now() + LOCK_TTL), "used": False}
    _store.table("slot_locks").upsert(lock)
    return {"reservation_token": lock["reservation_token"], "expires_at": lock["expires_at"], "rid": rid,
            "date_time": when, "party_size": party_size, "reservation_attribute": attribute}


def _conflict(account_id, when, party):
    start = datetime.strptime(when, "%Y-%m-%dT%H:%M")
    for row in _store.table("reservations").find(lambda x: x["diner_account_id"] == account_id
                                                 and x["status"] == "Confirmed"):
        other = datetime.strptime(row["date_time"], "%Y-%m-%dT%H:%M")
        if abs(other - start) < max(_turn(party), _turn(row["party_size"])):
            return row
    return None


def create_reservation(rid, account_id, token, first_name=None, last_name=None, email_address=None,
                       phone_number=None, special_request=None, occasion=None):
    restaurant = _restaurant(rid)
    if restaurant is None:
        return _no_restaurant(rid)
    lock = _store.table("slot_locks").get(token)
    if lock is None or lock["rid"] != rid or lock["account_id"] != account_id:
        return invalid("reservation_token is not a slot lock for this restaurant; create one with "
                       f"POST /v2/booking/{rid}/slot_locks", "reservation_token")
    if lock["used"]:
        return OpenTableError(409, "SLOT_LOCK_USED", "This slot lock was already used for a reservation.")
    if datetime.strptime(lock["expires_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) <= _now():
        return OpenTableError(409, "SLOT_LOCK_EXPIRED", "The slot lock expired; check availability and lock the "
                                                        "slot again.")
    if special_request and len(special_request) > REQUEST_LIMIT:
        return invalid(f"special_request must be at most {REQUEST_LIMIT} characters", "special_request")
    if occasion and occasion not in OCCASIONS:
        return invalid(f"occasion must be one of {', '.join(OCCASIONS)}", "occasion")
    clash = _conflict(account_id, lock["date_time"], lock["party_size"])
    if clash is not None:
        other = _restaurant(clash["rid"])
        return OpenTableError(409, "DINER_HAS_CONFLICTING_RESERVATION",
                              f"You already have a reservation at {other['name'] if other else clash['rid']} on "
                              f"{clash['date_time']} (confirmation {clash['confirmation_number']}).")
    diner = _store.table("diners").get(account_id) or {}
    number = str(80000000 + secrets.randbelow(19999999))
    while _store.table("reservations").get(number) is not None:
        number = str(80000000 + secrets.randbelow(19999999))
    row = {
        "confirmation_number": number, "rid": rid, "diner_account_id": account_id, "status": "Confirmed",
        "date_time": lock["date_time"], "party_size": lock["party_size"], "seating": lock["seating"],
        "table_size": lock["table_size"],
        "first_name": first_name or diner.get("first_name", ""), "last_name": last_name or diner.get("last_name", ""),
        "email_address": email_address or diner.get("email_address", ""),
        "phone_number": phone_number or diner.get("phone_number", ""),
        "special_request": special_request or "", "occasion": occasion or "", "created_at": _iso_utc(_now()),
        "cancelled_at": "",
    }
    _store.table("reservations").upsert(row)
    _store.table("slot_locks").patch(token, {"used": True})
    return _reservation_view(_store.table("reservations").get(number), restaurant)


def get_reservation(rid, account_id, number):
    row = _store.table("reservations").get(number)
    if row is None or row["rid"] != rid or row["diner_account_id"] != account_id:
        return _no_reservation(rid, number)
    return _reservation_view(row, _restaurant(rid))


def cancel_reservation(rid, account_id, number):
    row = _store.table("reservations").get(number)
    if row is None or row["rid"] != rid or row["diner_account_id"] != account_id:
        return _no_reservation(rid, number)
    if row["status"] != "Confirmed":
        return OpenTableError(409, "RESERVATION_NOT_CANCELLABLE",
                              f"Reservation {number} is {row['status']} and cannot be cancelled.")
    _store.table("reservations").patch(number, {"status": "Cancelled", "cancelled_at": _iso_utc(_now())})
    return _reservation_view(_store.table("reservations").get(number), _restaurant(rid))


_store.eager_load()
