"""Data access module for the Function Health mock service.

Function Health publishes no public API, so this mock serves a plain REST
shape of its own (see README.md) for the four operations the connector needs:
list lab visits, list a visit's biomarker results with their in-range or
out-of-range status, get one biomarker's history over time, and list
recommendations. Every read is scoped to the member the presented token's
connected account holds.

A result names its biomarker, value, unit, reference range and status; the
biomarker catalog carries the names, categories, units and ranges. Mock
simplifications (also stated in api_test_results.md): read-only, no booking,
no clinician notes, no optimal ranges or biological age, and no uploads of
outside lab results.
"""

import base64
import sys
from datetime import date, datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent

sys.path.insert(0, str(DATA_DIR.parent))
from _mutable_store import get_store, read_seed_with_ctx  # noqa: E402
from _connector_auth import ConnectorAuth  # noqa: E402

_API = "function-health-api"
_store = get_store(_API)

VISIT_STATUSES = ("completed", "scheduled")
RESULT_STATUSES = ("in_range", "out_of_range")
REC_STATUSES = ("active", "completed")
REC_CATEGORIES = ("nutrition", "supplements", "exercise", "sleep", "lifestyle", "follow_up")
CATEGORY_ORDER = ("Heart", "Metabolic", "Kidney", "Liver", "Thyroid", "Nutrients", "Blood", "Electrolytes",
                  "Hormones", "Immune", "Pancreas", "Toxins", "Urine")


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


for _table, _file in (("biomarkers", "biomarkers.json"), ("visits", "visits.json"), ("results", "results.json"),
                      ("recommendations", "recommendations.json")):
    _store.register(_table, primary_key="id",
                    initial_loader=lambda f=_file, t=_table: [_strip_ctx(r) for r in _load(f, t)])

auth = ConnectorAuth(_API, store=_store, data_dir=DATA_DIR)


class FunctionHealthError:
    """This mock's error (``{"error": {"code", "message", "param"}}``) and its HTTP status."""

    def __init__(self, status, code, message, param=None):
        self.status = status
        self.body = {"error": {"code": code, "message": message, "param": param}}


def invalid(message, param=None):
    return FunctionHealthError(400, "invalid_parameter", message, param)


def not_found(message):
    return FunctionHealthError(404, "not_found", message)


def _cursor(offset):
    return base64.urlsafe_b64encode(f"fh:{offset}".encode()).decode().rstrip("=")


def _offset(cursor):
    if cursor is None:
        return 0
    try:
        text = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        prefix, value = text.split(":")
        offset = int(value)
        if prefix != "fh" or offset < 0:
            raise ValueError
        return offset
    except (ValueError, UnicodeDecodeError):
        return invalid("cursor is not one this API returned", "cursor")


def _page(rows, limit, cursor, top):
    if not 1 <= limit <= top:
        return invalid(f"limit must be between 1 and {top}", "limit")
    start = _offset(cursor)
    if isinstance(start, FunctionHealthError):
        return start
    chunk = rows[start:start + limit]
    return chunk, _cursor(start + limit) if start + limit < len(rows) else None


def _choice(value, allowed, param):
    if value is not None and value not in allowed:
        return invalid(f"{param} must be one of {', '.join(allowed)}", param)
    return None


def _strip(row):
    return {k: v for k, v in row.items() if k != "owner_account_id"}


def biomarker_view(row):
    return {k: v for k, v in row.items() if k != "digits"}


# --- visits -------------------------------------------------------------------------------------

def list_visits(account_id, status=None, limit=20, cursor=None):
    error = _choice(status, VISIT_STATUSES, "status")
    if error:
        return error
    rows = [v for v in _store.table("visits").find(lambda v: v.get("owner_account_id") == account_id)
            if status is None or v["status"] == status]
    rows.sort(key=lambda v: v["scheduled_for"], reverse=True)
    paged = _page(rows, limit, cursor, 50)
    if isinstance(paged, FunctionHealthError):
        return paged
    chunk, next_cursor = paged
    return {"visits": [_strip(v) for v in chunk], "next_cursor": next_cursor}


def _visit(visit_id, account_id):
    row = _store.table("visits").get(visit_id)
    if row is None or row.get("owner_account_id") != account_id:
        return None
    return row


