"""Data access module for the Threads Messages mock service.

Serves exactly the three Threads messaging operations the connector needs --
list conversations, list the messages of a conversation, send a message -- for
the Threads profile one connected account owns. The profile is @mayamakes, the
same one threads-api serves, and every read is scoped to the conversations that
profile is part of.

Meta publishes no messaging endpoint in the Threads API that this mock could
copy, so, as the client asked, it mirrors instagram-messages-api: the same Graph
messaging shape (conversations, a conversation's messages, a send on
/me/messages) on the Threads Graph version prefix. Mock simplifications (also
stated in api_test_results.md): text messages only (seeded messages may carry
an image or a shared post), no reactions, no message requests folder, and no
messaging window.
"""

import base64
import hashlib
import sys
import uuid
from datetime import timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent

sys.path.insert(0, str(DATA_DIR.parent))
import _mock_clock  # noqa: E402
from _mutable_store import get_store, read_seed_with_ctx  # noqa: E402
from _connector_auth import ConnectorAuth  # noqa: E402

_API = "threads-messages-api"
_store = get_store(_API)

GRAPH_VERSION = "v1.0"
TEXT_LIMIT_BYTES = 1000
CONVERSATION_FIELDS = ("id", "updated_time", "participants")
MESSAGE_FIELDS = ("id", "created_time", "from", "to", "message", "attachments", "shared_post")


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _coerce_message_row(r):
    out = _strip_ctx(r)
    for key in ("message", "attachment_url", "shared_post_url"):
        out[key] = out.get(key) or ""
    return out


_store.register("accounts", primary_key="id",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("accounts.json", "accounts")])
_store.register("users", primary_key="id",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("users.json", "users")])
_store.register("conversations", primary_key="id",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("conversations.json", "conversations")])
_store.register("messages", primary_key="id",
                initial_loader=lambda: [_coerce_message_row(r) for r in _load("messages.json", "messages")],
                row_coercer=_coerce_message_row)

auth = ConnectorAuth(_API, store=_store, data_dir=DATA_DIR)


class GraphError:
    """A Threads Graph error envelope and the HTTP status it is served with."""

    def __init__(self, status, message, code=100, subcode=None, err_type="THApiException"):
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


def invalid(message):
    return GraphError(400, f"(#100) {message}", code=100, err_type="OAuthException")


def _now():
    return _mock_clock.now(timezone.utc)


