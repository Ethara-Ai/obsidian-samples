"""Data access module for the Instagram Graph API mock service.

Serves exactly the ten Instagram connector operations the client ranks --
accounts, profile, posts, post-feed, post-story, account-insights, saved-posts,
fetch-post-comments, followers, following -- for the professional accounts
linked to one connected account. Every read is scoped to the accounts the
presented token's connected account owns.
"""

import base64
import hashlib
import sys
import uuid
from datetime import date, timedelta, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent

sys.path.insert(0, str(DATA_DIR.parent))
import _mock_clock  # noqa: E402
from _mutable_store import get_store, read_seed_with_ctx, strict_bool, strict_int  # noqa: E402
from _connector_auth import ConnectorAuth  # noqa: E402

_API = "instagram-api"
_store = get_store(_API)

GRAPH_VERSION = "v21.0"
CAPTION_LIMIT = 2200
HASHTAG_LIMIT = 30
MEDIA_FIELDS = ("id", "caption", "media_type", "media_product_type", "media_url", "permalink",
                "timestamp", "username", "like_count", "comments_count", "is_comment_enabled")
PROFILE_FIELDS = ("id", "username", "name", "biography", "website", "profile_picture_url",
                  "account_type", "category", "followers_count", "follows_count", "media_count")
ACCOUNT_FIELDS = ("id", "username", "name", "account_type", "profile_picture_url")
INSIGHT_METRICS = {
    "reach": ("Reach", "Unique accounts that saw any of your content."),
    "impressions": ("Impressions", "Total times your content was shown."),
    "profile_views": ("Profile views", "Times your profile was viewed."),
    "website_clicks": ("Website clicks", "Taps on the website link in your profile."),
    "follower_count": ("Follower count", "New followers gained in the period."),
}
INSIGHT_PERIODS = {"day": 1, "week": 7, "days_28": 28}


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _coerce_media_row(r):
    out = _strip_ctx(r)
    out["like_count"] = strict_int(out, "like_count")
    out["is_comment_enabled"] = strict_bool(out, "is_comment_enabled")
    return out


def _coerce_comment_row(r):
    out = _strip_ctx(r)
    out["like_count"] = strict_int(out, "like_count")
    out["hidden"] = strict_bool(out, "hidden")
    return out


def _coerce_insight_row(r):
    out = _strip_ctx(r)
    for metric in ("reach", "impressions", "profile_views", "website_clicks"):
        out[metric] = strict_int(out, metric)
    out["_pk"] = f"{out['ig_user_id']}:{out['date']}"
    return out


def _with_pair_pk(r):
    out = _strip_ctx(r)
    out["_pk"] = f"{out['ig_user_id']}:{out['id']}"
    return out


_store.register("accounts", primary_key="id",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("accounts.json", "accounts")])
_store.register("media", primary_key="id",
                initial_loader=lambda: [_coerce_media_row(r) for r in _load("media.json", "media")],
                row_coercer=_coerce_media_row)
_store.register("comments", primary_key="id",
                initial_loader=lambda: [_coerce_comment_row(r) for r in _load("comments.json", "comments")],
                row_coercer=_coerce_comment_row)
_store.register("followers", primary_key="_pk",
                initial_loader=lambda: [_with_pair_pk(r) for r in _load("followers.json", "followers")])
_store.register("following", primary_key="_pk",
                initial_loader=lambda: [_with_pair_pk(r) for r in _load("following.json", "following")])
_store.register("saved_media", primary_key="id",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("saved_media.json", "saved_media")])
_store.register("insights", primary_key="_pk",
                initial_loader=lambda: [_coerce_insight_row(r) for r in _load("insights.json", "insights")],
                row_coercer=_coerce_insight_row)
_store.register("media_containers", primary_key="id", initial_loader=lambda: [])

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


def _new_numeric_id(prefix):
    return f"{prefix}{uuid.uuid4().int % 10**13:013d}"


