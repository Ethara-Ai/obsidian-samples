"""Data access module for the Peloton mock service.

Peloton publishes no official public API. This mock follows the member API that
Peloton's own apps call and that open-source clients document
(api.onepeloton.com/api), for the five operations the connector needs: get the
profile, list workouts with a date filter, get one workout, get a workout's
performance summary, and list available classes with discipline and duration
filters. Every read is scoped to the member the presented token's connected
account holds.

Workouts carry their summary metrics; the performance graph's per-sample series
are synthesized from them deterministically, seeded by the workout id, so the
same workout always answers the same samples. Mock simplifications (also stated
in api_test_results.md): read-only, no social, leaderboard, schedule, program,
achievement or challenge routes, and no workout deletion.
"""

import math
import random
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent

sys.path.insert(0, str(DATA_DIR.parent))
from _mutable_store import get_store, read_seed_with_ctx  # noqa: E402
from _connector_auth import ConnectorAuth  # noqa: E402

_API = "peloton-api"
_store = get_store(_API)

CDT = timezone(timedelta(hours=-5))
DISCIPLINES = ("cycling", "strength", "yoga", "stretching", "meditation", "running", "walking")
JOINS = ("ride", "ride.instructor")
ZONE_BOUNDS = (0.0, 0.65, 0.75, 0.85, 0.95)


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


for _table, _file in (("users", "users.json"), ("instructors", "instructors.json"),
                      ("class_types", "class_types.json"), ("rides", "rides.json"), ("workouts", "workouts.json")):
    _store.register(_table, primary_key="id",
                    initial_loader=lambda f=_file, t=_table: [_strip_ctx(r) for r in _load(f, t)])

auth = ConnectorAuth(_API, store=_store, data_dir=DATA_DIR)

ERROR_CODES = {400: 10, 404: 20, 405: 30}


class PelotonError:
    """This mock's rendering of a Peloton error and its HTTP status."""

    def __init__(self, status, message, details=None):
        self.status = status
        self.body = {"status": status, "error_code": ERROR_CODES.get(status, status), "subcode": "",
                     "message": message, "details": details or {}}


def invalid(message, param=None):
    return PelotonError(400, message, {"param": param} if param else None)


def not_found(message):
    return PelotonError(404, message)


def _member(account_id):
    return _store.table("users").find_one(lambda r: r.get("owner_account_id") == account_id)


# --- profile ------------------------------------------------------------------------------------

def profile(account_id):
    user = _member(account_id)
    if user is None:
        return not_found("User not found")
    return {k: v for k, v in user.items() if k != "owner_account_id"}


# --- workouts -----------------------------------------------------------------------------------

def _joins(text):
    if text is None:
        return set()
    wanted = {part.strip() for part in text.split(",") if part.strip()}
    unknown = sorted(wanted - set(JOINS))
    if unknown:
        return invalid(f"joins accepts {', '.join(JOINS)}; got {', '.join(unknown)}", "joins")
    if "ride.instructor" in wanted:
        wanted.add("ride")
    return wanted


def ride_view(ride, with_instructor=False):
    view = dict(ride)
    if with_instructor:
        view["instructor"] = _store.table("instructors").get(ride["instructor_id"])
    return view


def workout_view(row, joins):
    metrics = row["metrics"]
    view = {"id": row["id"], "user_id": row["user_id"], "created_at": row["created_at"],
            "start_time": row["start_time"], "end_time": row["end_time"],
            "fitness_discipline": row["fitness_discipline"], "name": row["name"], "title": row["title"],
            "metrics_type": row["metrics_type"], "has_pedaling_metrics": row["has_pedaling_metrics"],
            "has_leaderboard_metrics": row["has_leaderboard_metrics"], "platform": row["platform"],
            "device_type": row["device_type"], "timezone": row["timezone"], "status": row["status"],
            "workout_type": row["workout_type"], "is_total_work_personal_record": row["is_total_work_personal_record"],
            "total_work": round(metrics.get("total_output_kj", 0.0) * 1000, 1),
            "leaderboard_rank": row["leaderboard_rank"], "total_leaderboard_users": row["total_leaderboard_users"],
            "ftp_info": row["ftp_info"], "effort_zones": row["effort_zones"]}
    if "ride" in joins:
        view["ride"] = ride_view(_store.table("rides").get(row["ride_id"]), "ride.instructor" in joins)
    return view


def _day(text, name, end):
    try:
        day = date.fromisoformat(text)
    except ValueError:
        return invalid(f"{name} must be a date (YYYY-MM-DD)", name)
    return int(datetime.combine(day, time.max if end else time.min, tzinfo=CDT).timestamp())


