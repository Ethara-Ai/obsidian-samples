"""Data access module for the Granola mock service.

Granola publishes no widely documented public REST API, so this mock serves a
plain REST shape of its own for the three operations the connector needs: list
meeting notes with a date filter, get one note with its summary, action items
and transcript, and search notes by text. Every read is scoped to the notes the
presented token's connected account owns.

A note is one row carrying its meeting's title, folder, start and end, the ids
of its attendees, its generated summary (Markdown) and its transcript as a list
of timed utterances. Action items are rows of their own, each tied to a note and
an assignee. People are the attendee directory. Mock simplifications (also
stated in api_test_results.md): no writes, no folders or sharing, no templates,
and no live recording.
"""

import base64
import sys
from datetime import date, datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent

sys.path.insert(0, str(DATA_DIR.parent))
from _mutable_store import get_store, opt_bool, read_seed_with_ctx  # noqa: E402
from _connector_auth import ConnectorAuth  # noqa: E402

_API = "granola-api"
_store = get_store(_API)

LIMIT_MAX = 100


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _coerce_note(r):
    out = _strip_ctx(r)
    out["attendee_ids"] = list(out.get("attendee_ids") or [])
    out["transcript"] = list(out.get("transcript") or [])
    out["summary"] = out.get("summary") or ""
    return out


def _coerce_action(r):
    out = _strip_ctx(r)
    out["completed"] = opt_bool(out, "completed")
    out["due_date"] = out.get("due_date") or None
    return out


_store.register("people", primary_key="id",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("people.json", "people")])
_store.register("notes", primary_key="id",
                initial_loader=lambda: [_coerce_note(r) for r in _load("notes.json", "notes")],
                row_coercer=_coerce_note)
_store.register("action_items", primary_key="id",
                initial_loader=lambda: [_coerce_action(r) for r in _load("action_items.json", "action_items")],
                row_coercer=_coerce_action)

auth = ConnectorAuth(_API, store=_store, data_dir=DATA_DIR)


class GranolaError:
    """This mock's error body, ``{"error": {"code", "message", "param"}}``, and its HTTP status."""

    def __init__(self, status, code, message, param=None):
        self.status = status
        error = {"code": code, "message": message}
        if param is not None:
            error["param"] = param
        self.body = {"error": error}


def invalid(param, message):
    return GranolaError(400, "invalid_request", message, param)


def not_found(note_id):
    return GranolaError(404, "not_found", f"No note with id '{note_id}' exists in this workspace.")


# --- rendering ----------------------------------------------------------------------------------

def _person(person_id):
    p = _store.table("people").get(person_id) or {}
    return {"id": person_id, "name": p.get("name", ""), "email": p.get("email", ""),
            "organization": p.get("organization", "")}


def _summary_view(row):
    actions = _store.table("action_items").find(lambda a: a["note_id"] == row["id"])
    return {"id": row["id"], "title": row["title"], "folder": row["folder"], "started_at": row["started_at"],
            "ended_at": row["ended_at"], "attendees": [_person(p) for p in row["attendee_ids"]],
            "action_item_count": len(actions), "open_action_item_count": sum(1 for a in actions if not a["completed"]),
            "updated_at": row["updated_at"]}


def _action_view(a):
    view = {"id": a["id"], "text": a["text"], "assignee": _person(a["assignee_id"]) if a.get("assignee_id") else None,
            "due_date": a["due_date"], "completed": a["completed"]}
    return view


def _full_view(row):
    view = _summary_view(row)
    actions = sorted(_store.table("action_items").find(lambda a: a["note_id"] == row["id"]),
                     key=lambda a: a["position"])
    names = {p: _person(p)["name"] for p in row["attendee_ids"]}
    view.update({"calendar_event": row.get("calendar_event"), "summary": row["summary"],
                 "action_items": [_action_view(a) for a in actions],
                 "transcript": [{"speaker": names.get(u["speaker_id"]) or _person(u["speaker_id"])["name"],
                                 "speaker_id": u["speaker_id"], "start": u["start"], "text": u["text"]}
                                for u in row["transcript"]],
                 "created_at": row["created_at"]})
    return view