def _graph_time(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%S+0000")


def _account(threads_user_id, account_id):
    """The Threads profile addressed as ``me`` or by id, when the connected account owns it."""
    owned = _store.table("accounts").find(lambda a: a.get("owner_account_id") == account_id)
    if threads_user_id == "me":
        return owned[0] if owned else None
    return next((a for a in owned if a["id"] == threads_user_id), None)


def _project(view, fields, allowed, node_type):
    if not fields:
        return view
    wanted = [f.strip() for f in fields.split(",") if f.strip()]
    for name in wanted:
        if name not in allowed:
            return invalid(f"Tried accessing nonexisting field ({name}) on node type ({node_type})")
    return {"id": view["id"], **{name: view[name] for name in wanted if name in view}}


def _cursor(index):
    return base64.urlsafe_b64encode(f"thm:{index}".encode()).decode().rstrip("=")


def _cursor_index(cursor):
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        prefix, _, index = raw.partition(":")
        if prefix != "thm":
            raise ValueError(raw)
        return int(index)
    except (ValueError, UnicodeDecodeError):
        return None


def _page(items, limit, after, path):
    start = 0
    if after:
        index = _cursor_index(after)
        if index is None:
            return invalid(f"Invalid cursor: {after}")
        start = index + 1
    window = items[start:start + limit]
    paging = {"cursors": {}}
    if window:
        paging["cursors"] = {"before": _cursor(start), "after": _cursor(start + len(window) - 1)}
    if start + limit < len(items):
        paging["next"] = (f"/{GRAPH_VERSION}/{path}&limit={limit}" if "?" in path else
                          f"/{GRAPH_VERSION}/{path}?limit={limit}") + f"&after={_cursor(start + len(window) - 1)}"
    return {"data": window, "paging": paging}


def _who(user_id, account):
    if user_id == account["id"]:
        return {"username": account["username"], "id": account["id"]}
    user = _store.table("users").get(user_id) or {}
    return {"username": user.get("username", ""), "id": user_id}


def _conversation_view(c, account):
    return {"id": c["id"], "updated_time": c["updated_time"],
            "participants": {"data": [_who(account["id"], account), _who(c["participant_id"], account)]}}


def _message_view(m, account):
    view = {"id": m["id"], "created_time": m["created_time"], "from": _who(m["from_id"], account),
            "to": {"data": [_who(m["to_id"], account)]}, "message": m["message"]}
    if m["attachment_url"]:
        view["attachments"] = {"data": [{"image_data": {"url": m["attachment_url"],
                                                        "preview_url": m["attachment_url"]}}]}
    if m["shared_post_url"]:
        view["shared_post"] = {"link": m["shared_post_url"], "id": m["shared_post_url"].rstrip("/").rsplit("/", 1)[-1]}
    return view


# --- conversations ----------------------------------------------------------------------

def list_conversations(threads_user_id, account_id, user_id=None, limit=25, after=None, fields=None):
    account = _account(threads_user_id, account_id)
    if account is None:
        return _missing(threads_user_id)
    rows = _store.table("conversations").find(
        lambda c: c["threads_user_id"] == account["id"] and (user_id is None or c["participant_id"] == user_id))
    rows.sort(key=lambda c: c["updated_time"], reverse=True)
    views = []
    for c in rows:
        projected = _project(_conversation_view(c, account), fields, CONVERSATION_FIELDS, "Conversation")
        if isinstance(projected, GraphError):
            return projected
        views.append(projected)
    query = ([f"user_id={user_id}"] if user_id else []) + ([f"fields={fields}"] if fields else [])
    return _page(views, limit, after, f"{threads_user_id}/conversations" + ("?" + "&".join(query) if query else ""))


def list_messages(conversation_id, account_id, limit=25, after=None, fields=None):
    c = _store.table("conversations").get(conversation_id)
    account = None
    if c is not None:
        account = next((a for a in _store.table("accounts").find(lambda a: a.get("owner_account_id") == account_id)
                        if a["id"] == c["threads_user_id"]), None)
    if account is None:
        return _missing(conversation_id)
    rows = sorted(_store.table("messages").find(lambda m: m["conversation_id"] == conversation_id),
                  key=lambda m: m["created_time"], reverse=True)
    views = []
    for m in rows:
        projected = _project(_message_view(m, account), fields, MESSAGE_FIELDS, "Message")
        if isinstance(projected, GraphError):
            return projected
        views.append(projected)
    path = f"{conversation_id}/messages" + (f"?fields={fields}" if fields else "")
    return _page(views, limit, after, path)


# --- send -------------------------------------------------------------------------------

def send_message(threads_user_id, account_id, recipient_id, text):
    account = _account(threads_user_id, account_id)
    if account is None:
        return _missing(threads_user_id)
    conversation = _store.table("conversations").find_one(
        lambda c: c["threads_user_id"] == account["id"] and c["participant_id"] == recipient_id)
    if conversation is None:
        return GraphError(400, "(#100) No matching user found", code=100, subcode=2018001,
                          err_type="OAuthException")
    if not text or not text.strip():
        return invalid("The parameter message[text] is required")
    if len(text.encode("utf-8")) > TEXT_LIMIT_BYTES:
        return invalid(f"Param message[text] must be at most {TEXT_LIMIT_BYTES} bytes (UTF-8)")
    now = _graph_time(_now())
    message_id = "dGhfZDox" + base64.urlsafe_b64encode(uuid.uuid4().bytes + uuid.uuid4().bytes).decode().rstrip("=")
    _store.table("messages").upsert({"id": message_id, "conversation_id": conversation["id"],
                                     "from_id": account["id"], "to_id": recipient_id, "message": text,
                                     "created_time": now, "attachment_url": "", "shared_post_url": ""})
    _store.table("conversations").patch(conversation["id"], {"updated_time": now})
    return {"recipient_id": recipient_id, "message_id": message_id}


_store.eager_load()