def result_view(row, marker):
    return {"id": row["id"], "visit_id": row["visit_id"], "biomarker_id": row["biomarker_id"], "name": marker["name"],
            "category": marker["category"], "value": row["value"], "value_text": row["value_text"],
            "unit": marker["unit"], "reference_range": marker["reference_range"], "status": row["status"],
            "flag": row["flag"], "collected_at": row["collected_at"]}


def visit_results(visit_id, account_id, status=None, category=None, limit=100, cursor=None):
    visit = _visit(visit_id, account_id)
    if visit is None:
        return not_found(f"no visit {visit_id} for this member")
    error = _choice(status, RESULT_STATUSES, "status") or _choice(category, CATEGORY_ORDER, "category")
    if error:
        return error
    if visit["status"] != "completed":
        return FunctionHealthError(409, "results_not_ready",
                                   f"visit {visit_id} is scheduled for {visit['scheduled_for']}; results follow the draw")
    markers = {b["id"]: b for b in _store.table("biomarkers").rows()}
    rows = [r for r in _store.table("results").find(lambda r: r["visit_id"] == visit_id)
            if (status is None or r["status"] == status)
            and (category is None or markers[r["biomarker_id"]]["category"] == category)]
    rows.sort(key=lambda r: (CATEGORY_ORDER.index(markers[r["biomarker_id"]]["category"]),
                             markers[r["biomarker_id"]]["name"]))
    paged = _page(rows, limit, cursor, 200)
    if isinstance(paged, FunctionHealthError):
        return paged
    chunk, next_cursor = paged
    return {"visit": _strip(visit), "results": [result_view(r, markers[r["biomarker_id"]]) for r in chunk],
            "next_cursor": next_cursor}


# --- biomarker history --------------------------------------------------------------------------

def _date(text, param):
    try:
        return date.fromisoformat(text)
    except ValueError:
        return invalid(f"{param} must be a date (YYYY-MM-DD)", param)


def biomarker_history(biomarker_id, account_id, start_date=None, end_date=None):
    marker = _store.table("biomarkers").get(biomarker_id)
    if marker is None:
        return not_found(f"no biomarker {biomarker_id}")
    low = _date(start_date, "start_date") if start_date is not None else None
    high = _date(end_date, "end_date") if end_date is not None else None
    for bound in (low, high):
        if isinstance(bound, FunctionHealthError):
            return bound
    if low is not None and high is not None and low > high:
        return invalid("start_date must not be later than end_date", "start_date")
    mine = {v["id"] for v in _store.table("visits").find(lambda v: v.get("owner_account_id") == account_id)}

    def day(row):
        return datetime.fromisoformat(row["collected_at"].replace("Z", "+00:00")).astimezone(timezone.utc).date()

    rows = [r for r in _store.table("results").find(lambda r: r["biomarker_id"] == biomarker_id)
            if r["visit_id"] in mine and (low is None or day(r) >= low) and (high is None or day(r) <= high)]
    rows.sort(key=lambda r: r["collected_at"])
    history = [{"visit_id": r["visit_id"], "collected_at": r["collected_at"], "value": r["value"],
                "value_text": r["value_text"], "status": r["status"], "flag": r["flag"]} for r in rows]
    change = None
    if len(history) >= 2 and history[-1]["value"] is not None and history[-2]["value"] is not None:
        before, after = history[-2]["value"], history[-1]["value"]
        digits = marker["digits"] or 0
        change = {"value": round(after - before, digits) if digits else int(round(after - before)),
                  "percent": round((after - before) / before * 100, 1) if before else None}
    return {"biomarker": biomarker_view(marker), "history": history, "latest": history[-1] if history else None,
            "change_from_previous": change}


# --- recommendations ----------------------------------------------------------------------------

def list_recommendations(account_id, category=None, visit_id=None, status=None):
    error = _choice(category, REC_CATEGORIES, "category") or _choice(status, REC_STATUSES, "status")
    if error:
        return error
    if visit_id is not None and _visit(visit_id, account_id) is None:
        return not_found(f"no visit {visit_id} for this member")
    rows = [r for r in _store.table("recommendations").find(lambda r: r.get("owner_account_id") == account_id)
            if (category is None or r["category"] == category) and (visit_id is None or r["visit_id"] == visit_id)
            and (status is None or r["status"] == status)]
    rows.sort(key=lambda r: r["created_at"], reverse=True)
    return {"recommendations": [_strip(r) for r in rows]}


_store.eager_load()