def _owned(ig_user_id, account_id):
    row = _store.table("accounts").get(ig_user_id)
    if row is None or row.get("owner_account_id") != account_id:
        return None
    return row


def _project(view, fields, allowed, node_type):
    if not fields:
        return view
    wanted = [f.strip() for f in fields.split(",") if f.strip()]
    for name in wanted:
        if name not in allowed:
            return _invalid(f"Tried accessing nonexisting field ({name}) on node type ({node_type})")
    return {"id": view["id"], **{name: view[name] for name in wanted}}


def _cursor(index):
    return base64.urlsafe_b64encode(f"ig:{index}".encode()).decode().rstrip("=")


def _cursor_index(cursor):
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        prefix, _, index = raw.partition(":")
        if prefix != "ig":
            raise ValueError(raw)
        return int(index)
    except (ValueError, UnicodeDecodeError):
        return None


def _page(items, limit, after, path):
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
        paging["next"] = (f"/{GRAPH_VERSION}/{path}?limit={limit}"
                          f"&after={_cursor(start + len(window) - 1)}")
    return {"data": window, "paging": paging}


def _counts(ig_user_id):
    media = [m for m in _store.table("media").rows()
             if m["ig_user_id"] == ig_user_id and m["media_product_type"] != "STORY"]
    followers = _store.table("followers").find(lambda r: r["ig_user_id"] == ig_user_id)
    following = _store.table("following").find(lambda r: r["ig_user_id"] == ig_user_id)
    return len(followers), len(following), len(media)


def _comment_view(c):
    return {"id": c["id"], "text": c["text"], "username": c["username"],
            "from": {"id": c["from_id"], "username": c["username"]},
            "timestamp": c["timestamp"], "like_count": c["like_count"], "hidden": c["hidden"]}


def _media_view(m, username):
    comments = _store.table("comments").find(lambda c: c["media_id"] == m["id"])
    return {
        "id": m["id"], "caption": m["caption"], "media_type": m["media_type"],
        "media_product_type": m["media_product_type"], "media_url": m["media_url"],
        "permalink": m["permalink"], "timestamp": m["timestamp"], "username": username,
        "like_count": m["like_count"], "comments_count": len(comments),
        "is_comment_enabled": m["is_comment_enabled"],
    }


# --- accounts / profile -------------------------------------------------------

def list_accounts(account_id, fields=None):
    rows = sorted(_store.table("accounts").find(lambda a: a.get("owner_account_id") == account_id),
                  key=lambda a: a["connected_at"])
    data = []
    for a in rows:
        view = {k: a[k] for k in ACCOUNT_FIELDS}
        projected = _project(view, fields, ACCOUNT_FIELDS, "IGUser")
        if isinstance(projected, GraphError):
            return projected
        data.append(projected)
    return {"data": data}


def get_profile(ig_user_id, account_id, fields=None):
    a = _owned(ig_user_id, account_id)
    if a is None:
        return _missing(ig_user_id)
    followers, following, media = _counts(ig_user_id)
    view = {**{k: a[k] for k in PROFILE_FIELDS if k in a},
            "followers_count": followers, "follows_count": following, "media_count": media}
    return _project(view, fields, PROFILE_FIELDS, "IGUser")


# --- posts ----------------------------------------------------------------------

def list_media(ig_user_id, account_id, limit=25, after=None, fields=None):
    a = _owned(ig_user_id, account_id)
    if a is None:
        return _missing(ig_user_id)
    rows = sorted((m for m in _store.table("media").rows()
                   if m["ig_user_id"] == ig_user_id and m["media_product_type"] != "STORY"),
                  key=lambda m: m["timestamp"], reverse=True)
    views = []
    for m in rows:
        projected = _project(_media_view(m, a["username"]), fields, MEDIA_FIELDS, "IGMedia")
        if isinstance(projected, GraphError):
            return projected
        views.append(projected)
    return _page(views, limit, after, f"{ig_user_id}/media")