def _page(rows, limit, page, top):
    if not 1 <= limit <= top:
        return invalid(f"limit must be between 1 and {top}", "limit")
    if page < 0:
        return invalid("page must not be negative", "page")
    total = len(rows)
    page_count = max(1, math.ceil(total / limit))
    chunk = rows[page * limit:(page + 1) * limit]
    return {"chunk": chunk, "meta": {"total": total, "count": len(chunk), "limit": limit, "page": page,
                                     "page_count": page_count, "show_previous": page > 0,
                                     "show_next": (page + 1) * limit < total}}


def list_workouts(user_id, account_id, joins=None, limit=20, page=0, start_date=None, end_date=None):
    user = _member(account_id)
    if user is None or user["id"] != user_id:
        return not_found("User not found")
    wanted = _joins(joins)
    if isinstance(wanted, PelotonError):
        return wanted
    low = _day(start_date, "start_date", False) if start_date is not None else None
    high = _day(end_date, "end_date", True) if end_date is not None else None
    for bound in (low, high):
        if isinstance(bound, PelotonError):
            return bound
    if low is not None and high is not None and low > high:
        return invalid("start_date must not be later than end_date", "start_date")
    rows = [w for w in _store.table("workouts").find(lambda w: w["user_id"] == user_id)
            if (low is None or w["start_time"] >= low) and (high is None or w["start_time"] <= high)]
    rows.sort(key=lambda w: w["start_time"], reverse=True)
    paged = _page(rows, limit, page, 100)
    if isinstance(paged, PelotonError):
        return paged
    summary = {}
    for w in rows:
        summary[w["fitness_discipline"]] = summary.get(w["fitness_discipline"], 0) + 1
    return {"data": [workout_view(w, wanted) for w in paged["chunk"]], **paged["meta"], "summary": summary}


def _workout(workout_id, account_id):
    user = _member(account_id)
    row = _store.table("workouts").get(workout_id)
    if user is None or row is None or row["user_id"] != user["id"]:
        return None
    return row


def get_workout(workout_id, account_id, joins=None):
    row = _workout(workout_id, account_id)
    if row is None:
        return not_found("Workout not found")
    wanted = _joins(joins)
    if isinstance(wanted, PelotonError):
        return wanted
    return workout_view(row, wanted)


# --- performance graph --------------------------------------------------------------------------

def _shape(rng, count, every_n):
    """A relative effort curve: warm-up ramp, intervals around 1.0, cool-down."""
    period = rng.uniform(120, 300)
    out = []
    for i in range(count):
        t = i / max(1, count - 1)
        level = 1.0 + 0.22 * math.sin(2 * math.pi * i * every_n / period) + rng.uniform(-0.08, 0.08)
        if t < 0.15:
            level *= 0.6 + 0.4 * t / 0.15
        elif t > 0.9:
            level *= 1.0 - 0.45 * (t - 0.9) / 0.1
        out.append(max(0.05, level))
    return out


def _series(shape, average, peak, digits=0):
    mean = sum(shape) / len(shape)
    values = [min(peak, s / mean * average) for s in shape]
    values[max(range(len(values)), key=lambda i: values[i])] = peak
    return [round(v, digits) if digits else int(round(v)) for v in values]


def _metric(name, unit, slug, values, average, peak):
    return {"display_name": name, "display_unit": unit, "max_value": peak, "average_value": average,
            "values": values, "slug": slug}


def _zones(row, user):
    durations = (row["effort_zones"] or {}).get("heart_rate_zone_durations")
    if not durations:
        return None
    top = user["customized_max_heart_rate"] or user["default_max_heart_rate"]
    edges = [round(b * top) for b in ZONE_BOUNDS] + [top]
    return [{"display_name": f"Zone {i + 1}", "slug": f"zone{i + 1}", "min_value": edges[i],
             "max_value": edges[i + 1], "range": f"{edges[i]}-{edges[i + 1]} bpm",
             "duration": durations[f"heart_rate_z{i + 1}_duration"]} for i in range(5)]


