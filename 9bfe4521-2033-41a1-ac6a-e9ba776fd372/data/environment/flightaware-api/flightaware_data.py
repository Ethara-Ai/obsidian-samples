"""Data access module for the FlightAware AeroAPI mock service.

Serves exactly the four flight-tracking connector operations the client lists --
service reachability, flight status, airport delays, airport weather -- from one
seeded snapshot of 2026-10-03T18:00Z. Flight data is public, so reads are not
scoped to an account; the token's scopes decide which operations it may call.
The service is read-only.
"""

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent

sys.path.insert(0, str(DATA_DIR.parent))
import _mock_clock  # noqa: E402
from _mutable_store import (  # noqa: E402
    get_store, opt_bool, opt_csv_list, opt_int, opt_str, read_seed_with_ctx, strict_float, strict_int,
)
from _connector_auth import ConnectorAuth  # noqa: E402

_API = "flightaware-api"
_store = get_store(_API)

_IDENT = re.compile(r"^[A-Za-z0-9]{3,10}$")
_AIRPORT = re.compile(r"^[A-Za-z0-9]{3,4}$")
_INSTANT = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?)?$")
_PLUS_AS_SPACE = re.compile(r"(T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?) (\d{2}:?\d{2})$")
_TIME_FIELDS = ("scheduled_out", "estimated_out", "actual_out", "scheduled_off", "estimated_off", "actual_off",
                "scheduled_on", "estimated_on", "actual_on", "scheduled_in", "estimated_in", "actual_in")


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _coerce_flight_row(r):
    out = _strip_ctx(r)
    out["cancelled"] = opt_bool(out, "cancelled", False)
    out["diverted"] = opt_bool(out, "diverted", False)
    out["departure_delay"] = opt_int(out, "departure_delay")
    out["arrival_delay"] = opt_int(out, "arrival_delay")
    out["progress_percent"] = strict_int(out, "progress_percent")
    return out


def _coerce_delay_row(r):
    out = _strip_ctx(r)
    out["delay_secs"] = strict_int(out, "delay_secs")
    return out


def _coerce_observation_row(r):
    out = _strip_ctx(r)
    for column in ("temp_air", "temp_dewpoint", "wind_direction", "wind_speed"):
        out[column] = strict_int(out, column)
    out["wind_speed_gust"] = opt_int(out, "wind_speed_gust")
    out["visibility"] = strict_float(out, "visibility")
    out["pressure"] = strict_float(out, "pressure")
    out["clouds"] = opt_csv_list(out, "clouds", sep=";")
    return out


_store.register("airports", primary_key="code_icao",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("airports.json", "airports")])
_store.register("flights", primary_key="fa_flight_id",
                initial_loader=lambda: [_coerce_flight_row(r) for r in _load("flights.json", "flights")],
                row_coercer=_coerce_flight_row)
_store.register("airport_delays", primary_key="id",
                initial_loader=lambda: [_coerce_delay_row(r) for r in _load("airport_delays.json", "airport_delays")],
                row_coercer=_coerce_delay_row)
_store.register("observations", primary_key="id",
                initial_loader=lambda: [_coerce_observation_row(r) for r in _load("observations.json", "observations")],
                row_coercer=_coerce_observation_row)

auth = ConnectorAuth(_API, store=_store, data_dir=DATA_DIR)


class AeroError:
    """An AeroAPI error envelope and the HTTP status it is served with."""

    def __init__(self, status, title, reason, detail):
        self.status = status
        self.body = {"title": title, "reason": reason, "detail": detail, "status": status}


def _invalid(detail):
    return AeroError(400, "Invalid argument", "INVALID_ARGUMENT", detail)


def _missing(detail):
    return AeroError(404, "Not found", "NOT_FOUND", detail)


def server_time():
    return _mock_clock.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _airport(code):
    """Airport row for an ICAO or IATA code, None when unknown, an error for a malformed code."""
    if not _AIRPORT.match(code or ""):
        return _invalid(f"'{code}' is not a valid ICAO or IATA airport code.")
    wanted = code.upper()
    for a in _store.table("airports").rows():
        if wanted in (a["code_icao"], a["code_iata"]):
            return a
    return None


def _airport_view(code):
    a = _store.table("airports").get(code)
    if a is None:
        return {"code": code, "code_icao": code, "code_iata": None, "name": None, "city": None, "timezone": None}
    return {"code": a["code_icao"], "code_icao": a["code_icao"], "code_iata": a["code_iata"], "name": a["name"],
            "city": a["city"], "timezone": a["timezone"]}


