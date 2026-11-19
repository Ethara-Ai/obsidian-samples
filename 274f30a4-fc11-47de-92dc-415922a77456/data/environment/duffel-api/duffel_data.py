"""Data access module for the Duffel API mock service.

Serves exactly the nine Duffel connector operations the client lists -- search,
seat-options, validate-booking, booking-status, book, stays-search,
stays-fetch-rates, cancel-booking, cancellation-quote -- for the travel agency
that owns the connected Duffel test account. Offers are generated
deterministically from a seeded weekly flight schedule: the same request returns
the same flights and prices on any day, only ids and expiry times differ. Every
offer request, offer, order, cancellation and stay search is owned by the
connected account that made it and is invisible to any other.

Interpretations the spec left open:
  * Flights are nonstop; a multi-slice request only combines flights of one
    airline in one cabin.
  * Schedule times are local; arrival is derived from the duration using each
    airport's UTC offset, with the 2026 daylight-saving end dates applied.
  * Seat prices are the layout's fee in the offer's currency. A seat with a
    zero fee is free and carries no seat service.
  * Refund = offer total - (condition penalty for the whole party); the seat
    services bought with the order are not refunded.
"""

import hashlib
import itertools
import math
import re
import sys
import uuid
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

DATA_DIR = Path(__file__).parent

sys.path.insert(0, str(DATA_DIR.parent))
import _mock_clock  # noqa: E402
from _mutable_store import (  # noqa: E402
    CoerceError, get_store, opt_csv_list, read_seed_with_ctx, strict_bool, strict_float, strict_int,
)
from _connector_auth import ConnectorAuth  # noqa: E402

_API = "duffel-api"
_store = get_store(_API)

CABIN_ORDER = ("economy", "premium_economy", "business", "first")
CABIN_MARKETING = {"economy": "Main Cabin", "premium_economy": "Premium Select",
                   "business": "Business", "first": "First"}
