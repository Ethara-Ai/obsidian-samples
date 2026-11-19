"""Data access module for the Withings mock service.

Follows the Withings public API's action-style requests (wbsapi.withings.net):
one POST per webservice with `action` and its parameters as form fields, and
`{"status", "body"}` answers. Four operations: body measures (weight, body fat,
blood pressure) for a date range (`/measure` getmeas), daily activity
(`/v2/measure` getactivity), sleep summaries (`/v2/sleep` getsummary), and the
account's devices (`/v2/user` getdevice). Every read is scoped to the account
the presented token's connected account holds.

Mock simplifications (also stated in api_test_results.md): read-only, no
intraday activity, workouts, sleep stages, heart (ECG) or notification
webservices, and fixed page sizes.
"""

import sys
from datetime import date, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent

sys.path.insert(0, str(DATA_DIR.parent))
import _mock_clock  # noqa: E402
from _mutable_store import get_store, read_seed_with_ctx  # noqa: E402
from _connector_auth import ConnectorAuth  # noqa: E402

_API = "withings-api"
_store = get_store(_API)

TIME_ZONE = "America/Chicago"
MEASURE_PAGE, ACTIVITY_PAGE, SLEEP_PAGE = 100, 50, 50
# webservice path -> (its one action, the form parameters that action takes besides `action`)
ACTIONS = {
    "/measure": ("getmeas", ("meastype", "meastypes", "category", "startdate", "enddate", "lastupdate", "offset")),
    "/v2/measure": ("getactivity", ("startdateymd", "enddateymd", "lastupdate", "offset", "data_fields")),
    "/v2/sleep": ("getsummary", ("startdateymd", "enddateymd", "lastupdate", "offset", "data_fields")),
    "/v2/user": ("getdevice", ()),
}
ACTIVITY_IDENTITY = ("date", "timezone", "deviceid", "hash_deviceid", "brand", "is_tracker")
ACTIVITY_FIELDS = ("steps", "distance", "elevation", "soft", "moderate", "intense", "active", "calories",
                   "totalcalories", "hr_average", "hr_min", "hr_max", "hr_zone_0", "hr_zone_1", "hr_zone_2",
                   "hr_zone_3")
SLEEP_FIELDS = ("total_timeinbed", "total_sleep_time", "sleep_efficiency", "sleep_latency", "wakeup_latency",
                "wakeupduration", "wakeupcount", "waso", "lightsleepduration", "deepsleepduration",
                "remsleepduration", "durationtosleep", "durationtowakeup", "hr_average", "hr_min", "hr_max",
                "rr_average", "rr_min", "rr_max", "snoring", "snoringepisodecount", "sleep_score",
                "breathing_disturbances_intensity", "apnea_hypopnea_index", "nb_rem_episodes", "out_of_bed_count")


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


_store.register("devices", primary_key="deviceid",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("devices.json", "devices")])
_store.register("measuregrps", primary_key="grpid",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("measuregrps.json", "measuregrps")])
_store.register("sleep", primary_key="id",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("sleep.json", "sleep")])
_store.register("activity", primary_key="date",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("activity.json", "activity")])

auth = ConnectorAuth(_API, store=_store, data_dir=DATA_DIR)


class WithingsError:
    """This mock's rendering of a Withings error: a nonzero `status` in the body, HTTP 200 as Withings sends."""

    def __init__(self, status, message, http_status=200):
        self.status = http_status
        self.body = {"status": status, "body": {}, "error": message}


def invalid(message):
    return WithingsError(503, f"Invalid Params: {message}")


def wrong_action(message="Wrong action or wrong webservice", http_status=200):
    return WithingsError(2554, message, http_status)


def _ok(body):
    return {"status": 0, "body": body}


def _int(params, name):
    if name not in params:
        return None
    try:
        return int(params[name])
    except ValueError:
        return invalid(f"{name} must be an integer")


def _ymd(params, name):
    if name not in params:
        return None
    try:
        return date.fromisoformat(params[name])
    except ValueError:
        return invalid(f"{name} must be a date (YYYY-MM-DD)")


def _fields(params, allowed):
    if "data_fields" not in params:
        return allowed
    wanted = [f.strip() for f in params["data_fields"].split(",") if f.strip()]
    unknown = [f for f in wanted if f not in allowed]
    if unknown or not wanted:
        return invalid(f"data_fields accepts {', '.join(allowed)}; got {', '.join(unknown) or 'nothing'}")
    return tuple(wanted)


def _window(params):
    """startdateymd and enddateymd together, or lastupdate: what the v2 webservices require."""
    start, end, since = _ymd(params, "startdateymd"), _ymd(params, "enddateymd"), _int(params, "lastupdate")
    for value in (start, end, since):
        if isinstance(value, WithingsError):
            return value
    if (start is None) != (end is None):
        return invalid("startdateymd and enddateymd go together")
    if start is None and since is None:
        return invalid("send startdateymd and enddateymd, or lastupdate")
    if start is not None and since is not None:
        return invalid("send startdateymd and enddateymd, or lastupdate, not both")
    if start is not None and start > end:
        return invalid("startdateymd must not be later than enddateymd")
    return start, end, since