def performance_graph(workout_id, account_id, every_n=5):
    row = _workout(workout_id, account_id)
    if row is None:
        return not_found("Workout not found")
    if not 1 <= every_n <= 300:
        return invalid("every_n must be between 1 and 300", "every_n")
    user = _member(account_id)
    m = row["metrics"]
    duration = row["end_time"] - row["start_time"]
    count = math.ceil(duration / every_n)
    rng = random.Random(int(row["id"][:12], 16))
    shape = _shape(rng, count, every_n)
    metrics, averages, summaries = [], [], []
    if row["fitness_discipline"] == "cycling":
        output = _series(shape, m["avg_output"], m["max_output"])
        lean = [s ** 0.35 for s in shape]
        metrics += [_metric("Output", "watts", "output", output, m["avg_output"], m["max_output"]),
                    _metric("Cadence", "rpm", "cadence", _series(lean, m["avg_cadence"], m["max_cadence"]),
                            m["avg_cadence"], m["max_cadence"]),
                    _metric("Resistance", "%", "resistance", _series(lean, m["avg_resistance"], m["max_resistance"]),
                            m["avg_resistance"], m["max_resistance"]),
                    _metric("Speed", "mph", "speed", _series(lean, m["avg_speed"], m["max_speed"], 1),
                            m["avg_speed"], m["max_speed"])]
        averages = [{"display_name": "Avg Output", "display_unit": "watts", "value": m["avg_output"],
                     "slug": "avg_output"},
                    {"display_name": "Avg Cadence", "display_unit": "rpm", "value": m["avg_cadence"],
                     "slug": "avg_cadence"},
                    {"display_name": "Avg Resistance", "display_unit": "%", "value": m["avg_resistance"],
                     "slug": "avg_resistance"},
                    {"display_name": "Avg Speed", "display_unit": "mph", "value": m["avg_speed"],
                     "slug": "avg_speed"}]
        summaries.append({"display_name": "Total Output", "display_unit": "kj", "value": round(m["total_output_kj"]),
                          "slug": "total_output"})
    elif "avg_speed" in m:
        speed = _series([s ** 0.3 for s in shape], m["avg_speed"], round(m["avg_speed"] * 1.25, 1), 1)
        metrics.append(_metric("Speed", "mph", "speed", speed, m["avg_speed"], round(m["avg_speed"] * 1.25, 1)))
        averages.append({"display_name": "Avg Speed", "display_unit": "mph", "value": m["avg_speed"],
                         "slug": "avg_speed"})
    if "distance_mi" in m:
        summaries.append({"display_name": "Distance", "display_unit": "mi", "value": m["distance_mi"],
                          "slug": "distance"})
    summaries.append({"display_name": "Calories", "display_unit": "kcal", "value": m["calories"], "slug": "calories"})
    if m.get("avg_heart_rate"):
        lagged = [0.82 + 0.18 * sum(shape[max(0, i - 6):i + 1]) / len(shape[max(0, i - 6):i + 1]) for i in range(count)]
        heart = _metric("Heart Rate", "bpm", "heart_rate", _series(lagged, m["avg_heart_rate"], m["max_heart_rate"]),
                        m["avg_heart_rate"], m["max_heart_rate"])
        heart["zones"] = _zones(row, user)
        metrics.append(heart)
    return {"duration": duration, "every_n": every_n, "is_class_plan_shown": row["fitness_discipline"] == "cycling",
            "seconds_since_pedaling_start": [i * every_n for i in range(count)] if metrics else [],
            "average_summaries": averages,
            "summaries": summaries, "metrics": metrics, "has_apple_watch_metrics": False, "location_data": [],
            "effort_zones": row["effort_zones"]}


# --- classes ------------------------------------------------------------------------------------

def archived_classes(browse_category=None, duration=None, instructor_id=None, limit=18, page=0):
    if browse_category is not None and browse_category not in DISCIPLINES:
        return invalid(f"browse_category must be one of {', '.join(DISCIPLINES)}", "browse_category")
    durations = None
    if duration is not None:
        try:
            durations = {int(part) for part in duration.split(",") if part.strip()}
        except ValueError:
            return invalid("duration must be a length in seconds, or several separated by commas", "duration")
    rows = [r for r in _store.table("rides").rows()
            if (browse_category is None or r["fitness_discipline"] == browse_category)
            and (durations is None or r["duration"] in durations)
            and (instructor_id is None or r["instructor_id"] == instructor_id)]
    rows.sort(key=lambda r: r["original_air_time"], reverse=True)
    paged = _page(rows, limit, page, 100)
    if isinstance(paged, PelotonError):
        return paged
    chunk = paged["chunk"]
    instructor_ids = sorted({r["instructor_id"] for r in chunk})
    type_ids = sorted({t for r in chunk for t in r["class_type_ids"]})
    return {"data": [ride_view(r) for r in chunk], **paged["meta"],
            "instructors": [_store.table("instructors").get(i) for i in instructor_ids],
            "class_types": [_store.table("class_types").get(t) for t in type_ids]}


_store.eager_load()