# --- publishing: post-feed and post-story share Instagram's container flow --------

def create_container(ig_user_id, account_id, media_type=None, image_url=None, video_url=None,
                     caption=None):
    if _owned(ig_user_id, account_id) is None:
        return _missing(ig_user_id)
    kind = (media_type or ("VIDEO" if video_url and not image_url else "IMAGE")).upper()
    if kind not in ("IMAGE", "VIDEO", "STORIES"):
        return _invalid("The parameter media_type must be one of IMAGE, VIDEO, STORIES")
    if image_url and video_url:
        return _invalid("Send image_url or video_url, not both")
    if kind == "IMAGE" and not image_url:
        return _invalid("The parameter image_url is required for media_type IMAGE")
    if kind == "VIDEO" and not video_url:
        return _invalid("The parameter video_url is required for media_type VIDEO")
    if kind == "STORIES" and not (image_url or video_url):
        return _invalid("A story needs an image_url or a video_url")
    source = image_url or video_url
    if not source.startswith(("https://", "http://")):
        return _invalid("The media URL must be a public http(s) URL")
    if kind == "STORIES" and caption:
        return _invalid("Stories do not support a caption")
    if caption and len(caption) > CAPTION_LIMIT:
        return _invalid(f"The caption is longer than {CAPTION_LIMIT} characters")
    if caption and caption.count("#") > HASHTAG_LIMIT:
        return _invalid(f"A caption can carry at most {HASHTAG_LIMIT} hashtags")
    container = {
        "id": _new_numeric_id("1789"),
        "ig_user_id": ig_user_id,
        "media_type": "VIDEO" if video_url else "IMAGE",
        "media_product_type": "STORY" if kind == "STORIES" else "FEED",
        "image_url": image_url or "",
        "video_url": video_url or "",
        "caption": caption or "",
        "status_code": "FINISHED",
        "created_at": _graph_time(_now()),
        "published_media_id": "",
    }
    _store.table("media_containers").upsert(container)
    return {"id": container["id"]}


def publish_container(ig_user_id, account_id, creation_id):
    a = _owned(ig_user_id, account_id)
    if a is None:
        return _missing(ig_user_id)
    container = _store.table("media_containers").get(creation_id)
    if container is None or container["ig_user_id"] != ig_user_id:
        return _invalid(f"Invalid creation_id {creation_id}: no media container on this account")
    if container["published_media_id"]:
        return _invalid(f"The media container {creation_id} was already published as "
                        f"media {container['published_media_id']}")
    media_id = _new_numeric_id("1805")
    story = container["media_product_type"] == "STORY"
    permalink = (f"https://www.instagram.com/stories/{a['username']}/{media_id}/" if story
                 else f"https://www.instagram.com/p/{media_id[-11:]}/")
    _store.table("media").upsert({
        "id": media_id,
        "ig_user_id": ig_user_id,
        "media_type": container["media_type"],
        "media_product_type": container["media_product_type"],
        "caption": container["caption"],
        "media_url": container["image_url"] or container["video_url"],
        "permalink": permalink,
        "timestamp": _graph_time(_now()),
        "like_count": 0,
        "is_comment_enabled": not story,
    })
    _store.table("media_containers").patch(creation_id, {"published_media_id": media_id,
                                                         "status_code": "PUBLISHED"})
    return {"id": media_id}


# --- account insights -----------------------------------------------------------

def _parse_day(value, name):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return _invalid(f"The parameter {name} must be a YYYY-MM-DD date")


