"""Data access module for the Phone mock service.

The client names a Phone connector without describing it, so the operation set
here is an assumption, stated in README.md: list recent calls, list text
conversations, list the messages in a conversation, send a text message, and
place a call, which records an outgoing call. The shape is a plain REST one of
this mock's own. Every read and write is scoped to the phone line the
presented token's connected account owns.

Calls carry their direction, the other party's number, status (answered,
missed, declined, no_answer, or placed for a call this mock records), duration
and whether a voicemail was left. Text conversations are one row per number,
messages one row each. The address book only names numbers; it has no route of
its own. Mock simplifications (also stated in api_test_results.md): no real
calling, no voicemail playback, no MMS, group texts, blocking or deleting.
"""

import base64
import re
import secrets
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent

sys.path.insert(0, str(DATA_DIR.parent))
import _mock_clock  # noqa: E402
from _mutable_store import get_store, opt_bool, read_seed_with_ctx  # noqa: E402
from _connector_auth import ConnectorAuth  # noqa: E402

_API = "phone-api"
_store = get_store(_API)

CDT = timezone(timedelta(hours=-5))
NUMBER = re.compile(r"^\+[1-9]\d{6,14}$")
CALL_STATUSES = ("answered", "missed", "declined", "no_answer", "placed")
LIMIT_MAX = 100
TEXT_LIMIT = 1600


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _coerce_message(r):
    out = _strip_ctx(r)
    out["read"] = opt_bool(out, "read", default=True)
    return out


for _table, _file in (("lines", "lines.json"), ("contacts", "contacts.json"), ("calls", "calls.json"),
                      ("conversations", "conversations.json")):
    _store.register(_table, primary_key="id",
                    initial_loader=(lambda f=_file, t=_table: [_strip_ctx(r) for r in _load(f, t)]))
_store.register("messages", primary_key="id",
                initial_loader=lambda: [_coerce_message(r) for r in _load("messages.json", "messages")],
                row_coercer=_coerce_message)

auth = ConnectorAuth(_API, store=_store, data_dir=DATA_DIR)


class PhoneError:
    """This mock's error body, ``{"error": {"code", "message", "param"}}``, and its HTTP status."""

    def __init__(self, status, code, message, param=None):
        self.status = status
        error = {"code": code, "message": message}
        if param is not None:
            error["param"] = param
        self.body = {"error": error}


def invalid(param, message):
    return PhoneError(400, "invalid_request", message, param)


def not_found(what, ident):
    return PhoneError(404, "not_found", f"No {what} with id '{ident}' on this line.")


def _now():
    return _mock_clock.now(timezone.utc).astimezone(CDT).replace(microsecond=0)


# --- lookup and rendering -----------------------------------------------------------------------

def _line(account_id):
    return _store.table("lines").find_one(lambda r: r.get("owner_account_id") == account_id)


def _contact(account_id, number):
    row = _store.table("contacts").find_one(
        lambda r: r.get("owner_account_id") == account_id and r["number"] == number)
    if row is None:
        return None
    return {"name": row["name"], "organization": row["organization"], "label": row["label"]}


def _call_view(row, account_id):
    return {"id": row["id"], "direction": row["direction"], "number": row["number"],
            "contact": _contact(account_id, row["number"]), "status": row["status"],
            "duration_seconds": row["duration_seconds"], "voicemail_left": row["voicemail_left"],
            "started_at": row["started_at"]}


def _messages(conversation_id):
    return sorted(_store.table("messages").find(lambda m: m["conversation_id"] == conversation_id),
                  key=lambda m: m["sent_at"], reverse=True)


def _conversation_view(row, account_id):
    rows = _messages(row["id"])
    return {"id": row["id"], "number": row["number"], "contact": _contact(account_id, row["number"]),
            "last_message_at": row["last_message_at"], "snippet": rows[0]["body"][:120] if rows else "",
            "message_count": len(rows), "unread_count": sum(1 for m in rows if not m["read"])}


def _message_view(row, line_number, number):
    inbound = row["direction"] == "inbound"
    return {"id": row["id"], "conversation_id": row["conversation_id"], "direction": row["direction"],
            "from": number if inbound else line_number, "to": line_number if inbound else number,
            "body": row["body"], "sent_at": row["sent_at"], "status": row["status"], "read": row["read"]}


def _cursor(offset):
    return base64.urlsafe_b64encode(f"ph:{offset}".encode()).decode().rstrip("=")


