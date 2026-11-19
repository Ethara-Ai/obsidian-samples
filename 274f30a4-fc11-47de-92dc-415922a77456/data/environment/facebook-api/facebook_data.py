"""Data access module for the Facebook Graph API mock service.

Serves exactly the eight Facebook connector operations the client lists --
marketplace, me, groups, timeline, profile, post, feed, saved -- for one
connected personal account. Reads of the user's own data (timeline, saved items,
groups) are scoped to the presented token's connected account; news-feed and
group content is limited to what that account can see (friends' and pages'
posts, and posts in groups it belongs to).
"""

import base64
import hashlib
import sys
import urllib.parse
import uuid
from datetime import timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent

sys.path.insert(0, str(DATA_DIR.parent))
import _mock_clock  # noqa: E402
from _mutable_store import get_store, read_seed_with_ctx, strict_float, strict_int  # noqa: E402
from _connector_auth import ConnectorAuth  # noqa: E402

_API = "facebook-api"
_store = get_store(_API)

GRAPH_VERSION = "v21.0"
MESSAGE_LIMIT = 63206
PRIVACY_VALUES = ("EVERYONE", "ALL_FRIENDS", "SELF")
CONDITIONS = ("new", "used_like_new", "used_good", "used_fair")
ME_FIELDS = ("id", "name", "first_name", "last_name", "link", "picture")
PROFILE_FIELDS = ("id", "name", "first_name", "last_name", "about", "hometown", "location", "link",
                  "work", "education", "picture")
POST_FIELDS = ("id", "message", "created_time", "from", "permalink_url", "type", "privacy", "link",
               "group", "reactions", "comments")


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _coerce_post_row(r):
    out = _strip_ctx(r)
    out["reactions_count"] = strict_int(out, "reactions_count")
    out["comments_count"] = strict_int(out, "comments_count")
    return out


def _coerce_group_row(r):
    out = _strip_ctx(r)
    out["member_count"] = strict_int(out, "member_count")
    return out


def _coerce_listing_row(r):
    out = _strip_ctx(r)
    out["price"] = strict_float(out, "price")
    return out


def _with_member_pk(r):
    out = _strip_ctx(r)
    out["_pk"] = f"{out['group_id']}:{out['user_id']}"
    return out


_store.register("users", primary_key="id",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("users.json", "users")])
_store.register("posts", primary_key="id",
                initial_loader=lambda: [_coerce_post_row(r) for r in _load("posts.json", "posts")],
                row_coercer=_coerce_post_row)
_store.register("groups", primary_key="id",
                initial_loader=lambda: [_coerce_group_row(r) for r in _load("groups.json", "groups")],
                row_coercer=_coerce_group_row)
_store.register("group_members", primary_key="_pk",
                initial_loader=lambda: [_with_member_pk(r) for r in _load("group_members.json", "group_members")])
_store.register("saved_items", primary_key="id",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("saved_items.json", "saved_items")])
_store.register("listings", primary_key="id",
                initial_loader=lambda: [_coerce_listing_row(r) for r in _load("listings.json", "listings")],
                row_coercer=_coerce_listing_row)

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


def _new_numeric_id(width=15):
    return f"{uuid.uuid4().int % 10**width:0{width}d}"


def _me(account_id):
    rows = _store.table("users").find(lambda u: u.get("owner_account_id") == account_id)
    return rows[0] if rows else None


def _user_name(user_id):
    u = _store.table("users").get(user_id)
    return u["name"] if u else ""


def _project(view, fields, allowed, node_type):
    if not fields:
        return view
    wanted = [f.strip() for f in fields.split(",") if f.strip()]
    for name in wanted:
        if name not in allowed:
            return _invalid(f"Tried accessing nonexisting field ({name}) on node type ({node_type})")
    return {"id": view["id"], **{name: view[name] for name in wanted if name in view}}


def _cursor(index):
    return base64.urlsafe_b64encode(f"fb:{index}".encode()).decode().rstrip("=")


def _cursor_index(cursor):
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        prefix, _, index = raw.partition(":")
        if prefix != "fb":
            raise ValueError(raw)
        return int(index)
    except (ValueError, UnicodeDecodeError):
        return None


def _page(items, limit, after, path, query=None):
    start = 0
    if after:
        index = _cursor_index(after)
        if index is None:
            return _invalid(f"Invalid cursor: {after}")
        start = index + 1
    window = items[start:start + limit]
    paging = {"cursors": {}}
    if window:
        paging["cursors"] = {"before": _cursor(start), "after": _cursor(start + len(window) - 1)}
    if start + limit < len(items):
        params = dict(query or {})
        params["limit"] = limit
        params["after"] = _cursor(start + len(window) - 1)
        paging["next"] = f"/{GRAPH_VERSION}/{path}?{urllib.parse.urlencode(params)}"
    return {"data": window, "paging": paging}


# --- views -----------------------------------------------------------------------

