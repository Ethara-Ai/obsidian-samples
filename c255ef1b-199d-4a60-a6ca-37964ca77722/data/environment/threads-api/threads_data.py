"""Data access module for the Threads API mock service.

Serves exactly the five Threads operations the connector needs -- read the
profile, list the account's threads, get one thread, publish a text thread
(create a container, then publish it), and list the replies to a thread -- for
the Threads profile one connected account owns (mayamakes, the creator account
instagram-api also serves). Replies are media objects of their own: a reply to
a reply is reached through the replies edge of the reply it answers.

Mock simplifications (also stated in api_test_results.md): only text posts can
be published, there is no insights, quote or repost endpoint, and a container
is ready to publish as soon as it is created.
"""

import base64
import hashlib
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent

sys.path.insert(0, str(DATA_DIR.parent))
import _mock_clock  # noqa: E402
from _mutable_store import get_store, opt_bool, read_seed_with_ctx  # noqa: E402
from _connector_auth import ConnectorAuth  # noqa: E402

_API = "threads-api"
_store = get_store(_API)

API_VERSION = "v1.0"
TEXT_LIMIT = 500
PROFILE_FIELDS = ("id", "username", "name", "threads_profile_picture_url", "threads_biography", "is_verified")
THREAD_FIELDS = ("id", "media_product_type", "media_type", "media_url", "permalink", "owner", "username", "text",
                 "timestamp", "shortcode", "is_quote_post", "has_replies", "is_reply")
REPLY_FIELDS = ("id", "media_product_type", "media_type", "permalink", "username", "text", "timestamp",
                "shortcode", "has_replies", "root_post", "replied_to", "is_reply", "hide_status")
SHORTCODE_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _coerce_account_row(r):
    out = _strip_ctx(r)
    out["is_verified"] = opt_bool(out, "is_verified")
    return out


def _coerce_thread_row(r):
    out = _strip_ctx(r)
    out["is_quote_post"] = opt_bool(out, "is_quote_post")
    out["media_url"] = out.get("media_url") or ""
    return out


_store.register("accounts", primary_key="id",
                initial_loader=lambda: [_coerce_account_row(r) for r in _load("accounts.json", "accounts")],
                row_coercer=_coerce_account_row)
_store.register("threads", primary_key="id",
                initial_loader=lambda: [_coerce_thread_row(r) for r in _load("threads.json", "threads")],
                row_coercer=_coerce_thread_row)
_store.register("replies", primary_key="id",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("replies.json", "replies")])
_store.register("containers", primary_key="id", initial_loader=lambda: [])

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
    return GraphError(400, f"(#100) {message}")


def _now():
    return _mock_clock.now(timezone.utc)