def get_insights(ig_user_id, account_id, metric, period="day", since=None, until=None):
    if _owned(ig_user_id, account_id) is None:
        return _missing(ig_user_id)
    names = [m.strip() for m in (metric or "").split(",") if m.strip()]
    if not names:
        return _invalid("The parameter metric is required")
    unknown = [n for n in names if n not in INSIGHT_METRICS]
    if unknown:
        return _invalid(f"metric[{names.index(unknown[0])}] must be one of the following values: "
                        + ", ".join(INSIGHT_METRICS))
    if period not in INSIGHT_PERIODS:
        return _invalid("The parameter period must be one of: " + ", ".join(INSIGHT_PERIODS))
    daily = {r["date"]: r for r in _store.table("insights").find(lambda r: r["ig_user_id"] == ig_user_id)}
    gained = {}
    for f in _store.table("followers").find(lambda r: r["ig_user_id"] == ig_user_id):
        gained[f["followed_at"][:10]] = gained.get(f["followed_at"][:10], 0) + 1
    if not daily:
        return {"data": []}
    last = max(date.fromisoformat(d) for d in daily)
    end = _parse_day(until, "until") if until else last
    if isinstance(end, GraphError):
        return end
    span = INSIGHT_PERIODS[period]
    begin = _parse_day(since, "since") if since else end - timedelta(days=(6 if period == "day" else span - 1))
    if isinstance(begin, GraphError):
        return begin
    if begin > end:
        return _invalid("since must not be later than until")

    def value(name, day):
        key = day.isoformat()
        if name == "follower_count":
            return gained.get(key, 0)
        return daily[key][name] if key in daily else 0

    def end_time(day):
        return f"{(day + timedelta(days=1)).isoformat()}T07:00:00+0000"

    data = []
    for name in names:
        if period == "day":
            days = [begin + timedelta(days=i) for i in range((end - begin).days + 1)]
            values = [{"value": value(name, d), "end_time": end_time(d)} for d in days]
        else:
            window = [end - timedelta(days=i) for i in range(span)]
            values = [{"value": sum(value(name, d) for d in window), "end_time": end_time(end)}]
        title, description = INSIGHT_METRICS[name]
        data.append({"name": name, "period": period, "values": values, "title": title,
                     "description": description, "id": f"{ig_user_id}/insights/{name}/{period}"})
    return {"data": data}


# --- saved posts, comments, relationships ----------------------------------------

def list_saved(ig_user_id, account_id, limit=25, after=None):
    if _owned(ig_user_id, account_id) is None:
        return _missing(ig_user_id)
    rows = sorted(_store.table("saved_media").find(lambda r: r["ig_user_id"] == ig_user_id),
                  key=lambda r: r["saved_at"], reverse=True)
    views = [{"id": r["media_id"], "owner_username": r["owner_username"], "media_type": r["media_type"],
              "caption": r["caption"], "permalink": r["permalink"], "collection": r["collection"],
              "saved_at": r["saved_at"]} for r in rows]
    return _page(views, limit, after, f"{ig_user_id}/saved_media")


def list_comments(media_id, account_id, limit=25, after=None):
    m = _store.table("media").get(media_id)
    if m is None or _owned(m["ig_user_id"], account_id) is None:
        return _missing(media_id)
    rows = _store.table("comments").find(lambda c: c["media_id"] == media_id)
    tops = sorted((c for c in rows if not c["parent_id"]), key=lambda c: c["timestamp"], reverse=True)
    views = []
    for c in tops:
        replies = sorted((r for r in rows if r["parent_id"] == c["id"]), key=lambda r: r["timestamp"])
        views.append({**_comment_view(c), "replies": {"data": [_comment_view(r) for r in replies]}})
    return _page(views, limit, after, f"{media_id}/comments")


def list_relationships(table, ig_user_id, account_id, limit=25, after=None):
    if _owned(ig_user_id, account_id) is None:
        return _missing(ig_user_id)
    rows = sorted(_store.table(table).find(lambda r: r["ig_user_id"] == ig_user_id),
                  key=lambda r: r["followed_at"], reverse=True)
    views = [{"id": r["id"], "username": r["username"], "name": r["name"],
              "followed_at": r["followed_at"]} for r in rows]
    return _page(views, limit, after, f"{ig_user_id}/{table}")


_store.eager_load()