def _instant(value, name):
    text = _PLUS_AS_SPACE.sub(r"\1+\2", (value or "").strip())
    if not _INSTANT.match(text):
        return _invalid(f"The parameter {name} must be an ISO 8601 date or datetime.")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return _invalid(f"The parameter {name} must be an ISO 8601 date or datetime.")
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _when(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _flight_view(f):
    view = {
        "ident": f["ident"], "ident_icao": f["ident"], "ident_iata": opt_str(f, "ident_iata") or None,
        "fa_flight_id": f["fa_flight_id"], "operator": f["operator"], "operator_icao": f["operator"],
        "operator_iata": opt_str(f, "operator_iata") or None, "flight_number": f["flight_number"],
        "registration": opt_str(f, "registration") or None,
        "origin": _airport_view(f["origin_code"]), "destination": _airport_view(f["destination_code"]),
    }
    for field in _TIME_FIELDS:
        view[field] = opt_str(f, field) or None
    view.update({
        "departure_delay": f["departure_delay"], "arrival_delay": f["arrival_delay"], "status": f["status"],
        "cancelled": f["cancelled"], "diverted": f["diverted"],
        "diverted_to": _airport_view(f["diverted_to"]) if opt_str(f, "diverted_to") else None,
        "gate_origin": opt_str(f, "gate_origin") or None, "gate_destination": opt_str(f, "gate_destination") or None,
        "terminal_origin": opt_str(f, "terminal_origin") or None,
        "terminal_destination": opt_str(f, "terminal_destination") or None,
        "baggage_claim": opt_str(f, "baggage_claim") or None, "aircraft_type": opt_str(f, "aircraft_type") or None,
        "progress_percent": f["progress_percent"],
    })
    return view


# --- reachability ------------------------------------------------------------------

def ping():
    return {"status": "ok", "service": "aeroapi", "server_time": server_time()}


# --- flight status -------------------------------------------------------------------

def get_flights(ident, start=None, end=None):
    if not _IDENT.match(ident or ""):
        return _invalid(f"'{ident}' is not a valid flight identifier (an ICAO or IATA airline code and flight number).")
    first = last = None
    if start is not None:
        first = _instant(start, "start")
        if isinstance(first, AeroError):
            return first
    if end is not None:
        last = _instant(end, "end")
        if isinstance(last, AeroError):
            return last
    if first is not None and last is not None and first > last:
        return _invalid("The parameter start must not be later than end.")
    wanted = ident.upper()
    rows = _store.table("flights").find(lambda f: wanted in (f["ident"], f.get("ident_iata", "")))
    if not rows:
        return _missing(f"No flight was found for the identifier '{ident}'.")
    rows = sorted(rows, key=lambda f: f["scheduled_out"])
    if first is not None:
        rows = [f for f in rows if _when(f["scheduled_out"]) >= first]
    if last is not None:
        rows = [f for f in rows if _when(f["scheduled_out"]) < last]
    return {"flights": [_flight_view(f) for f in rows], "links": None, "num_pages": 1}


# --- airport delays -------------------------------------------------------------------

def _summary(reasons, direction):
    applicable = [r["delay_secs"] for r in reasons if r["applies_to"] in (direction, "both")]
    worst = max(applicable, default=0)
    color = "green" if worst < 900 else ("yellow" if worst < 3600 else "red")
    return {"delay_secs": worst, "color": color}


def get_airport_delays(airport_id):
    a = _airport(airport_id)
    if isinstance(a, AeroError):
        return a
    if a is None:
        return _missing(f"No airport was found for the code '{airport_id}'.")
    rows = sorted(_store.table("airport_delays").find(lambda d: d["airport_code"] == a["code_icao"]),
                  key=lambda d: (-d["delay_secs"], d["id"]))
    return {
        "airport_code": a["code_icao"], "airport_code_icao": a["code_icao"], "airport_code_iata": a["code_iata"],
        "name": a["name"], "city": a["city"],
        "reasons": [{"category": d["category"], "reason": d["reason"], "color": d["color"],
                     "delay_secs": d["delay_secs"], "applies_to": d["applies_to"]} for d in rows],
        "departure_delay": _summary(rows, "departures"),
        "arrival_delay": _summary(rows, "arrivals"),
        "updated_at": max((d["updated_at"] for d in rows), default=None),
    }


# --- airport weather -------------------------------------------------------------------

def _cloud_view(token):
    kind, _, hundreds = token.partition(":")
    return {"type": kind, "altitude": int(hundreds)}


def get_observations(airport_id):
    a = _airport(airport_id)
    if isinstance(a, AeroError):
        return a
    if a is None:
        return _missing(f"No airport was found for the code '{airport_id}'.")
    rows = sorted(_store.table("observations").find(lambda o: o["airport_code"] == a["code_icao"]),
                  key=lambda o: o["time"], reverse=True)
    data = [{
        "time": o["time"], "raw_data": o["raw_data"], "temp_air": o["temp_air"], "temp_dewpoint": o["temp_dewpoint"],
        "wind_direction": o["wind_direction"], "wind_speed": o["wind_speed"], "wind_speed_gust": o["wind_speed_gust"],
        "visibility": o["visibility"], "visibility_units": "sm", "pressure": o["pressure"], "pressure_units": "hPa",
        "clouds": [_cloud_view(c) for c in o["clouds"]], "conditions": o["conditions"] or None,
        "flight_category": o["flight_category"],
    } for o in rows]
    return {"observations": data, "links": None, "num_pages": 1}


_store.eager_load()