CHECKED_BAGS = {"economy": 0, "premium_economy": 1, "business": 2, "first": 2}
OCCUPANCY_PCT = {"economy": 38, "premium_economy": 30, "business": 25, "first": 20}
SCHEDULE_FROM = date(2026, 10, 1)
SCHEDULE_TO = date(2026, 12, 31)
STAY_FROM = date(2026, 10, 1)
STAY_TO = date(2027, 1, 31)
MAX_NIGHTS = 30
MAX_PASSENGERS = 9
MAX_OFFERS = 50
OFFER_TTL = timedelta(minutes=30)
CANCELLATION_TTL = timedelta(minutes=30)
PAX_FARE_FACTOR = {"adult": Decimal("1"), "child": Decimal("0.75"), "infant_without_seat": Decimal("0.10")}
TAX_RULES = {"US": (Decimal("0.075"), Decimal("5.60")), "EU": (Decimal("0.11"), Decimal("9.40"))}
DST_END = {"US": date(2026, 11, 1), "EU": date(2026, 10, 25)}
CENT = Decimal("0.01")
PHONE_RE = re.compile(r"^\+[1-9][0-9]{6,14}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
AMOUNT_RE = re.compile(r"^[0-9]+\.[0-9]{2}$")
REF_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


# --- money ---------------------------------------------------------------------

def _money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def _fmt(value):
    return f"{_money(value):.2f}"


def _money_cell(row, column, required=True):
    if column not in row:
        raise CoerceError(f"required column missing: {column}")
    raw = row[column]
    if raw is None or str(raw).strip() == "":
        if required:
            raise CoerceError(f"required amount is blank: {column}")
        return ""
    try:
        return _fmt(Decimal(str(raw).strip()))
    except InvalidOperation:
        raise CoerceError(f"amount unparseable, got {raw!r}: {column}")


# --- seed loading ----------------------------------------------------------------

def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _coerce_airport(r):
    out = _strip_ctx(r)
    out["std_offset_minutes"] = strict_int(out, "std_offset_minutes")
    out["latitude"] = strict_float(out, "latitude")
    out["longitude"] = strict_float(out, "longitude")
    return out


def _coerce_airline(r):
    out = _strip_ctx(r)
    for kind in ("refund", "change"):
        for cabin in CABIN_ORDER:
            out[f"{kind}_penalty_{cabin}"] = _money_cell(out, f"{kind}_penalty_{cabin}", required=False)
    return out


def _coerce_layout(r):
    out = _strip_ctx(r)
    out["row_start"] = strict_int(out, "row_start")
    out["row_end"] = strict_int(out, "row_end")
    for column in ("columns", "aisles_after", "exit_rows", "preferred_rows"):
        out[column] = [v.strip() for v in opt_csv_list(out, column) if v.strip()]
    for column in ("fee_standard", "fee_preferred", "fee_exit"):
        out[column] = _money_cell(out, column)
    return out


def _coerce_schedule(r):
    out = _strip_ctx(r)
    out["duration_minutes"] = strict_int(out, "duration_minutes")
    out["days_of_week"] = [v.strip() for v in opt_csv_list(out, "days_of_week") if v.strip()]
    for cabin in CABIN_ORDER:
        out[f"fare_{cabin}"] = _money_cell(out, f"fare_{cabin}", required=False)
    return out


def _coerce_blocked(r):
    out = _strip_ctx(r)
    out["seats_blocked"] = strict_int(out, "seats_blocked")
    return out


def _coerce_accommodation(r):
    out = _strip_ctx(r)
    out["latitude"] = strict_float(out, "latitude")
    out["longitude"] = strict_float(out, "longitude")
    out["star_rating"] = strict_int(out, "star_rating")
    out["review_score"] = strict_float(out, "review_score")
    out["amenities"] = [v.strip() for v in opt_csv_list(out, "amenities") if v.strip()]
    return out


def _coerce_room(r):
    out = _strip_ctx(r)
    out["max_guests"] = strict_int(out, "max_guests")
    return out


def _coerce_rate(r):
    out = _strip_ctx(r)
    out["nightly_amount"] = _money_cell(out, "nightly_amount")
    out["tax_percent"] = _money_cell(out, "tax_percent")
    out["refundable"] = strict_bool(out, "refundable")
    out["free_cancellation_days"] = strict_int(out, "free_cancellation_days")
    return out


def _seed_table(name, filename, coercer=None):
    if coercer is None:
        _store.register(name, primary_key="id",
                        initial_loader=lambda: [_strip_ctx(r) for r in _load(filename, name)])
    else:
        _store.register(name, primary_key="id",
                        initial_loader=lambda: [coercer(r) for r in _load(filename, name)],
                        row_coercer=coercer)


_seed_table("airports", "airports.json", _coerce_airport)
_seed_table("airlines", "airlines.json", _coerce_airline)
_seed_table("aircraft", "aircraft.json")
_seed_table("seat_layouts", "seat_layouts.json", _coerce_layout)
_seed_table("schedules", "schedules.json", _coerce_schedule)
_seed_table("blocked_inventory", "blocked_inventory.json", _coerce_blocked)
_seed_table("accommodations", "accommodations.json", _coerce_accommodation)
_seed_table("rooms", "rooms.json", _coerce_room)
_seed_table("rates", "rates.json", _coerce_rate)
for _runtime in ("offer_requests", "offers", "orders", "booked_seats", "order_cancellations",
                 "stay_search_results"):
    _store.register(_runtime, primary_key="id", initial_loader=lambda: [])

auth = ConnectorAuth(_API, store=_store, data_dir=DATA_DIR)


# --- errors ----------------------------------------------------------------------

class DuffelError:
    """A Duffel error envelope and the HTTP status it is served with."""

    def __init__(self, status, error_type, code, title, message):
        self.status = status
        self.body = {
            "errors": [{"type": error_type, "title": title, "message": message, "code": code}],
            "meta": {"status": status,
                     "request_id": "FZ" + hashlib.sha1(message.encode()).hexdigest()[:14]},
        }


def _missing(kind, ident):
    return DuffelError(404, "invalid_request_error", "not_found", "Resource not found",
                       f"Could not find the {kind} with ID '{ident}'.")


def _bad(code, message, title="Invalid request"):
    return DuffelError(400, "invalid_request_error", code, title, message)


def _invalid(code, message, title="Validation error"):
    return DuffelError(422, "validation_error", code, title, message)


def _state(code, message, title):
    return DuffelError(422, "invalid_state_error", code, title, message)


# --- small helpers -----------------------------------------------------------------

def _now():
    return _mock_clock.now(timezone.utc)


def _ts(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def _parse_ts(value):
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


def _local(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%S")


def _hex(n):
    return uuid.uuid4().hex[:n]


def _parse_date(value, name):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return _bad("invalid_date", f"{name} must be an ISO 8601 date (YYYY-MM-DD), got {value!r}.")


def _iso_duration(minutes):
    return f"PT{minutes // 60}H{minutes % 60}M"


def _pax_type_for_age(age):
    if age < 2:
        return "infant_without_seat"
    if age < 18:
        return "child"
    return "adult"


def _age_on(born_on, when):
    return when.year - born_on.year - ((when.month, when.day) < (born_on.month, born_on.day))


# --- airports, airlines, times ---------------------------------------------------------

def _offset_minutes(airport, on_date):
    return airport["std_offset_minutes"] + (60 if on_date < DST_END[airport["region"]] else 0)


def _flight_times(sched, dep_date, origin, dest):
    hh, mm = (int(x) for x in sched["departure_time"].split(":"))
    dep_local = datetime.combine(dep_date, time(hh, mm))
    dep_utc = dep_local - timedelta(minutes=_offset_minutes(origin, dep_date))
    arr_utc = dep_utc + timedelta(minutes=sched["duration_minutes"])
    arr_local = arr_utc + timedelta(minutes=_offset_minutes(dest, arr_utc.date()))
    return dep_local, arr_local


def _airport_view(a):
    return {"id": f"arp_{a['iata_code'].lower()}", "iata_code": a["iata_code"], "name": a["name"],
            "city_name": a["city_name"], "iata_city_code": a["iata_code"],
            "iata_country_code": a["country_code"], "latitude": a["latitude"],
            "longitude": a["longitude"]}


def _airline_view(al):
    return {"id": f"arl_{al['iata_code']}", "iata_code": al["iata_code"], "name": al["name"]}


def _aircraft_view(ac):
    return {"id": f"arc_{ac['id']}", "iata_code": ac["iata_code"], "name": ac["name"]}


# --- layouts and inventory -------------------------------------------------------------

def _layouts(aircraft_id):
    return {l["cabin_class"]: l for l in _store.table("seat_layouts").find(
        lambda l: l["aircraft_id"] == aircraft_id)}


def _designators(layout):
    return [f"{n}{c}" for n in range(layout["row_start"], layout["row_end"] + 1)
            for c in layout["columns"]]


def _seat_fee(layout, row_no):
    key = str(row_no)
    if key in layout["exit_rows"]:
        return Decimal(layout["fee_exit"])
    if key in layout["preferred_rows"]:
        return Decimal(layout["fee_preferred"])
    return Decimal(layout["fee_standard"])


def _row_of(designator):
    return int(designator[:-1])


def _baseline_taken(flight_key, cabin, designator):
    digest = hashlib.sha256(f"{flight_key}:{designator}".encode()).hexdigest()
    return int(digest[:8], 16) % 100 < OCCUPANCY_PCT[cabin]


def _flight_key(schedule_id, dep_date):
    return f"{schedule_id}:{dep_date.isoformat() if isinstance(dep_date, date) else dep_date}"


class _Inventory:
    """One consistent read of the sold and blocked seats."""

    def __init__(self):
        booked_rows = _store.table("booked_seats").rows()
        self.booked = Counter((b["flight_key"], b["cabin_class"]) for b in booked_rows)
        self.taken = {fk: {b["designator"] for b in booked_rows if b["flight_key"] == fk and b["designator"]}
                      for fk in {b["flight_key"] for b in booked_rows}}
        self.blocked = Counter()
        for blk in _store.table("blocked_inventory").rows():
            self.blocked.update({(blk["schedule_id"], blk["date"], blk["cabin_class"]): blk["seats_blocked"]})

    def free_seats(self, schedule_id, dep_date, cabin, layout):
        fk = _flight_key(schedule_id, dep_date)
        seats = _designators(layout)
        occupied = sum(1 for d in seats if _baseline_taken(fk, cabin, d))
        booked = self.booked.get((fk, cabin), 0)
        blocked = self.blocked.get((schedule_id, dep_date.isoformat(), cabin), 0)
        return len(seats) - occupied - booked - blocked

    def seat_free(self, fk, cabin, designator):
        return (not _baseline_taken(fk, cabin, designator)
                and designator not in self.taken.get(fk, set()))


# --- pricing -----------------------------------------------------------------------------

def _date_factor(d):
    weekday = {4: Decimal("1.10"), 6: Decimal("1.08"), 5: Decimal("0.95"),
               1: Decimal("0.92"), 2: Decimal("0.92")}.get(d.weekday(), Decimal("1.00"))
    if d.month == 11 and d.day >= 22:
        season = Decimal("1.25") if d.day <= 29 else Decimal("0.95")
    elif d.month == 11:
        season = Decimal("0.95")
    elif d.month == 12 and d.day >= 15:
        season = Decimal("1.30")
    elif d.month == 12:
        season = Decimal("0.97")
    else:
        season = Decimal("1.00")
    return weekday * season


def _price(legs, pax_types, cabin):
    """(base, tax) for the party over the given (schedule, date, origin airport) legs."""
    base_total = Decimal("0")
    tax_total = Decimal("0")
    for sched, dep_date, origin in legs:
        rate, fixed = TAX_RULES[origin["region"]]
        adult_base = _money(Decimal(sched[f"fare_{cabin}"]) * _date_factor(dep_date))
        for ptype in pax_types:
            pax_base = _money(adult_base * PAX_FARE_FACTOR[ptype])
            base_total += pax_base
            tax_total += _money(pax_base * rate) + fixed
    return _money(base_total), _money(tax_total)


def _conditions(airline, cabin, currency, party):
    def one(kind):
        raw = airline.get(f"{kind}_penalty_{cabin}", "")
        if raw == "":
            return {"allowed": False, "penalty_amount": None, "penalty_currency": None}
        return {"allowed": True, "penalty_amount": _fmt(Decimal(raw) * party),
                "penalty_currency": currency}
    return {"refund_before_departure": one("refund"), "change_before_departure": one("change")}


# --- views ---------------------------------------------------------------------------------

def _segment_view(seg, cabin, passengers, seats=None):
    origin = _store.table("airports").get(seg["origin"])
    dest = _store.table("airports").get(seg["destination"])
    sched = _store.table("schedules").get(seg["schedule_id"])
    airline = _store.table("airlines").get(sched["airline_id"])
    aircraft = _store.table("aircraft").get(seg["aircraft_id"])
    number = sched["flight_number"].split(" ")[1]
    pax_rows = []
    for p in passengers:
        entry = {"passenger_id": p["id"], "cabin_class": cabin,
                 "cabin_class_marketing_name": CABIN_MARKETING[cabin],
                 "baggages": [{"type": "checked", "quantity": CHECKED_BAGS[cabin]},
                              {"type": "carry_on", "quantity": 0 if p["type"] == "infant_without_seat" else 1}]}
        if seats is not None:
            entry = {**entry, "seat": ({"designator": seats[p["id"]], "name": seats[p["id"]]}
                                       if p["id"] in seats else None)}
        pax_rows.append(entry)
    return {
        "id": seg["segment_id"], "origin": _airport_view(origin), "destination": _airport_view(dest),
        "departing_at": seg["departing_at"], "arriving_at": seg["arriving_at"],
        "duration": _iso_duration(seg["duration_minutes"]),
        "marketing_carrier": _airline_view(airline), "operating_carrier": _airline_view(airline),
        "marketing_carrier_flight_number": number, "operating_carrier_flight_number": number,
        "aircraft": _aircraft_view(aircraft), "passengers": pax_rows,
    }


def _slice_views(row, seats_by_segment=None):
    out = []
    for index, sl in enumerate(row["slices"]):
        seg = sl["segment"]
        seats = seats_by_segment.get(index, {}) if seats_by_segment is not None else None
        view = _segment_view(seg, row["cabin_class"], row["passengers"], seats)
        origin = _store.table("airports").get(sl["origin"])
        dest = _store.table("airports").get(sl["destination"])
        out.append({"id": sl["slice_id"], "origin": _airport_view(origin),
                    "destination": _airport_view(dest), "departure_date": sl["departure_date"],
                    "duration": view["duration"], "fare_brand_name": CABIN_MARKETING[row["cabin_class"]],
                    "segments": [view]})
    return out


def _passenger_view(p):
    out = {"id": p["id"], "type": p["type"]}
    if p.get("age") is not None:
        out["age"] = p["age"]
    return out


def _offer_view(row):
    airline = _store.table("airlines").get(row["airline_id"])
    return {
        "id": row["id"], "live_mode": False, "offer_request_id": row["offer_request_id"],
        "created_at": row["created_at"], "updated_at": row["updated_at"],
        "expires_at": row["expires_at"],
        "total_amount": row["total_amount"], "total_currency": row["currency"],
        "base_amount": row["base_amount"], "base_currency": row["currency"],
        "tax_amount": row["tax_amount"], "tax_currency": row["currency"],
        "owner": _airline_view(airline), "cabin_class": row["cabin_class"],
        "slices": _slice_views(row), "passengers": [_passenger_view(p) for p in row["passengers"]],
        "conditions": row["conditions"],
        "passenger_identity_documents_required": False,
        "payment_requirements": {"requires_instant_payment": True,
                                 "payment_required_by": None,
                                 "price_guarantee_expires_at": row["expires_at"]},
    }


# --- offer requests (.search) ----------------------------------------------------------------

def _resolve_passengers(raw):
    if len(raw) > MAX_PASSENGERS:
        return _bad("too_many_passengers", f"A request can carry at most {MAX_PASSENGERS} passengers.")
    out = []
    for p in raw:
        ptype, age = p.get("type"), p.get("age")
        if (ptype is None) == (age is None):
            return _bad("invalid_passenger", "Each passenger needs exactly one of 'type' or 'age'.")
        if age is not None:
            if age < 0 or age > 120:
                return _bad("invalid_passenger", f"Passenger age {age} is out of range.")
            ptype = _pax_type_for_age(age)
        out.append({"id": f"pas_{_hex(16)}", "type": ptype, **({"age": age} if age is not None else {})})
    adults = sum(1 for p in out if p["type"] == "adult")
    infants = sum(1 for p in out if p["type"] == "infant_without_seat")
    if adults == 0:
        return _bad("adult_required", "At least one adult passenger is required.")
    if infants > adults:
        return _bad("too_many_infants", "Each infant needs its own accompanying adult.")
    return out


def _resolve_slices(raw):
    out = []
    airports = _store.table("airports")
    previous = None
    for i, s in enumerate(raw):
        origin = airports.get(s["origin"].strip().upper())
        dest = airports.get(s["destination"].strip().upper())
        if origin is None:
            return _bad("unknown_airport", f"slices[{i}].origin {s['origin']!r} is not a supported airport.")
        if dest is None:
            return _bad("unknown_airport",
                        f"slices[{i}].destination {s['destination']!r} is not a supported airport.")
        if origin["id"] == dest["id"]:
            return _bad("same_origin_destination", f"slices[{i}] origin and destination are the same.")
        day = _parse_date(s["departure_date"], f"slices[{i}].departure_date")
        if isinstance(day, DuffelError):
            return day
        if not SCHEDULE_FROM <= day <= SCHEDULE_TO:
            return _bad("departure_date_out_of_range",
                        f"slices[{i}].departure_date must fall between {SCHEDULE_FROM} and {SCHEDULE_TO}.")
        if previous is not None and day < previous:
            return _bad("slice_order", "Slice departure dates must not go backwards.")
        previous = day
        out.append({"origin": origin, "destination": dest, "date": day})
    return out


def create_offer_request(account_id, slices, passengers, cabin_class=None):
    pax = _resolve_passengers(passengers)
    if isinstance(pax, DuffelError):
        return pax
    legs = _resolve_slices(slices)
    if isinstance(legs, DuffelError):
        return legs
    seat_pax = sum(1 for p in pax if p["type"] != "infant_without_seat")
    pax_types = [p["type"] for p in pax]
    schedules = _store.table("schedules").rows()
    airlines = {a["id"]: a for a in _store.table("airlines").rows()}
    layouts = {}
    inv = _Inventory()
    now = _now()
    request_id = f"orq_{_hex(24)}"
    candidates = []
    for cabin in ([cabin_class] if cabin_class else list(CABIN_ORDER)):
        per_slice = []
        for leg in legs:
            by_airline = {}
            for s in schedules:
                if (s["origin"] != leg["origin"]["id"] or s["destination"] != leg["destination"]["id"]
                        or str(leg["date"].isoweekday()) not in s["days_of_week"]
                        or not s["valid_from"] <= leg["date"].isoformat() <= s["valid_to"]
                        or not s[f"fare_{cabin}"]):
                    continue
                lay = layouts.setdefault(s["aircraft_id"], _layouts(s["aircraft_id"])).get(cabin)
                if lay is None or inv.free_seats(s["id"], leg["date"], cabin, lay) < seat_pax:
                    continue
                by_airline.setdefault(s["airline_id"], []).append(s)
            per_slice.append(by_airline)
        for airline_id in sorted(set.intersection(*(set(m) for m in per_slice))):
            for combo in itertools.product(*(m[airline_id] for m in per_slice)):
                candidates.append((cabin, airline_id, combo))
    offers = []
    for cabin, airline_id, combo in candidates:
        priced = [(s, leg["date"], leg["origin"]) for s, leg in zip(combo, legs)]
        base, tax = _price(priced, pax_types, cabin)
        currency = combo[0]["currency"]
        offer_slices = []
        for s, leg in zip(combo, legs):
            dep, arr = _flight_times(s, leg["date"], leg["origin"], leg["destination"])
            offer_slices.append({
                "slice_id": f"sli_{_hex(24)}", "origin": leg["origin"]["id"],
                "destination": leg["destination"]["id"], "departure_date": leg["date"].isoformat(),
                "segment": {"segment_id": f"seg_{_hex(24)}", "schedule_id": s["id"],
                            "flight_key": _flight_key(s["id"], leg["date"]),
                            "aircraft_id": s["aircraft_id"], "origin": leg["origin"]["id"],
                            "destination": leg["destination"]["id"], "departing_at": _local(dep),
                            "arriving_at": _local(arr), "duration_minutes": s["duration_minutes"]}})
        offers.append({
            "id": f"off_{_hex(24)}", "owner_account_id": account_id, "offer_request_id": request_id,
            "created_at": _ts(now), "updated_at": _ts(now), "expires_at": _ts(now + OFFER_TTL),
            "total_amount": _fmt(base + tax), "base_amount": _fmt(base), "tax_amount": _fmt(tax),
            "currency": currency, "cabin_class": cabin, "airline_id": airline_id,
            "slices": offer_slices, "passengers": [dict(p) for p in pax],
            "conditions": _conditions(airlines[airline_id], cabin, currency, len(pax)),
            "booked_order_id": "",
            "_sort": [Decimal(base + tax), "|".join(s["flight_number"] for s in combo)],
        })
    offers.sort(key=lambda o: (o["_sort"][0], o["_sort"][1]))
    offers = offers[:MAX_OFFERS]
    for o in offers:
        o.pop("_sort")
        _store.table("offers").upsert(o)
    request_slices = [{"id": f"sli_{_hex(24)}", "origin": l["origin"]["id"],
                       "destination": l["destination"]["id"],
                       "departure_date": l["date"].isoformat()} for l in legs]
    _store.table("offer_requests").upsert({
        "id": request_id, "owner_account_id": account_id, "created_at": _ts(now),
        "cabin_class": cabin_class or "", "passengers": [dict(p) for p in pax],
        "slices": request_slices, "offer_ids": [o["id"] for o in offers],
    })
    return {"data": {
        "id": request_id, "live_mode": False, "created_at": _ts(now),
        "cabin_class": cabin_class, "passengers": [_passenger_view(p) for p in pax],
        "slices": [{"id": rs["id"], "origin": _airport_view(l["origin"]),
                    "destination": _airport_view(l["destination"]),
                    "departure_date": rs["departure_date"]}
                   for rs, l in zip(request_slices, legs)],
        "offers": [_offer_view(o) for o in offers],
    }}


# --- offers (.validate-booking) ---------------------------------------------------------------

def _owned_offer(offer_id, account_id):
    row = _store.table("offers").get(offer_id)
    if row is None or row["owner_account_id"] != account_id:
        return None
    return row


def _offer_problem(row, inv):
    """A DuffelError when the offer can no longer be sold, else None."""
    if _now() >= _parse_ts(row["expires_at"]):
        return _state("offer_expired", f"Offer {row['id']} expired at {row['expires_at']}.",
                      "Offer expired")
    if row["booked_order_id"]:
        return _state("offer_no_longer_available",
                      f"Offer {row['id']} was already booked as order {row['booked_order_id']}.",
                      "Offer no longer available")
    seat_pax = sum(1 for p in row["passengers"] if p["type"] != "infant_without_seat")
    for sl in row["slices"]:
        seg = sl["segment"]
        layout = _layouts(seg["aircraft_id"]).get(row["cabin_class"])
        dep_date = date.fromisoformat(sl["departure_date"])
        if layout is None or inv.free_seats(seg["schedule_id"], dep_date, row["cabin_class"],
                                            layout) < seat_pax:
            return _state("offer_no_longer_available",
                          f"The {row['cabin_class']} cabin on a flight in offer {row['id']} is sold out.",
                          "Offer no longer available")
    return None


def _reprice(row):
    """The offer's (base, tax) at today's seeded fares, or None when a schedule is gone."""
    legs = []
    for sl in row["slices"]:
        sched = _store.table("schedules").get(sl["segment"]["schedule_id"])
        origin = _store.table("airports").get(sl["origin"])
        if sched is None or origin is None or not sched[f"fare_{row['cabin_class']}"]:
            return None
        legs.append((sched, date.fromisoformat(sl["departure_date"]), origin))
    return _price(legs, [p["type"] for p in row["passengers"]], row["cabin_class"])


def _repriced_row(row):
    prices = _reprice(row)
    if prices is None:
        return None
    base, tax = prices
    stamp = _ts(_now())
    return _store.table("offers").patch(row["id"], {
        "base_amount": _fmt(base), "tax_amount": _fmt(tax), "total_amount": _fmt(base + tax),
        "updated_at": stamp})


def get_offer(offer_id, account_id):
    row = _owned_offer(offer_id, account_id)
    if row is None:
        return _missing("offer", offer_id)
    problem = _offer_problem(row, _Inventory())
    if problem is not None:
        return problem
    fresh = _repriced_row(row)
    if fresh is None:
        return _state("offer_no_longer_available", f"Offer {offer_id} can no longer be priced.",
                      "Offer no longer available")
    return {"data": _offer_view(fresh)}


# --- seat maps (.seat-options) ------------------------------------------------------------------

def _seat_service_id(offer_id, seg_index, designator, pax_id):
    return f"ase_{offer_id[4:]}_{seg_index}_{designator}_{pax_id[4:]}"


def _parse_seat_service(service_id):
    parts = service_id.split("_")
    if len(parts) != 5 or parts[0] != "ase" or not parts[2].isdigit():
        return None
    return {"offer_id": f"off_{parts[1]}", "seg_index": int(parts[2]), "designator": parts[3],
            "pax_id": f"pas_{parts[4]}"}


def get_seat_maps(offer_id, account_id):
    row = _owned_offer(offer_id, account_id)
    if row is None:
        return _missing("offer", offer_id)
    if _now() >= _parse_ts(row["expires_at"]):
        return _state("offer_expired", f"Offer {offer_id} expired at {row['expires_at']}.", "Offer expired")
    inv = _Inventory()
    seat_pax = [p for p in row["passengers"] if p["type"] != "infant_without_seat"]
    maps = []
    for index, sl in enumerate(row["slices"]):
        seg = sl["segment"]
        dep_date = date.fromisoformat(sl["departure_date"])
        layouts = _layouts(seg["aircraft_id"])
        cabins = []
        for cabin in reversed(CABIN_ORDER):
            layout = layouts.get(cabin)
            if layout is None:
                continue
            sold_out = inv.free_seats(seg["schedule_id"], dep_date, cabin, layout) <= 0
            rows = []
            for n in range(layout["row_start"], layout["row_end"] + 1):
                fee = _seat_fee(layout, n)
                sections, current = [], []
                for col in layout["columns"]:
                    designator = f"{n}{col}"
                    free = not sold_out and inv.seat_free(seg["flight_key"], cabin, designator)
                    services = []
                    if free and fee > 0 and cabin == row["cabin_class"]:
                        services = [{"id": _seat_service_id(offer_id, index, designator, p["id"]),
                                     "passenger_id": p["id"], "total_amount": _fmt(fee),
                                     "total_currency": row["currency"]} for p in seat_pax]
                    disclosures = []
                    if str(n) in layout["exit_rows"]:
                        disclosures.append("Exit row seat")
                    elif str(n) in layout["preferred_rows"]:
                        disclosures.append("Preferred seat")
                    current.append({"type": "seat", "designator": designator, "name": designator,
                                    "availability": "available" if free else "unavailable",
                                    "disclosures": disclosures, "available_services": services})
                    if col in layout["aisles_after"]:
                        sections.append({"elements": current})
                        current = []
                if current:
                    sections.append({"elements": current})
                rows.append({"number": n, "sections": sections})
            cabins.append({"cabin_class": cabin, "deck": 0, "aisles": len(layout["aisles_after"]),
                           "rows": rows, "wings": {"first_row_index": 0, "last_row_index": len(rows) - 1}})
        digest = hashlib.sha1(f"{offer_id}:{index}".encode()).hexdigest()[:24]
        maps.append({"id": f"sea_{digest}", "segment_id": seg["segment_id"], "slice_id": sl["slice_id"],
                     "cabins": cabins})
    return {"data": maps}


# --- orders (.book, .booking-status) -----------------------------------------------------------------

def _booking_reference(taken):
    while True:
        raw = uuid.uuid4().bytes
        ref = "".join(REF_ALPHABET[b % len(REF_ALPHABET)] for b in raw[:6])
        if ref not in taken:
            return ref


def _check_party(party, offer_pax, first_departure):
    expected = {p["id"]: p for p in offer_pax}
    seen = [p["id"] for p in party]
    if sorted(seen) != sorted(expected):
        return _invalid("passenger_mismatch",
                        "passengers must contain every passenger id of the offer exactly once; "
                        f"expected {sorted(expected)}, got {sorted(seen)}.")
    for p in party:
        born = _parse_date(p["born_on"], "born_on")
        if isinstance(born, DuffelError):
            return born
        if not PHONE_RE.match(p["phone_number"]):
            return _invalid("invalid_phone_number", f"phone_number {p['phone_number']!r} must be E.164.")
        if not EMAIL_RE.match(p["email"]):
            return _invalid("invalid_email", f"email {p['email']!r} is not a valid address.")
        if not p["given_name"].strip() or not p["family_name"].strip():
            return _invalid("invalid_name", "given_name and family_name must not be blank.")
        if born > first_departure or _pax_type_for_age(_age_on(born, first_departure)) != expected[p["id"]]["type"]:
            return _invalid("passenger_age_mismatch",
                            f"born_on {p['born_on']} does not match a {expected[p['id']]['type']} "
                            f"on {first_departure.isoformat()}.")
    return None


def _resolve_services(row, services, inv):
    """Validated seat picks as [(seg_index, pax_id, designator, fee)], or a DuffelError."""
    picks, seen_pax, seen_seat = [], set(), set()
    by_pax = {p["id"]: p for p in row["passengers"]}
    for svc in services:
        if svc["quantity"] != 1:
            return _bad("unsupported_quantity", f"Seat service {svc['id']} must have quantity 1.")
        parsed = _parse_seat_service(svc["id"])
        if parsed is None or parsed["offer_id"] != row["id"]:
            return _invalid("service_not_found", f"Service {svc['id']} does not belong to offer {row['id']}.")
        idx, pax_id, designator = parsed["seg_index"], parsed["pax_id"], parsed["designator"]
        if idx >= len(row["slices"]) or pax_id not in by_pax:
            return _invalid("service_not_found", f"Service {svc['id']} does not belong to offer {row['id']}.")
        if by_pax[pax_id]["type"] == "infant_without_seat":
            return _bad("infant_seat_not_supported",
                        "Infants travelling without a seat cannot be assigned a seat.")
        seg = row["slices"][idx]["segment"]
        layout = _layouts(seg["aircraft_id"]).get(row["cabin_class"])
        if layout is None or designator not in _designators(layout):
            return _invalid("service_not_found", f"Seat {designator} does not exist in the booked cabin.")
        fee = _seat_fee(layout, _row_of(designator))
        if fee <= 0:
            return _invalid("service_not_found", f"Seat {designator} is free and has no seat service.")
        if (idx, pax_id) in seen_pax or (idx, designator) in seen_seat:
            return _invalid("duplicate_service", f"Service {svc['id']} repeats a passenger or seat already selected.")
        seen_pax.add((idx, pax_id))
        seen_seat.add((idx, designator))
        if not inv.seat_free(seg["flight_key"], row["cabin_class"], designator):
            return _invalid("seat_unavailable", f"Seat {designator} on segment {idx} is already taken.",
                            "Seat unavailable")
        picks.append((idx, pax_id, designator, fee))
    return picks


def create_order(account_id, selected_offers, passengers, payments, services=None):
    if len(selected_offers) != 1:
        return _bad("unsupported_selection", "Exactly one offer can be booked per order.")
    if len(payments) != 1:
        return _bad("unsupported_payments", "Exactly one balance payment is supported per order.")
    offer_id = selected_offers[0]
    row = _owned_offer(offer_id, account_id)
    if row is None:
        return _missing("offer", offer_id)
    inv = _Inventory()
    problem = _offer_problem(row, inv)
    if problem is not None:
        return problem
    first_departure = date.fromisoformat(row["slices"][0]["departure_date"])
    problem = _check_party(passengers, row["passengers"], first_departure)
    if problem is not None:
        return problem
    picks = _resolve_services(row, services or [], inv)
    if isinstance(picks, DuffelError):
        return picks
    fresh = _repriced_row(row)
    if fresh is None:
        return _state("offer_no_longer_available", f"Offer {offer_id} can no longer be priced.",
                      "Offer no longer available")
    services_total = sum((fee for _i, _p, _d, fee in picks), Decimal("0"))
    total = Decimal(fresh["total_amount"]) + services_total
    pay = payments[0]
    if not AMOUNT_RE.match(pay["amount"]):
        return _invalid("invalid_amount", f"Payment amount {pay['amount']!r} must be a decimal string with 2 places.")
    if pay["currency"] != fresh["currency"]:
        return _invalid("payment_currency_mismatch",
                        f"Payment currency must be {fresh['currency']}, got {pay['currency']}.")
    if Decimal(pay["amount"]) != _money(total):
        return _invalid("payment_amount_mismatch",
                        f"Payment amount must equal {_fmt(total)} {fresh['currency']} "
                        f"(offer {fresh['total_amount']} + services {_fmt(services_total)}), got {pay['amount']}.")
    order_id = f"ord_{_hex(24)}"
    now = _now()
    seats = {}
    for idx, pax_id, designator, _fee in picks:
        seats.setdefault(idx, {})[pax_id] = designator
    detail = {p["id"]: p for p in passengers}
    airline = _store.table("airlines").get(fresh["airline_id"])
    order_pax = [{"id": p["id"], "type": p["type"], "title": detail[p["id"]]["title"],
                  "given_name": detail[p["id"]]["given_name"], "family_name": detail[p["id"]]["family_name"],
                  "born_on": detail[p["id"]]["born_on"], "gender": detail[p["id"]]["gender"],
                  "email": detail[p["id"]]["email"], "phone_number": detail[p["id"]]["phone_number"]}
                 for p in fresh["passengers"]]
    order_services = [{"id": _seat_service_id(offer_id, idx, designator, pax_id), "type": "seat",
                       "quantity": 1, "total_amount": _fmt(fee), "total_currency": fresh["currency"],
                       "passenger_id": pax_id, "segment_id": fresh["slices"][idx]["segment"]["segment_id"],
                       "designator": designator} for idx, pax_id, designator, fee in picks]
    documents = [{"type": "electronic_ticket", "passenger_ids": [p["id"]],
                  "unique_identifier": airline["ticket_prefix"] + str(
                      int(hashlib.sha1((order_id + p["id"]).encode()).hexdigest()[:12], 16) % 10**10).zfill(10)}
                 for p in fresh["passengers"]]
    taken_refs = {o["booking_reference"] for o in _store.table("orders").rows()}
    view_row = {"slices": fresh["slices"], "cabin_class": fresh["cabin_class"], "passengers": order_pax}
    _store.table("orders").upsert({
        "id": order_id, "owner_account_id": account_id,
        "booking_reference": _booking_reference(taken_refs), "status": "confirmed",
        "created_at": _ts(now), "offer_id": offer_id, "airline_id": fresh["airline_id"],
        "cabin_class": fresh["cabin_class"], "currency": fresh["currency"],
        "total_amount": _fmt(total), "base_amount": _fmt(Decimal(fresh["base_amount"]) + services_total),
        "tax_amount": fresh["tax_amount"], "offer_total_amount": fresh["total_amount"],
        "conditions": fresh["conditions"], "passengers": order_pax,
        "slices": _slice_views(view_row, seats), "services": order_services, "documents": documents,
        "payments": [{"type": "balance", "amount": _fmt(total), "currency": fresh["currency"],
                      "created_at": _ts(now)}],
        "cancelled_at": "", "cancellation_id": "",
    })
    for idx, sl in enumerate(fresh["slices"]):
        for p in fresh["passengers"]:
            if p["type"] == "infant_without_seat":
                continue
            _store.table("booked_seats").upsert({
                "id": f"{order_id}:{idx}:{p['id']}", "order_id": order_id,
                "flight_key": sl["segment"]["flight_key"], "cabin_class": fresh["cabin_class"],
                "designator": seats.get(idx, {}).get(p["id"], ""), "passenger_id": p["id"],
                "segment_id": sl["segment"]["segment_id"]})
    _store.table("offers").patch(offer_id, {"booked_order_id": order_id})
    return _order_response(order_id)


def _order_response(order_id):
    row = _store.table("orders").get(order_id)
    airline = _store.table("airlines").get(row["airline_id"])
    cancellation = None
    if row["cancellation_id"]:
        c = _store.table("order_cancellations").get(row["cancellation_id"])
        cancellation = {"id": c["id"], "refund_amount": c["refund_amount"],
                        "refund_currency": c["refund_currency"], "refund_to": c["refund_to"],
                        "confirmed_at": c["confirmed_at"] or None}
    return {"data": {
        "id": row["id"], "live_mode": False, "booking_reference": row["booking_reference"],
        "status": row["status"], "created_at": row["created_at"], "owner": _airline_view(airline),
        "total_amount": row["total_amount"], "total_currency": row["currency"],
        "base_amount": row["base_amount"], "base_currency": row["currency"],
        "tax_amount": row["tax_amount"], "tax_currency": row["currency"],
        "cabin_class": row["cabin_class"], "passengers": row["passengers"], "slices": row["slices"],
        "services": row["services"], "documents": row["documents"], "conditions": row["conditions"],
        "payments": row["payments"], "cancelled_at": row["cancelled_at"] or None,
        "cancellation": cancellation,
    }}


def _owned_order(order_id, account_id):
    row = _store.table("orders").get(order_id)
    if row is None or row["owner_account_id"] != account_id:
        return None
    return row


def get_order(order_id, account_id):
    if _owned_order(order_id, account_id) is None:
        return _missing("order", order_id)
    return _order_response(order_id)


# --- cancellations (.cancellation-quote, .cancel-booking) --------------------------------------------

def _cancellation_view(c):
    return {"id": c["id"], "order_id": c["order_id"], "live_mode": False,
            "refund_amount": c["refund_amount"], "refund_currency": c["refund_currency"],
            "refund_to": c["refund_to"], "created_at": c["created_at"],
            "expires_at": c["expires_at"], "confirmed_at": c["confirmed_at"] or None}


def quote_cancellation(account_id, order_id):
    order = _owned_order(order_id, account_id)
    if order is None:
        return _missing("order", order_id)
    if order["status"] == "cancelled":
        return _state("order_already_cancelled", f"Order {order_id} is already cancelled.",
                      "Order already cancelled")
    refund = order["conditions"]["refund_before_departure"]
    if refund["allowed"]:
        amount = max(Decimal("0"), Decimal(order["offer_total_amount"]) - Decimal(refund["penalty_amount"]))
    else:
        amount = Decimal("0")
    now = _now()
    row = {"id": f"ore_{_hex(24)}", "order_id": order_id, "owner_account_id": account_id,
           "refund_amount": _fmt(amount), "refund_currency": order["currency"], "refund_to": "balance",
           "created_at": _ts(now), "expires_at": _ts(now + CANCELLATION_TTL), "confirmed_at": ""}
    _store.table("order_cancellations").upsert(row)
    return {"data": _cancellation_view(row)}


def confirm_cancellation(account_id, cancellation_id):
    c = _store.table("order_cancellations").get(cancellation_id)
    if c is None or c["owner_account_id"] != account_id:
        return _missing("order cancellation", cancellation_id)
    if c["confirmed_at"]:
        return _state("cancellation_already_confirmed",
                      f"Cancellation {cancellation_id} was already confirmed at {c['confirmed_at']}.",
                      "Cancellation already confirmed")
    if _now() >= _parse_ts(c["expires_at"]):
        return _state("cancellation_expired",
                      f"Cancellation quote {cancellation_id} expired at {c['expires_at']}; request a new quote.",
                      "Cancellation quote expired")
    order = _store.table("orders").get(c["order_id"])
    if order["status"] == "cancelled":
        return _state("order_already_cancelled", f"Order {c['order_id']} is already cancelled.",
                      "Order already cancelled")
    stamp = _ts(_now())
    updated = _store.table("order_cancellations").patch(cancellation_id, {"confirmed_at": stamp})
    _store.table("orders").patch(c["order_id"], {"status": "cancelled", "cancelled_at": stamp,
                                                 "cancellation_id": cancellation_id})
    for seat in _store.table("booked_seats").find(lambda b: b["order_id"] == c["order_id"]):
        _store.table("booked_seats").delete(seat["id"])
    return {"data": _cancellation_view(updated)}


# --- stays (.stays-search, .stays-fetch-rates) -----------------------------------------------------------

def _haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def _night_factor(d):
    factor = Decimal("1.15") if d.weekday() in (4, 5) else Decimal("1.00")
    if d.month == 12 and d.day >= 18:
        factor *= Decimal("1.20")
    return factor


def _rate_view(rate, check_in, nights, rooms, currency):
    nightly = Decimal(rate["nightly_amount"])
    base = _money(sum((_money(nightly * _night_factor(check_in + timedelta(days=i))) for i in range(nights)),
                      Decimal("0")) * rooms)
    tax = _money(base * Decimal(rate["tax_percent"]) / 100)
    total = base + tax
    deadline = f"{(check_in - timedelta(days=rate['free_cancellation_days'])).isoformat()}T23:59:00Z"
    if rate["refundable"]:
        timeline = [{"before": deadline, "refund_amount": _fmt(total), "currency": currency},
                    {"before": f"{check_in.isoformat()}T15:00:00Z", "refund_amount": "0.00",
                     "currency": currency}]
    else:
        timeline = [{"before": f"{check_in.isoformat()}T15:00:00Z", "refund_amount": "0.00",
                     "currency": currency}]
    return {"id": rate["id"], "name": rate["name"], "board_type": rate["board_type"],
            "payment_type": rate["payment_type"], "base_amount": _fmt(base), "tax_amount": _fmt(tax),
            "total_amount": _fmt(total), "total_currency": currency,
            "cancellation_timeline": timeline}


def _eligible_rooms(accommodation_id, rooms, guests):
    return [r for r in _store.table("rooms").find(lambda r: r["accommodation_id"] == accommodation_id)
            if r["max_guests"] * rooms >= guests]


def _stay_rates(accommodation, check_in, nights, rooms, guests):
    """[(room, [rate views])] for every room that can host the party."""
    out = []
    for room in _eligible_rooms(accommodation["id"], rooms, guests):
        rates = _store.table("rates").find(lambda r: r["room_id"] == room["id"])
        out.append((room, [_rate_view(r, check_in, nights, rooms, accommodation["currency"]) for r in rates]))
    return out


def _accommodation_view(a):
    return {"id": a["id"], "name": a["name"], "brand": {"name": a["brand"]},
            "rating": a["star_rating"], "review_score": a["review_score"],
            "description": a["description"], "amenities": a["amenities"],
            "location": {"address": {"line_one": a["address_line"], "city_name": a["city_name"],
                                     "country_code": a["country_code"], "postal_code": a["postal_code"]},
                         "geographic_coordinates": {"latitude": a["latitude"], "longitude": a["longitude"]}},
            "check_in_information": {"check_in_after_time": a["check_in_after"],
                                     "check_out_before_time": a["check_out_before"]}}


def _stay_window(check_in_date, check_out_date):
    check_in = _parse_date(check_in_date, "check_in_date")
    if isinstance(check_in, DuffelError):
        return check_in
    check_out = _parse_date(check_out_date, "check_out_date")
    if isinstance(check_out, DuffelError):
        return check_out
    if check_out <= check_in:
        return _bad("invalid_stay_dates", "check_out_date must be after check_in_date.")
    if (check_out - check_in).days > MAX_NIGHTS:
        return _bad("stay_too_long", f"A stay can be at most {MAX_NIGHTS} nights.")
    if not STAY_FROM <= check_in <= STAY_TO:
        return _bad("check_in_out_of_range",
                    f"check_in_date must fall between {STAY_FROM} and {STAY_TO}.")
    return check_in, check_out


def search_stays(account_id, latitude, longitude, radius, check_in_date, check_out_date, rooms, guests):
    window = _stay_window(check_in_date, check_out_date)
    if isinstance(window, DuffelError):
        return window
    check_in, check_out = window
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return _bad("invalid_coordinates", "geographic_coordinates are out of range.")
    if not 0 < radius <= 200:
        return _bad("invalid_radius", "location.radius must be greater than 0 and at most 200 km.")
    if not 1 <= rooms <= 9:
        return _bad("invalid_rooms", "rooms must be between 1 and 9.")
    for g in guests:
        if g.get("type") == "child" and g.get("age") is None:
            return _bad("invalid_guest", "A child guest needs an age.")
        if g.get("type") == "adult" and g.get("age") is not None:
            return _bad("invalid_guest", "An adult guest does not take an age; use type child for minors.")
        if g.get("age") is not None and not 0 <= g["age"] <= 17:
            return _bad("invalid_guest", "A child guest age must be between 0 and 17.")
    if not any(g["type"] == "adult" for g in guests):
        return _bad("adult_required", "At least one adult guest is required.")
    if len(guests) < rooms:
        return _bad("too_many_rooms", "There must be at least one guest per room.")
    nights = (check_out - check_in).days
    now = _now()
    found = []
    for a in _store.table("accommodations").rows():
        distance = _haversine_km(latitude, longitude, a["latitude"], a["longitude"])
        if distance > radius:
            continue
        options = [v for _room, rates in _stay_rates(a, check_in, nights, rooms, len(guests)) for v in rates]
        if not options:
            continue
        cheapest = min(options, key=lambda v: Decimal(v["total_amount"]))
        found.append((Decimal(cheapest["total_amount"]), a["name"], a, cheapest, distance))
    found.sort(key=lambda t: (t[0], t[1]))
    results = []
    for _total, _name, a, cheapest, distance in found:
        row = {"id": f"srr_{_hex(24)}", "owner_account_id": account_id, "accommodation_id": a["id"],
               "check_in_date": check_in.isoformat(), "check_out_date": check_out.isoformat(),
               "rooms": rooms, "guests": [dict(g) for g in guests],
               "cheapest_rate_total_amount": cheapest["total_amount"],
               "cheapest_rate_currency": a["currency"], "distance_km": round(distance, 2),
               "created_at": _ts(now), "rates_fetched_at": ""}
        _store.table("stay_search_results").upsert(row)
        results.append(_search_result_view(row, a))
    return {"data": {"results": results, "created_at": _ts(now)}}


def _search_result_view(row, accommodation):
    return {"id": row["id"], "accommodation": _accommodation_view(accommodation),
            "check_in_date": row["check_in_date"], "check_out_date": row["check_out_date"],
            "rooms": row["rooms"], "guests": row["guests"],
            "cheapest_rate_total_amount": row["cheapest_rate_total_amount"],
            "cheapest_rate_currency": row["cheapest_rate_currency"],
            "distance_km": row["distance_km"]}


def fetch_all_rates(account_id, search_result_id):
    row = _store.table("stay_search_results").get(search_result_id)
    if row is None or row["owner_account_id"] != account_id:
        return _missing("stay search result", search_result_id)
    a = _store.table("accommodations").get(row["accommodation_id"])
    check_in = date.fromisoformat(row["check_in_date"])
    nights = (date.fromisoformat(row["check_out_date"]) - check_in).days
    rooms = []
    for room, rates in _stay_rates(a, check_in, nights, row["rooms"], len(row["guests"])):
        rooms.append({"id": room["id"], "name": room["name"], "beds": room["beds"],
                      "max_guests": room["max_guests"], "rates": rates})
    cheapest = min((Decimal(r["total_amount"]) for room in rooms for r in room["rates"]), default=None)
    stamp = _ts(_now())
    updated = _store.table("stay_search_results").patch(search_result_id, {
        "rates_fetched_at": stamp,
        "cheapest_rate_total_amount": _fmt(cheapest) if cheapest is not None else row["cheapest_rate_total_amount"]})
    return {"data": {**_search_result_view(updated, a),
                     "accommodation": {**_accommodation_view(a), "rooms": rooms},
                     "rates_fetched_at": stamp}}


_store.eager_load()
