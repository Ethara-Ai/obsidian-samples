"""Data access module for the normalized health-records API mock service.

Serves exactly the four health connector operations the client ranks --
query (measurements), nutrition, sleep, workouts -- for the one person linked to
the connected account. Every read is scoped to the person the presented token's
connected account owns. The service is read-only.
"""

import re
import sys
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).parent

sys.path.insert(0, str(DATA_DIR.parent))
import _mock_clock  # noqa: E402
from _mutable_store import (  # noqa: E402
    get_store, opt_float, opt_int, read_seed_with_ctx, strict_float, strict_int,
)
from _connector_auth import ConnectorAuth  # noqa: E402

_API = "health-api"
_store = get_store(_API)

# type -> (unit, aggregation applied by aggregate=day|week, whole-number values)
MEASUREMENT_TYPES = {
    "steps": ("count", "sum", True),
    "distance_km": ("km", "sum", False),
    "active_energy_kcal": ("kcal", "sum", True),
    "resting_heart_rate": ("bpm", "mean", True),
    "heart_rate_variability_ms": ("ms", "mean", True),
    "weight_kg": ("kg", "mean", False),
    "body_fat_percent": ("percent", "mean", False),
    "blood_pressure": ("mmHg", "mean", False),
    "blood_oxygen_percent": ("percent", "mean", False),
}
SPOT_TYPES = ("weight_kg", "body_fat_percent", "blood_pressure", "blood_oxygen_percent")
AGGREGATES = ("none", "day", "week")
MEALS = ("breakfast", "lunch", "dinner", "snack")
WORKOUT_TYPES = ("running", "cycling", "strength_training", "yoga", "walking", "swimming")
DEFAULT_WINDOW_DAYS = 7
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_NUTRIENTS = ("protein_g", "carbs_g", "fat_g", "fiber_g", "sugar_g", "sodium_mg")


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _coerce_measurement_row(r):
    out = _strip_ctx(r)
    out["value"] = strict_float(out, "value")
    out["value_secondary"] = opt_float(out, "value_secondary")
    return out


def _coerce_sleep_row(r):
    out = _strip_ctx(r)
    for column in ("duration_min", "time_in_bed_min", "awake_min", "light_min", "deep_min", "rem_min"):
        out[column] = strict_int(out, column)
    out["efficiency_percent"] = strict_float(out, "efficiency_percent")
    return out


def _coerce_workout_row(r):
    out = _strip_ctx(r)
    for column in ("duration_min", "active_energy_kcal", "avg_heart_rate", "max_heart_rate"):
        out[column] = strict_int(out, column)
    out["distance_km"] = opt_float(out, "distance_km")
    out["elevation_gain_m"] = opt_int(out, "elevation_gain_m")
    return out


def _coerce_nutrition_row(r):
    out = _strip_ctx(r)
    out["calories_kcal"] = strict_int(out, "calories_kcal")
    for column in _NUTRIENTS:
        out[column] = strict_float(out, column)
    return out


_store.register("people", primary_key="id",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("people.json", "people")])
_store.register("measurements", primary_key="id",
                initial_loader=lambda: [_coerce_measurement_row(r) for r in _load("measurements.json", "measurements")],
                row_coercer=_coerce_measurement_row)
_store.register("sleep_sessions", primary_key="id",
                initial_loader=lambda: [_coerce_sleep_row(r) for r in _load("sleep.json", "sleep_sessions")],
                row_coercer=_coerce_sleep_row)
_store.register("workouts", primary_key="id",
                initial_loader=lambda: [_coerce_workout_row(r) for r in _load("workouts.json", "workouts")],
                row_coercer=_coerce_workout_row)
_store.register("nutrition_entries", primary_key="id",
                initial_loader=lambda: [_coerce_nutrition_row(r) for r in _load("nutrition.json", "nutrition_entries")],
                row_coercer=_coerce_nutrition_row)

auth = ConnectorAuth(_API, store=_store, data_dir=DATA_DIR)


class HealthError:
    """A provider error envelope and the HTTP status it is served with."""

    def __init__(self, status, code, message):
        self.status = status
        self.body = {"error": {"code": code, "message": message}}