# --- paging -------------------------------------------------------------------------------------

def _cursor(offset):
    return base64.urlsafe_b64encode(f"gn:{offset}".encode()).decode().rstrip("=")


def _offset(cursor):
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        prefix, _, value = raw.partition(":")
        if prefix != "gn" or not value.isdigit():
            raise ValueError(raw)
        return int(value)
    except (ValueError, UnicodeDecodeError):
        return None


def _page(items, limit, cursor, key):
    if not 1 <= limit <= LIMIT_MAX:
        return invalid("limit", f"limit must be between 1 and {LIMIT_MAX}.")
    start = 0
    if cursor is not None:
        start = _offset(cursor)
        if start is None:
            return invalid("cursor", "cursor is not a cursor this API returned.")
    window = items[start:start + limit]
    more = start + limit < len(items)
    return {key: window, "has_more": more, "next_cursor": _cursor(start + limit) if more else None}


def _day(text, name):
    try:
        return date.fromisoformat(text)
    except (TypeError, ValueError):
        return invalid(name, f"{name} must be a date in YYYY-MM-DD form.")


def _local_day(stamp):
    return datetime.fromisoformat(stamp).date()


def _owned(account_id):
    rows = _store.table("notes").find(lambda r: r.get("owner_account_id") == account_id)
    return sorted(rows, key=lambda r: r["started_at"], reverse=True)


# --- operations ---------------------------------------------------------------------------------

def list_notes(account_id, start_date=None, end_date=None, limit=20, cursor=None):
    bounds = {}
    for name, value in (("start_date", start_date), ("end_date", end_date)):
        if value is not None:
            day = _day(value, name)
            if isinstance(day, GranolaError):
                return day
            bounds[name] = day
    if "start_date" in bounds and "end_date" in bounds and bounds["start_date"] > bounds["end_date"]:
        return invalid("end_date", "end_date must not be before start_date.")
    rows = [r for r in _owned(account_id)
            if ("start_date" not in bounds or _local_day(r["started_at"]) >= bounds["start_date"])
            and ("end_date" not in bounds or _local_day(r["started_at"]) <= bounds["end_date"])]
    return _page([_summary_view(r) for r in rows], limit, cursor, "notes")


def get_note(note_id, account_id):
    row = _store.table("notes").get(note_id)
    if row is None or row.get("owner_account_id") != account_id:
        return not_found(note_id)
    return _full_view(row)


def _snippet(text, term):
    low = text.lower()
    at = low.find(term)
    start = max(0, at - 60)
    end = min(len(text), at + len(term) + 60)
    return ("..." if start else "") + text[start:end].replace("\n", " ") + ("..." if end < len(text) else "")


def search_notes(account_id, q, limit=20, cursor=None):
    query = (q or "").strip().lower()
    if not query:
        return invalid("q", "q is required and must not be empty.")
    terms = query.split()
    results = []
    for row in _owned(account_id):
        actions = _store.table("action_items").find(lambda a: a["note_id"] == row["id"])
        fields = [("title", row["title"]), ("summary", row["summary"])]
        fields += [("action_item", a["text"]) for a in actions]
        fields += [("transcript", u["text"]) for u in row["transcript"]]
        haystack = " ".join(text.lower() for _, text in fields)
        if not all(t in haystack for t in terms):
            continue
        matches = []
        for field, text in fields:
            hit = next((t for t in terms if t in text.lower()), None)
            if hit is not None:
                matches.append({"field": field, "snippet": _snippet(text, hit)})
        results.append({"note": _summary_view(row), "matches": matches[:5]})
    return _page(results, limit, cursor, "results")


_store.eager_load()
