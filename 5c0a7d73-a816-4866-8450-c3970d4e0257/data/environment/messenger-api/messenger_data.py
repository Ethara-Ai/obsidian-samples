"""Data access module for the Facebook Messenger mock service.

Serves exactly the eight Messenger connector operations the client lists -- sync,
messages, check, threads, send, search, contacts, unsend -- for the personal
inbox of one connected account. Every read is scoped to the conversations the
presented token's connected account owns; every write goes through the shared
store so a sent or unsent message is visible on the next read.
"""

import base64
import hashlib
import sys
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent

sys.path.insert(0, str(DATA_DIR.parent))
import _mock_clock  # noqa: E402
from _mutable_store import get_store, opt_str, read_seed_with_ctx, strict_bool  # noqa: E402
from _connector_auth import ConnectorAuth  # noqa: E402

_API = "messenger-api"
_store = get_store(_API)

GRAPH_VERSION = "v21.0"
TEXT_LIMIT = 2000
UNSEND_WINDOW = timedelta(minutes=10)
SYNC_DEFAULT_WINDOW = timedelta(hours=48)
UNSENT_SNIPPET = "You unsent a message"


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _coerce_thread_row(r):
    out = _strip_ctx(r)
    out["is_group"] = strict_bool(out, "is_group")
    return out


def _coerce_message_row(r):
    out = _strip_ctx(r)
    out["unsent"] = strict_bool(out, "unsent")
    out["updated_time"] = opt_str(out, "updated_time") or out["created_time"]
    out["source"] = opt_str(out, "source", "seed")
    return out


def _with_participant_pk(r):
    out = _strip_ctx(r)
    out["_pk"] = f"{out['thread_id']}:{out['user_id']}"
    return out


def _with_reaction_pk(r):
    out = _strip_ctx(r)
    out["_pk"] = f"{out['message_id']}:{out['user_id']}"
    return out


_store.register("users", primary_key="id",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("users.json", "users")])
_store.register("threads", primary_key="id",
                initial_loader=lambda: [_coerce_thread_row(r) for r in _load("threads.json", "threads")],
                row_coercer=_coerce_thread_row)
_store.register("thread_participants", primary_key="_pk",
                initial_loader=lambda: [_with_participant_pk(r) for r in
                                        _load("thread_participants.json", "thread_participants")])
_store.register("messages", primary_key="id",
                initial_loader=lambda: [_coerce_message_row(r) for r in _load("messages.json", "messages")],
                row_coercer=_coerce_message_row)
_store.register("attachments", primary_key="id",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("attachments.json", "attachments")])
_store.register("reactions", primary_key="_pk",
                initial_loader=lambda: [_with_reaction_pk(r) for r in _load("reactions.json", "reactions")])

auth = ConnectorAuth(_API, store=_store, data_dir=DATA_DIR)


class GraphError:
    """A Graph API error envelope and the HTTP status it is served with."""

    def __init__(self, status, message, code=100, subcode=None, err_type="GraphMethodException"):
        self.status = status
        error = {"message": message, "type": err_type, "code": code,
                 "fbtrace_id": "Amock" + hashlib.sha1(message.encode()).hexdigest()[:11]}
        if subcode is not None:
            error["error_subcode"] = subcode
        self.body = {"error": error}


def _missing(object_id):
    return GraphError(
        404,
        f"Unsupported get request. Object with ID '{object_id}' does not exist, cannot be "
        "loaded due to missing permissions, or does not support this operation.",
        code=100, subcode=33,
    )


def _invalid(message):
    return GraphError(400, f"(#100) {message}", code=100, err_type="OAuthException")


def _now():
    return _mock_clock.now(timezone.utc)