def _post_view(p):
    view = {
        "id": p["id"], "created_time": p["created_time"], "type": p["type"],
        "from": {"id": p["from_id"], "name": _user_name(p["from_id"])},
        "permalink_url": p["permalink_url"],
        "reactions": {"summary": {"total_count": p["reactions_count"]}},
        "comments": {"summary": {"total_count": p["comments_count"]}},
    }
    if p["message"]:
        view["message"] = p["message"]
    if p["link"]:
        view["link"] = p["link"]
    if p["privacy"]:
        view["privacy"] = {"value": p["privacy"]}
    if p["group_id"]:
        g = _store.table("groups").get(p["group_id"])
        view["group"] = {"id": p["group_id"], "name": g["name"] if g else ""}
    return view


def _picture(user):
    return {"data": {"url": user["picture_url"]}}


def _listing_view(l):
    return {
        "id": l["id"], "title": l["title"], "description": l["description"], "category": l["category"],
        "price": {"amount": f"{l['price']:.2f}", "currency": l["currency"],
                  "formatted": f"${l['price']:,.2f}" if l["currency"] == "USD" else f"{l['price']:,.2f} {l['currency']}"},
        "condition": l["condition"], "location": {"city": l["city"], "state": l["state"]},
        "seller": {"id": l["seller_id"], "name": _user_name(l["seller_id"])},
        "created_time": l["created_time"],
        "permalink_url": f"https://www.facebook.com/marketplace/item/{l['id']}/",
    }


def _is_member(group_id, user_id):
    return _store.table("group_members").get(f"{group_id}:{user_id}") is not None


def _visible(p, me):
    """Whether the connected user can see post ``p``: own, public friend/page posts, member groups."""
    if p["from_id"] == me["id"]:
        return True
    if p["group_id"]:
        return _is_member(p["group_id"], me["id"])
    return True


def _newest_first(rows):
    # Timestamps have one-second resolution; rows appended later win a tie.
    ordered = sorted(enumerate(rows), key=lambda pair: (pair[1]["created_time"], pair[0]), reverse=True)
    return [r for _, r in ordered]


# --- .me / .profile -----------------------------------------------------------------

def get_me(account_id, fields=None):
    me = _me(account_id)
    if me is None:
        return _missing("me")
    view = {"id": me["id"], "name": me["name"], "first_name": me["first_name"],
            "last_name": me["last_name"], "link": me["link"], "picture": _picture(me)}
    return _project(view, fields, ME_FIELDS, "User")


def get_profile(user_id, account_id, fields=None):
    if _me(account_id) is None:
        return _missing(user_id)
    u = _store.table("users").get(user_id)
    if u is None:
        return _missing(user_id)
    view = {"id": u["id"], "name": u["name"], "link": u["link"], "picture": _picture(u)}
    if u["kind"] == "user":
        view["first_name"] = u["first_name"]
        view["last_name"] = u["last_name"]
    if u["about"]:
        view["about"] = u["about"]
    if u["hometown"]:
        view["hometown"] = {"name": u["hometown"]}
    if u["location"]:
        view["location"] = {"name": u["location"]}
    if u["work_employer"]:
        view["work"] = [{"employer": {"name": u["work_employer"]},
                         "position": {"name": u["work_position"]}}]
    if u["education_school"]:
        view["education"] = [{"school": {"name": u["education_school"]}, "type": u["education_type"]}]
    return _project(view, fields, PROFILE_FIELDS, "User")


# --- .timeline / .post / .feed --------------------------------------------------------

def list_timeline(account_id, limit=25, after=None):
    me = _me(account_id)
    if me is None:
        return _missing("me")
    rows = _newest_first(p for p in _store.table("posts").rows()
                         if p["from_id"] == me["id"] and not p["group_id"])
    return _page([_post_view(p) for p in rows], limit, after, "me/feed")


def create_post(account_id, message, link=None, privacy=None):
    me = _me(account_id)
    if me is None:
        return _missing("me")
    if not message or not message.strip():
        return _invalid("The parameter message is required")
    if len(message) > MESSAGE_LIMIT:
        return _invalid(f"The message is longer than {MESSAGE_LIMIT} characters")
    if privacy is not None and privacy not in PRIVACY_VALUES:
        return _invalid("The parameter privacy must be one of " + ", ".join(PRIVACY_VALUES))
    if link is not None and not link.startswith(("https://", "http://")):
        return _invalid("The parameter link must be a public http(s) URL")
    suffix = _new_numeric_id()
    post_id = f"{me['id']}_{suffix}"
    _store.table("posts").upsert({
        "id": post_id,
        "from_id": me["id"],
        "message": message,
        "link": link or "",
        "privacy": privacy or "ALL_FRIENDS",
        "created_time": _graph_time(_now()),
        "permalink_url": f"https://www.facebook.com/{me['id']}/posts/{suffix}",
        "group_id": "",
        "audience": "timeline",
        "type": "link" if link else "status",
        "reactions_count": 0,
        "comments_count": 0,
    })
    return {"id": post_id}