def _offset(cursor):
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        prefix, _, value = raw.partition(":")
        if prefix != "ph" or not value.isdigit():
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


def _bound(text, name, end):
    """An aware datetime for a ``since``/``until`` value: a date (whole local day) or an RFC 3339 instant."""
    try:
        day = date.fromisoformat(text)
        moment = datetime.combine(day, time.max if end else time.min, tzinfo=CDT)
        return moment
    except ValueError:
        pass
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return invalid(name, f"{name} must be a date (YYYY-MM-DD) or an RFC 3339 date-time.")
    if moment.tzinfo is None:
        return invalid(name, f"{name} needs a time zone offset.")
    return moment


# --- operations ---------------------------------------------------------------------------------

def list_calls(account_id, direction=None, status=None, since=None, until=None, limit=25, cursor=None):
    if direction is not None and direction not in ("incoming", "outgoing"):
        return invalid("direction", "direction must be incoming or outgoing.")
    if status is not None and status not in CALL_STATUSES:
        return invalid("status", f"status must be one of {', '.join(CALL_STATUSES)}.")
    low = _bound(since, "since", False) if since is not None else None
    high = _bound(until, "until", True) if until is not None else None
    for bound in (low, high):
        if isinstance(bound, PhoneError):
            return bound
    rows = [r for r in _store.table("calls").find(lambda r: r.get("owner_account_id") == account_id)
            if (direction is None or r["direction"] == direction) and (status is None or r["status"] == status)
            and (low is None or datetime.fromisoformat(r["started_at"]) >= low)
            and (high is None or datetime.fromisoformat(r["started_at"]) <= high)]
    rows.sort(key=lambda r: datetime.fromisoformat(r["started_at"]), reverse=True)
    return _page([_call_view(r, account_id) for r in rows], limit, cursor, "calls")


def _check_number(number, account_id):
    if not NUMBER.match(number or ""):
        return invalid("to", "to must be a phone number in E.164 form, for example +13125550143.")
    line = _line(account_id)
    if line and number == line["number"]:
        return invalid("to", "to is this line's own number.")
    return None


def place_call(account_id, to):
    problem = _check_number(to, account_id)
    if problem:
        return problem
    line = _line(account_id)
    row = {"id": "call_" + secrets.token_hex(8), "owner_account_id": account_id, "line_id": line["id"],
           "direction": "outgoing", "number": to, "status": "placed", "duration_seconds": 0,
           "voicemail_left": False, "started_at": _now().isoformat()}
    _store.table("calls").upsert(row)
    return _call_view(row, account_id)


def list_conversations(account_id, unread_only=False, limit=25, cursor=None):
    rows = _store.table("conversations").find(lambda r: r.get("owner_account_id") == account_id)
    rows.sort(key=lambda r: datetime.fromisoformat(r["last_message_at"]), reverse=True)
    views = [_conversation_view(r, account_id) for r in rows]
    if unread_only:
        views = [v for v in views if v["unread_count"]]
    return _page(views, limit, cursor, "conversations")


def list_messages(conversation_id, account_id, limit=25, cursor=None):
    row = _store.table("conversations").get(conversation_id)
    if row is None or row.get("owner_account_id") != account_id:
        return not_found("conversation", conversation_id)
    line = _line(account_id)
    views = [_message_view(m, line["number"], row["number"]) for m in _messages(conversation_id)]
    return _page(views, limit, cursor, "messages")


def send_text(account_id, to, body):
    problem = _check_number(to, account_id)
    if problem:
        return problem
    if not (body or "").strip():
        return invalid("body", "body must not be empty.")
    if len(body) > TEXT_LIMIT:
        return invalid("body", f"body can be at most {TEXT_LIMIT} characters.")
    line = _line(account_id)
    now = _now().isoformat()
    conversation = _store.table("conversations").find_one(
        lambda r: r.get("owner_account_id") == account_id and r["number"] == to)
    if conversation is None:
        conversation = {"id": "conv_" + secrets.token_hex(8), "owner_account_id": account_id, "line_id": line["id"],
                        "number": to, "last_message_at": now}
        _store.table("conversations").upsert(conversation)
    row = {"id": "msg_" + secrets.token_hex(8), "conversation_id": conversation["id"], "owner_account_id": account_id,
           "direction": "outbound", "body": body, "sent_at": now, "status": "delivered", "read": True}
    _store.table("messages").upsert(row)
    _store.table("conversations").patch(conversation["id"], {"last_message_at": now})
    return _message_view(row, line["number"], to)


_store.eager_load()