def _graph_time(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%S+0000")


def _precise_time(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%f+0000")


def _parse_time(text):
    return datetime.fromisoformat(text.replace("+0000", "+00:00"))


def _new_numeric_id(width=15):
    return f"{uuid.uuid4().int % 10**width:0{width}d}"


def _cursor(prefix, value):
    return base64.urlsafe_b64encode(f"{prefix}:{value}".encode()).decode().rstrip("=")


def _cursor_value(cursor, prefix):
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        found, _, value = raw.partition(":")
        if found != prefix:
            raise ValueError(raw)
        return int(value)
    except (ValueError, UnicodeDecodeError):
        return None


def _page(items, limit, after, path):
    start = 0
    if after:
        index = _cursor_value(after, "mg")
        if index is None:
            return _invalid(f"Invalid cursor: {after}")
        start = index + 1
    window = items[start:start + limit]
    paging = {"cursors": {}}
    if window:
        paging["cursors"] = {"before": _cursor("mg", start), "after": _cursor("mg", start + len(window) - 1)}
    if start + limit < len(items):
        query = urllib.parse.urlencode({"limit": limit, "after": _cursor("mg", start + len(window) - 1)})
        paging["next"] = f"/{GRAPH_VERSION}/{path}?{query}"
    return {"data": window, "paging": paging}


def _newest_first(rows, key):
    # Timestamps have one-second resolution; rows appended later win a tie.
    ordered = sorted(enumerate(rows), key=lambda pair: (pair[1][key], pair[0]), reverse=True)
    return [r for _, r in ordered]


def _me(account_id):
    rows = _store.table("users").find(lambda u: u.get("owner_account_id") == account_id)
    return rows[0] if rows else None


def _owned_thread(thread_id, account_id):
    t = _store.table("threads").get(thread_id)
    if t is None or t["owner_account_id"] != account_id:
        return None
    return t


def _user_name(user_id):
    u = _store.table("users").get(user_id)
    return u["name"] if u else ""


def _participant_ids(thread_id):
    return [p["user_id"] for p in _store.table("thread_participants").find(lambda p: p["thread_id"] == thread_id)]


def _thread_messages(thread_id):
    return [m for m in _store.table("messages").rows() if m["thread_id"] == thread_id]


def _unread(thread, me_id):
    return [m for m in _thread_messages(thread["id"])
            if m["from_id"] != me_id and not m["unsent"] and m["created_time"] > thread["last_read_time"]]


def _message_view(m):
    sender = m["from_id"]
    to = [{"id": u, "name": _user_name(u)} for u in _participant_ids(m["thread_id"]) if u != sender]
    attachments, reactions = [], []
    if not m["unsent"]:
        attachments = [{"id": a["id"], "type": a["type"], "name": a["name"], "url": a["url"]}
                       for a in _store.table("attachments").find(lambda a: a["message_id"] == m["id"])]
        reactions = [{"user": {"id": r["user_id"], "name": _user_name(r["user_id"])}, "reaction": r["reaction"]}
                     for r in _store.table("reactions").find(lambda r: r["message_id"] == m["id"])]
    return {
        "id": m["id"], "thread_id": m["thread_id"],
        "from": {"id": sender, "name": _user_name(sender)}, "to": {"data": to},
        "message": m["text"], "created_time": m["created_time"],
        "attachments": {"data": attachments}, "reactions": {"data": reactions}, "unsent": m["unsent"],
    }


def _thread_view(t, me_id):
    participants = []
    for uid in _participant_ids(t["id"]):
        u = _store.table("users").get(uid)
        participants.append({"id": uid, "name": u["name"] if u else "", "username": u["username"] if u else ""})
    view = {"id": t["id"], "participants": {"data": participants}, "snippet": t["snippet"],
            "updated_time": t["updated_time"], "unread_count": len(_unread(t, me_id)),
            "is_group": t["is_group"]}
    if t["is_group"] and t["name"]:
        view["name"] = t["name"]
    return view


def _owned_threads(account_id):
    return _newest_first(_store.table("threads").find(lambda t: t["owner_account_id"] == account_id),
                         "updated_time")


# --- .threads -------------------------------------------------------------------------

def list_threads(account_id, limit=25, after=None):
    me = _me(account_id)
    if me is None:
        return _missing("me")
    return _page([_thread_view(t, me["id"]) for t in _owned_threads(account_id)], limit, after,
                 "me/conversations")


def get_thread(thread_id, account_id):
    me = _me(account_id)
    t = _owned_thread(thread_id, account_id)
    if me is None or t is None:
        return _missing(thread_id)
    return _thread_view(t, me["id"])


# --- .messages -------------------------------------------------------------------------

def list_messages(thread_id, account_id, limit=25, after=None):
    if _me(account_id) is None or _owned_thread(thread_id, account_id) is None:
        return _missing(thread_id)
    rows = _newest_first(_thread_messages(thread_id), "created_time")
    return _page([_message_view(m) for m in rows], limit, after, f"me/conversations/{thread_id}/messages")


# --- .check ----------------------------------------------------------------------------

def get_unread(account_id):
    me = _me(account_id)
    if me is None:
        return _missing("me")
    entries = []
    for t in _owned_threads(account_id):
        unread = _unread(t, me["id"])
        if not unread:
            continue
        newest = _newest_first(unread, "created_time")[0]
        entries.append({"thread_id": t["id"], "is_group": t["is_group"],
                        "name": t["name"] if t["is_group"] else "",
                        "unread_count": len(unread), "newest_unread_message": _message_view(newest)})
    entries.sort(key=lambda e: e["newest_unread_message"]["created_time"], reverse=True)
    return {"total_unread": sum(e["unread_count"] for e in entries), "threads": entries}


# --- .sync -----------------------------------------------------------------------------

def sync(account_id, cursor=None):
    me = _me(account_id)
    if me is None:
        return _missing("me")
    owned = {t["id"]: t for t in _owned_threads(account_id)}
    messages = [m for m in _store.table("messages").rows() if m["thread_id"] in owned]
    if cursor:
        micros = _cursor_value(cursor, "sync")
        if micros is None:
            return _invalid(f"Invalid cursor: {cursor}")
        since = datetime.fromtimestamp(micros / 1_000_000, tz=timezone.utc)
        changed = [m for m in messages if _parse_time(m["updated_time"]) > since]
        changed_threads = {m["thread_id"] for m in changed}
        changed_threads |= {tid for tid, t in owned.items() if _parse_time(t["updated_time"]) > since}
    else:
        seeded = [_parse_time(m["created_time"]) for m in messages if m["source"] != "api"]
        anchor = max(seeded) if seeded else max((_parse_time(m["created_time"]) for m in messages),
                                                default=_now())
        start = anchor - SYNC_DEFAULT_WINDOW
        changed = [m for m in messages if _parse_time(m["updated_time"]) >= start]
        changed_threads = {m["thread_id"] for m in changed}
        changed_threads |= {tid for tid, t in owned.items() if _parse_time(t["updated_time"]) >= start}
    stamps = [_now()] + [_parse_time(m["updated_time"]) for m in messages]
    next_cursor = _cursor("sync", int(max(stamps).timestamp() * 1_000_000))
    ordered = sorted(enumerate(changed), key=lambda pair: (pair[1]["created_time"], pair[0]))
    return {
        "threads": [_thread_view(t, me["id"]) for t in owned.values() if t["id"] in changed_threads],
        "messages": [_message_view(m) for _, m in ordered],
        "cursor": next_cursor,
    }


# --- .search ---------------------------------------------------------------------------

def search(account_id, q):
    me = _me(account_id)
    if me is None:
        return _missing("me")
    needle = (q or "").strip().lower()
    if not needle:
        return _invalid("The parameter q is required")
    owned = _owned_threads(account_id)
    threads = []
    for t in owned:
        others = [_user_name(u) for u in _participant_ids(t["id"]) if u != me["id"]]
        if any(needle in name.lower() for name in others):
            threads.append(_thread_view(t, me["id"]))
    owned_ids = {t["id"] for t in owned}
    hits = [m for m in _store.table("messages").rows()
            if m["thread_id"] in owned_ids and not m["unsent"] and needle in m["text"].lower()]
    return {"threads": threads, "messages": [_message_view(m) for m in _newest_first(hits, "created_time")]}


# --- .contacts -------------------------------------------------------------------------

def list_contacts(account_id, limit=25, after=None):
    me = _me(account_id)
    if me is None:
        return _missing("me")
    rows = sorted((u for u in _store.table("users").rows() if u["id"] != me["id"]), key=lambda u: u["name"])
    views = [{"id": u["id"], "name": u["name"], "username": u["username"],
              "is_friend": u["is_friend"] == "true", "last_active": u["last_active"]} for u in rows]
    return _page(views, limit, after, "me/contacts")


# --- .send -----------------------------------------------------------------------------

def _direct_thread(account_id, me_id, contact_id):
    pair = {me_id, contact_id}
    found = [t for t in _owned_threads(account_id)
             if not t["is_group"] and set(_participant_ids(t["id"])) == pair]
    return found[0] if found else None


def send_message(account_id, text, recipient_id=None, thread_id=None):
    me = _me(account_id)
    if me is None:
        return _missing("me")
    if bool(recipient_id) == bool(thread_id):
        return _invalid("The parameter recipient must carry exactly one of id or thread_id")
    if text is None or not text.strip():
        return _invalid("The parameter message.text must not be empty")
    if len(text) > TEXT_LIMIT:
        return _invalid(f"The message text is longer than {TEXT_LIMIT} characters")
    now = _now()
    if thread_id:
        thread = _owned_thread(thread_id, account_id)
        if thread is None:
            return _invalid(f"Invalid recipient: no conversation {thread_id} on this account")
    else:
        contact = _store.table("users").get(recipient_id)
        if contact is None or contact["id"] == me["id"]:
            return _invalid(f"Invalid recipient: {recipient_id} is not a contact of this account")
        thread = _direct_thread(account_id, me["id"], contact["id"])
        if thread is None:
            thread = {"id": f"t_{_new_numeric_id()}", "owner_account_id": account_id, "is_group": False,
                      "name": "", "snippet": "", "updated_time": _graph_time(now),
                      "last_read_time": _graph_time(now)}
            _store.table("threads").upsert(thread)
            for uid in (me["id"], contact["id"]):
                _store.table("thread_participants").upsert(
                    {"_pk": f"{thread['id']}:{uid}", "thread_id": thread["id"], "user_id": uid})
    message_id = f"m_{_new_numeric_id(20)}"
    _store.table("messages").upsert({
        "id": message_id, "thread_id": thread["id"], "from_id": me["id"], "text": text,
        "created_time": _graph_time(now), "updated_time": _precise_time(now), "unsent": False,
        "source": "api",
    })
    _store.table("threads").patch(thread["id"], {"snippet": text[:100], "updated_time": _graph_time(now)})
    return {"message_id": message_id, "thread_id": thread["id"]}


# --- .unsend ---------------------------------------------------------------------------

def unsend_message(message_id, account_id):
    me = _me(account_id)
    m = _store.table("messages").get(message_id)
    if me is None or m is None or _owned_thread(m["thread_id"], account_id) is None:
        return _missing(message_id)
    if m["from_id"] != me["id"]:
        return _invalid("Only messages sent by the connected user can be unsent")
    if m["unsent"]:
        return _invalid(f"Message {message_id} was already unsent")
    now = _now()
    age = now - _parse_time(m["created_time"])
    if not timedelta(0) <= age <= UNSEND_WINDOW:
        return _invalid("A message can only be unsent within 10 minutes of sending")
    _store.table("messages").patch(message_id, {"text": "", "unsent": True,
                                                "updated_time": _precise_time(now)})
    newest = _newest_first(_thread_messages(m["thread_id"]), "created_time")[0]
    if newest["id"] == message_id:
        _store.table("threads").patch(m["thread_id"], {"snippet": UNSENT_SNIPPET})
    return {"success": True}


_store.eager_load()