def get_post(post_id, account_id, fields=None):
    me = _me(account_id)
    p = _store.table("posts").get(post_id)
    if me is None or p is None or not _visible(p, me):
        return _missing(post_id)
    return _project(_post_view(p), fields, POST_FIELDS, "Post")


def _normalize_link(link):
    parts = urllib.parse.urlsplit(link.strip())
    host = (parts.hostname or "").lower()
    if host in ("facebook.com", "m.facebook.com", "web.facebook.com", "mbasic.facebook.com"):
        host = "www.facebook.com"
    return f"{host}{parts.path.rstrip('/')}"


def get_post_by_link(link, account_id):
    me = _me(account_id)
    if me is None:
        return _missing("posts")
    wanted = _normalize_link(link)
    for p in _store.table("posts").rows():
        if _normalize_link(p["permalink_url"]) == wanted and _visible(p, me):
            return _post_view(p)
    return _missing(link)


def list_home(account_id, limit=25, after=None):
    me = _me(account_id)
    if me is None:
        return _missing("me")
    rows = _newest_first(p for p in _store.table("posts").rows()
                         if p["from_id"] != me["id"] and _visible(p, me))
    return _page([_post_view(p) for p in rows], limit, after, "me/home")


# --- .groups ----------------------------------------------------------------------------

def _group_view(g):
    return {"id": g["id"], "name": g["name"], "description": g["description"],
            "privacy": g["privacy"], "member_count": g["member_count"]}


def list_groups(account_id, limit=25, after=None):
    me = _me(account_id)
    if me is None:
        return _missing("me")
    groups = [g for g in _store.table("groups").rows() if _is_member(g["id"], me["id"])]
    groups.sort(key=lambda g: g["name"])
    return _page([_group_view(g) for g in groups], limit, after, "me/groups")


def list_group_feed(group_id, account_id, limit=25, after=None):
    me = _me(account_id)
    g = _store.table("groups").get(group_id)
    if me is None or g is None or not _is_member(group_id, me["id"]):
        return _missing(group_id)
    rows = _newest_first(p for p in _store.table("posts").rows() if p["group_id"] == group_id)
    return _page([_post_view(p) for p in rows], limit, after, f"{group_id}/feed")


# --- .saved -------------------------------------------------------------------------------

def list_saved(account_id, limit=25, after=None):
    me = _me(account_id)
    if me is None:
        return _missing("me")
    rows = sorted(_store.table("saved_items").find(lambda r: r["user_id"] == me["id"]),
                  key=lambda r: r["saved_at"], reverse=True)
    views = []
    for r in rows:
        view = {"id": r["id"], "type": r["item_type"], "title": r["title"], "url": r["url"],
                "collection_name": r["collection_name"], "saved_at": r["saved_at"]}
        if r["target_id"]:
            view["target_id"] = r["target_id"]
        views.append(view)
    return _page(views, limit, after, "me/saved")


# --- .marketplace --------------------------------------------------------------------------

def search_listings(q=None, category=None, min_price=None, max_price=None, location=None,
                    condition=None, limit=25, after=None):
    listings = _store.table("listings").rows()
    if category:
        known = {l["category"].lower() for l in listings}
        if category.lower() not in known:
            return _invalid("The parameter category must be one of: "
                            + ", ".join(sorted({l["category"] for l in listings})))
    if condition and condition not in CONDITIONS:
        return _invalid("The parameter condition must be one of: " + ", ".join(CONDITIONS))
    if min_price is not None and min_price < 0:
        return _invalid("The parameter min_price must not be negative")
    if max_price is not None and max_price < 0:
        return _invalid("The parameter max_price must not be negative")
    if min_price is not None and max_price is not None and min_price > max_price:
        return _invalid("min_price must not be greater than max_price")
    tokens = [t for t in (q or "").lower().split() if t]
    rows = []
    for l in listings:
        if tokens:
            haystack = f"{l['title']} {l['description']} {l['category']}".lower()
            if not all(t in haystack for t in tokens):
                continue
        if category and l["category"].lower() != category.lower():
            continue
        if min_price is not None and l["price"] < min_price:
            continue
        if max_price is not None and l["price"] > max_price:
            continue
        if location and l["city"].lower() != location.strip().lower():
            continue
        if condition and l["condition"] != condition:
            continue
        rows.append(l)
    rows = _newest_first(rows)
    query = {k: v for k, v in (("q", q), ("category", category), ("min_price", min_price),
                                ("max_price", max_price), ("location", location),
                                ("condition", condition)) if v is not None}
    return _page([_listing_view(l) for l in rows], limit, after, "marketplace_listings", query)


def get_listing(listing_id):
    l = _store.table("listings").get(listing_id)
    if l is None:
        return _missing(listing_id)
    return _listing_view(l)


_store.eager_load()