def _invalid(message):
    return HealthError(400, "invalid_parameter", message)


def _no_person(account_id):
    return HealthError(404, "not_found", f"No health profile is linked to account '{account_id}'.")


def _person(account_id):
    rows = _store.table("people").find(lambda p: p.get("account_id") == account_id)
    return rows[0] if rows else None


def _day(value, name):
    if not _DATE.match(value or ""):
        return _invalid(f"The parameter {name} must be a calendar date in YYYY-MM-DD format.")
    try:
        return date.fromisoformat(value)
    except ValueError:
        return _invalid(f"The parameter {name} must be a calendar date in YYYY-MM-DD format.")


def _window(start, end, latest):
    """Inclusive (start, end) dates; the default is the 7 days ending at the newest record."""
    last = None
    if end is not None:
        last = _day(end, "end")
        if isinstance(last, HealthError):
            return last
    first = None
    if start is not None:
        first = _day(start, "start")
        if isinstance(first, HealthError):
            return first
    if first is not None and last is not None and first > last:
        return _invalid("The parameter start must not be later than end.")
    if last is None:
        last = latest if latest is not None else (first or _mock_clock.today())
        if first is not None and first > last:
            last = first
    if first is None:
        first = last - timedelta(days=DEFAULT_WINDOW_DAYS - 1)
    return first, last


def _num(value):
    return int(value) if float(value).is_integer() else value


def _round(value, whole, places):
    return int(round(value)) if whole else round(value, places)


# --- measurements (.query) -------------------------------------------------------

def get_measurements(account_id, type_, start=None, end=None, aggregate=None):
    if not type_:
        return _invalid("The parameter type is required. One of: " + ", ".join(MEASUREMENT_TYPES))
    if type_ not in MEASUREMENT_TYPES:
        return _invalid(f"The parameter type must be one of: {', '.join(MEASUREMENT_TYPES)}.")
    mode = aggregate or "none"
    if mode not in AGGREGATES:
        return _invalid(f"The parameter aggregate must be one of: {', '.join(AGGREGATES)}.")
    person = _person(account_id)
    if person is None:
        return _no_person(account_id)
    rows = _store.table("measurements").find(lambda m: m["person_id"] == person["id"] and m["type"] == type_)
    latest = max((date.fromisoformat(m["date"]) for m in rows), default=None)
    window = _window(start, end, latest)
    if isinstance(window, HealthError):
        return window
    first, last = window
    rows = sorted((m for m in rows if first <= date.fromisoformat(m["date"]) <= last),
                  key=lambda m: m["timestamp"] or m["date"])
    unit, kind, whole = MEASUREMENT_TYPES[type_]
    spot = type_ in SPOT_TYPES
    places = 2 if type_ == "distance_km" else 1
    data = []
    if mode == "none":
        for m in rows:
            point = {"timestamp": m["timestamp"]} if spot else {"date": m["date"]}
            if type_ == "blood_pressure":
                point.update(systolic=_num(m["value"]), diastolic=_num(m["value_secondary"]))
            else:
                point["value"] = _round(m["value"], whole, places)
            data.append(point)
    else:
        buckets = {}
        for m in rows:
            day = date.fromisoformat(m["date"])
            key = day if mode == "day" else day - timedelta(days=day.weekday())
            buckets.setdefault(key, []).append(m)
        for key in sorted(buckets):
            group = buckets[key]
            count = len(group)
            point = {"date": key.isoformat(), "sample_count": count}

            def fold(values):
                total = sum(values)
                if kind == "sum":
                    return _round(total, whole, places)
                return round(total / count, 1)

            if type_ == "blood_pressure":
                point["systolic"] = fold([m["value"] for m in group])
                point["diastolic"] = fold([m["value_secondary"] for m in group])
            else:
                point["value"] = fold([m["value"] for m in group])
            data.append(point)
    return {"type": type_, "unit": unit, "aggregation": "none" if mode == "none" else kind,
            "interval": mode, "start": first.isoformat(), "end": last.isoformat(), "data": data}


# --- nutrition ----------------------------------------------------------------------