def _graph_time(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%S+0000")


def _new_numeric_id(prefix, digits=14):
    return f"{prefix}{uuid.uuid4().int % 10**digits:0{digits}d}"


def _new_shortcode():
    raw = uuid.uuid4().bytes
    return "D" + "".join(SHORTCODE_ALPHABET[b % 64] for b in raw[:10])


def _profile(user_id, account_id):
    owned = _store.table("accounts").find(lambda a: a.get("owner_account_id") == account_id)
    if user_id == "me":
        return owned[0] if owned else None
    return next((a for a in owned if a["id"] == user_id), None)


def _project(view, fields, allowed, node_type):
    if not fields:
        return view
    wanted = [f.strip() for f in fields.split(",") if f.strip()]
    for name in wanted:
        if name not in allowed:
            return invalid(f"Tried accessing nonexisting field ({name}) on node type ({node_type})")
    return {"id": view["id"], **{name: view[name] for name in wanted if name in view}}


def _cursor(index):
    return base64.urlsafe_b64encode(f"th:{index}".encode()).decode().rstrip("=")


def _cursor_index(cursor):
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        prefix, _, index = raw.partition(":")
        if prefix != "th":
            raise ValueError(raw)
        return int(index)
    except (ValueError, UnicodeDecodeError):
        return None


def _page(items, limit, after, path, query):
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
        extra = "".join(f"&{k}={v}" for k, v in query)
        paging["next"] = f"/{API_VERSION}/{path}?limit={limit}{extra}&after={_cursor(start + len(window) - 1)}"
    return {"data": window, "paging": paging}


def _has_replies(media_id):
    return _store.table("replies").find_one(lambda r: r["replied_to_id"] == media_id) is not None


def _profile_view(a):
    return {k: a[k] for k in PROFILE_FIELDS if k in a}


def _thread_view(t, account):
    view = {"id": t["id"], "media_product_type": "THREADS", "media_type": t["media_type"]}
    if t["media_url"]:
        view["media_url"] = t["media_url"]
    view.update({"permalink": t["permalink"], "owner": {"id": account["id"]}, "username": account["username"],
                 "text": t["text"], "timestamp": t["timestamp"], "shortcode": t["shortcode"],
                 "is_quote_post": t["is_quote_post"], "has_replies": _has_replies(t["id"]), "is_reply": False})
    return view


def _reply_view(r):
    return {"id": r["id"], "media_product_type": "THREADS", "media_type": "TEXT_POST", "permalink": r["permalink"],
            "username": r["username"], "text": r["text"], "timestamp": r["timestamp"], "shortcode": r["shortcode"],
            "has_replies": _has_replies(r["id"]), "root_post": {"id": r["root_id"]},
            "replied_to": {"id": r["replied_to_id"]}, "is_reply": True, "hide_status": r["hide_status"]}


def _when(value, name):
    """Seconds since the epoch for a unix timestamp or an ISO date; GraphError when unreadable."""
    text = str(value).strip()
    if text.lstrip("-").isdigit():
        return int(text)
    try:
        if len(text) == 10:
            return int(datetime.combine(date.fromisoformat(text), datetime.min.time(), timezone.utc).timestamp())
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return int(moment.timestamp())
    except ValueError:
        return invalid(f"Param {name} must be a unix timestamp or a date such as 2026-09-01")


def _epoch(graph_time):
    return int(datetime.strptime(graph_time, "%Y-%m-%dT%H:%M:%S%z").timestamp())


def _text_length(text):
    """Threads counts characters, with an emoji counted by its UTF-8 length."""
    return sum(len(ch.encode("utf-8")) if ord(ch) > 0xFFFF else 1 for ch in text)


# --- profile and single node ---------------------------------------------------------------

def get_node(node_id, account_id, fields=None):
    profile = _profile(node_id, account_id)
    if profile is not None:
        return _project(_profile_view(profile), fields, PROFILE_FIELDS, "ThreadsUser")
    owned = {a["id"]: a for a in _store.table("accounts").find(lambda a: a.get("owner_account_id") == account_id)}
    thread = _store.table("threads").get(node_id)
    if thread is None or thread["user_id"] not in owned:
        return _missing(node_id)
    return _project(_thread_view(thread, owned[thread["user_id"]]), fields, THREAD_FIELDS, "ThreadsMedia")


# --- the account's threads ---------------------------------------------------------------------

def list_threads(user_id, account_id, since=None, until=None, limit=25, after=None, fields=None):
    account = _profile(user_id, account_id)
    if account is None:
        return _missing(user_id)
    low = _when(since, "since") if since is not None else None
    high = _when(until, "until") if until is not None else None
    for bound in (low, high):
        if isinstance(bound, GraphError):
            return bound
    if low is not None and high is not None and low > high:
        return invalid("Param since must not be later than until")
    rows = [t for t in _store.table("threads").find(lambda t: t["user_id"] == account["id"])
            if (low is None or _epoch(t["timestamp"]) >= low) and (high is None or _epoch(t["timestamp"]) <= high)]
    rows.sort(key=lambda t: t["timestamp"], reverse=True)
    views = []
    for t in rows:
        projected = _project(_thread_view(t, account), fields, THREAD_FIELDS, "ThreadsMedia")
        if isinstance(projected, GraphError):
            return projected
        views.append(projected)
    query = [(k, v) for k, v in (("since", since), ("until", until), ("fields", fields)) if v is not None]
    return _page(views, limit, after, f"{user_id}/threads", query)


# --- publishing: a container first, then threads_publish -----------------------------------------

def create_container(user_id, account_id, media_type, text):
    account = _profile(user_id, account_id)
    if account is None:
        return _missing(user_id)
    kind = (media_type or "").upper()
    if kind in ("IMAGE", "VIDEO", "CAROUSEL"):
        return invalid(f"media_type {kind} is not supported by this service; publish text posts with "
                       "media_type TEXT")
    if kind != "TEXT":
        return invalid("Param media_type must be one of {TEXT, IMAGE, VIDEO, CAROUSEL}")
    if not text or not text.strip():
        return invalid("Param text is required for a TEXT post")
    if _text_length(text) > TEXT_LIMIT:
        return invalid(f"Param text must be at most {TEXT_LIMIT} characters")
    container = {"id": _new_numeric_id("1789", 13), "user_id": account["id"], "media_type": "TEXT_POST",
                 "text": text, "status": "FINISHED", "created_time": _graph_time(_now()), "published_id": ""}
    _store.table("containers").upsert(container)
    return {"id": container["id"]}


def publish_container(user_id, account_id, creation_id):
    account = _profile(user_id, account_id)
    if account is None:
        return _missing(user_id)
    container = _store.table("containers").get(creation_id)
    if container is None or container["user_id"] != account["id"]:
        return invalid(f"Param creation_id {creation_id} is not a media container of this user")
    if container["published_id"]:
        return invalid(f"The media container {creation_id} was already published as {container['published_id']}")
    media_id = _new_numeric_id("1806", 14)
    code = _new_shortcode()
    _store.table("threads").upsert({
        "id": media_id, "user_id": account["id"], "media_type": container["media_type"], "media_url": "",
        "text": container["text"], "timestamp": _graph_time(_now()), "shortcode": code,
        "permalink": f"https://www.threads.net/@{account['username']}/post/{code}", "is_quote_post": False,
    })
    _store.table("containers").patch(creation_id, {"published_id": media_id, "status": "PUBLISHED"})
    return {"id": media_id}


# --- replies ------------------------------------------------------------------------------------

def list_replies(media_id, account_id, reverse=True, limit=25, after=None, fields=None):
    owned = {a["id"] for a in _store.table("accounts").find(lambda a: a.get("owner_account_id") == account_id)}
    thread = _store.table("threads").get(media_id)
    reply = _store.table("replies").get(media_id)
    root = thread or (_store.table("threads").get(reply["root_id"]) if reply else None)
    if root is None or root["user_id"] not in owned:
        return _missing(media_id)
    rows = sorted(_store.table("replies").find(lambda r: r["replied_to_id"] == media_id),
                  key=lambda r: r["timestamp"], reverse=reverse)
    views = []
    for r in rows:
        projected = _project(_reply_view(r), fields, REPLY_FIELDS, "ThreadsMedia")
        if isinstance(projected, GraphError):
            return projected
        views.append(projected)
    query = [("reverse", "true" if reverse else "false")] + ([("fields", fields)] if fields else [])
    return _page(views, limit, after, f"{media_id}/replies", query)


_store.eager_load()