def _page(rows, offset, size):
    if offset is not None and offset < 0:
        return invalid("offset must not be negative")
    first = offset or 0
    chunk = rows[first:first + size]
    more = first + size < len(rows)
    return chunk, more, first + size if more else 0


# --- getmeas ------------------------------------------------------------------------------------

def getmeas(account_id, params):
    meastype, start, end, since, offset, category = (_int(params, n) for n in (
        "meastype", "startdate", "enddate", "lastupdate", "offset", "category"))
    for value in (meastype, start, end, since, offset, category):
        if isinstance(value, WithingsError):
            return value
    types = None
    if meastype is not None:
        types = {meastype}
    if "meastypes" in params:
        try:
            types = (types or set()) | {int(t) for t in params["meastypes"].split(",") if t.strip()}
        except ValueError:
            return invalid("meastypes must be measure type numbers separated by commas")
    if category not in (None, 1, 2):
        return invalid("category must be 1 (real measures) or 2 (user objectives)")
    if since is not None and (start is not None or end is not None):
        return invalid("send startdate and enddate, or lastupdate, not both")
    rows = []
    for group in _store.table("measuregrps").find(lambda g: g.get("owner_account_id") == account_id):
        if category is not None and group["category"] != category:
            continue
        if (start is not None and group["date"] < start) or (end is not None and group["date"] > end):
            continue
        if since is not None and group["modified"] < since:
            continue
        measures = [m for m in group["measures"] if types is None or m["type"] in types]
        if measures:
            rows.append({**{k: v for k, v in group.items() if k != "owner_account_id"}, "measures": measures})
    rows.sort(key=lambda g: (g["date"], g["grpid"]), reverse=True)
    paged = _page(rows, offset, MEASURE_PAGE)
    if isinstance(paged, WithingsError):
        return paged
    chunk, more, next_offset = paged
    return _ok({"updatetime": int(_mock_clock.now(timezone.utc).timestamp()), "timezone": TIME_ZONE,
                "measuregrps": chunk, "more": int(more), "offset": next_offset})


# --- getactivity --------------------------------------------------------------------------------

def getactivity(account_id, params):
    window = _window(params)
    if isinstance(window, WithingsError):
        return window
    fields = _fields(params, ACTIVITY_FIELDS)
    offset = _int(params, "offset")
    for value in (fields, offset):
        if isinstance(value, WithingsError):
            return value
    start, end, since = window
    rows = [a for a in _store.table("activity").find(lambda a: a.get("owner_account_id") == account_id)
            if (start is None or start <= date.fromisoformat(a["date"]) <= end)
            and (since is None or a["modified"] >= since)]
    rows.sort(key=lambda a: a["date"])
    paged = _page(rows, offset, ACTIVITY_PAGE)
    if isinstance(paged, WithingsError):
        return paged
    chunk, more, next_offset = paged
    keep = ACTIVITY_IDENTITY + tuple(fields)
    return _ok({"activities": [{k: a[k] for k in keep} for a in chunk], "more": more, "offset": next_offset})


# --- sleep getsummary ---------------------------------------------------------------------------

def getsummary(account_id, params):
    window = _window(params)
    if isinstance(window, WithingsError):
        return window
    fields = _fields(params, SLEEP_FIELDS)
    offset = _int(params, "offset")
    for value in (fields, offset):
        if isinstance(value, WithingsError):
            return value
    start, end, since = window
    rows = [s for s in _store.table("sleep").find(lambda s: s.get("owner_account_id") == account_id)
            if (start is None or start <= date.fromisoformat(s["date"]) <= end)
            and (since is None or s["modified"] >= since)]
    rows.sort(key=lambda s: s["startdate"])
    paged = _page(rows, offset, SLEEP_PAGE)
    if isinstance(paged, WithingsError):
        return paged
    chunk, more, next_offset = paged
    series = [{**{k: v for k, v in s.items() if k not in ("owner_account_id", "data")},
               "data": {k: s["data"][k] for k in fields}} for s in chunk]
    return _ok({"series": series, "more": more, "offset": next_offset})


# --- getdevice ----------------------------------------------------------------------------------

def getdevice(account_id, _params):
    rows = sorted(_store.table("devices").find(lambda d: d.get("owner_account_id") == account_id),
                  key=lambda d: d["first_session_date"])
    return _ok({"devices": [{k: v for k, v in d.items() if k != "owner_account_id"} for d in rows]})


HANDLERS = {"getmeas": getmeas, "getactivity": getactivity, "getsummary": getsummary, "getdevice": getdevice}


def dispatch(path, account_id, params):
    action, accepted = ACTIONS[path]
    if "action" not in params:
        return invalid("action is required")
    if params["action"] != action:
        return wrong_action(f"Wrong action or wrong webservice: {path} takes action={action}")
    unknown = sorted(set(params) - set(accepted) - {"action"})
    if unknown:
        return invalid(f"{', '.join(unknown)} is not a parameter of {action}")
    return HANDLERS[action](account_id, {k: v for k, v in params.items() if k != "action"})


_store.eager_load()