def _entry_view(e):
    view = {"id": e["id"], "logged_at": e["logged_at"], "meal": e["meal"], "food_name": e["food_name"],
            "serving": e["serving"], "calories_kcal": e["calories_kcal"]}
    for column in _NUTRIENTS:
        view[column] = _num(e[column])
    return view


def get_nutrition(account_id, start=None, end=None, meal=None):
    if meal is not None and meal not in MEALS:
        return _invalid(f"The parameter meal must be one of: {', '.join(MEALS)}.")
    person = _person(account_id)
    if person is None:
        return _no_person(account_id)
    rows = _store.table("nutrition_entries").find(lambda e: e["person_id"] == person["id"])
    latest = max((date.fromisoformat(e["logged_at"][:10]) for e in rows), default=None)
    window = _window(start, end, latest)
    if isinstance(window, HealthError):
        return window
    first, last = window
    rows = sorted((e for e in rows
                   if first <= date.fromisoformat(e["logged_at"][:10]) <= last and (meal is None or e["meal"] == meal)),
                  key=lambda e: e["logged_at"])
    totals = {}
    for e in rows:
        day = totals.setdefault(e["logged_at"][:10], {"date": e["logged_at"][:10], "calories_kcal": 0, "entries": 0,
                                                      **{c: 0 for c in _NUTRIENTS}})
        day["calories_kcal"] += e["calories_kcal"]
        day["entries"] += 1
        for column in _NUTRIENTS:
            day[column] += e[column]
    daily = []
    for key in sorted(totals):
        day = totals[key]
        for column in _NUTRIENTS:
            day[column] = _num(round(day[column], 1))
        daily.append(day)
    return {"start": first.isoformat(), "end": last.isoformat(), "meal": meal,
            "data": [_entry_view(e) for e in rows], "daily_totals": daily}


# --- sleep -----------------------------------------------------------------------------

def get_sleep(account_id, start=None, end=None):
    person = _person(account_id)
    if person is None:
        return _no_person(account_id)
    rows = _store.table("sleep_sessions").find(lambda s: s["person_id"] == person["id"])
    latest = max((date.fromisoformat(s["end"][:10]) for s in rows), default=None)
    window = _window(start, end, latest)
    if isinstance(window, HealthError):
        return window
    first, last = window
    rows = sorted((s for s in rows if first <= date.fromisoformat(s["end"][:10]) <= last), key=lambda s: s["end"])
    data = [{
        "id": s["id"], "start": s["start"], "end": s["end"], "duration_min": s["duration_min"],
        "time_in_bed_min": s["time_in_bed_min"], "efficiency_percent": s["efficiency_percent"],
        "stages": {"awake": s["awake_min"], "light": s["light_min"], "deep": s["deep_min"], "rem": s["rem_min"]},
        "source_device": s["source_device"],
    } for s in rows]
    return {"start": first.isoformat(), "end": last.isoformat(), "data": data}


# --- workouts ----------------------------------------------------------------------------

def get_workouts(account_id, start=None, end=None, type_=None):
    if type_ is not None and type_ not in WORKOUT_TYPES:
        return _invalid(f"The parameter type must be one of: {', '.join(WORKOUT_TYPES)}.")
    person = _person(account_id)
    if person is None:
        return _no_person(account_id)
    rows = _store.table("workouts").find(lambda w: w["person_id"] == person["id"])
    latest = max((date.fromisoformat(w["start"][:10]) for w in rows), default=None)
    window = _window(start, end, latest)
    if isinstance(window, HealthError):
        return window
    first, last = window
    rows = sorted((w for w in rows if first <= date.fromisoformat(w["start"][:10]) <= last
                   and (type_ is None or w["type"] == type_)), key=lambda w: w["start"])
    data = [{
        "id": w["id"], "type": w["type"], "start": w["start"], "end": w["end"], "duration_min": w["duration_min"],
        "distance_km": w["distance_km"], "active_energy_kcal": w["active_energy_kcal"],
        "avg_heart_rate": w["avg_heart_rate"], "max_heart_rate": w["max_heart_rate"],
        "elevation_gain_m": w["elevation_gain_m"], "notes": w["notes"],
    } for w in rows]
    return {"start": first.isoformat(), "end": last.isoformat(), "data": data}


_store.eager_load()
