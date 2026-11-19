"""Data access module for the Spotify Web API mock service.

Serves exactly the ten Spotify connector operations the client ranks -- search,
library, add-to-collection, create-collection, update-collection, devices, play,
now-playing, transfer, playlist-tracks -- for one connected listener. Catalog
reads (search) are global; the library, playlists the account owns or follows,
devices and playback state are scoped to the connected account the presented
token belongs to.

Mock simplifications (also stated in api_test_results.md): ``q`` is matched as
free text (no ``artist:`` style field filters), playback progress is stored when
a command changes it rather than advancing with the clock, and there is no
queue or skip.
"""

import base64
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

DATA_DIR = Path(__file__).parent

sys.path.insert(0, str(DATA_DIR.parent))
import _mock_clock  # noqa: E402
from _mutable_store import get_store, read_seed_with_ctx, strict_bool, strict_int, opt_csv_list  # noqa: E402
from _connector_auth import ConnectorAuth  # noqa: E402

_API = "spotify-api"
_store = get_store(_API)

API_BASE = "https://api.spotify.com/v1"
WEB_BASE = "https://open.spotify.com"
SEARCH_TYPES = ("track", "album", "artist", "playlist", "show", "episode")
ITEM_KINDS = ("track", "episode")
CONTEXT_KINDS = ("album", "artist", "playlist", "show")
MAX_ADD_URIS = 100
_B62 = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _coerce_artist_row(r):
    out = _strip_ctx(r)
    out["popularity"] = strict_int(out, "popularity")
    out["followers"] = strict_int(out, "followers")
    out["genres"] = opt_csv_list(out, "genres", sep=";")
    return out


def _coerce_track_row(r):
    out = _strip_ctx(r)
    for column in ("track_number", "disc_number", "duration_ms", "popularity"):
        out[column] = strict_int(out, column)
    out["explicit"] = strict_bool(out, "explicit")
    out["artist_ids"] = opt_csv_list(out, "artist_ids", sep=";")
    return out


def _coerce_episode_row(r):
    out = _strip_ctx(r)
    out["duration_ms"] = strict_int(out, "duration_ms")
    out["explicit"] = strict_bool(out, "explicit")
    return out


def _coerce_playlist_row(r):
    out = _strip_ctx(r)
    out["public"] = strict_bool(out, "public")
    out["collaborative"] = strict_bool(out, "collaborative")
    return out


def _coerce_item_row(r):
    out = _strip_ctx(r)
    out["position"] = strict_int(out, "position")
    return out


def _coerce_follow_row(r):
    out = _strip_ctx(r)
    out["_pk"] = f"{out['account_id']}:{out['playlist_id']}"
    return out


def _coerce_saved_row(r):
    out = _strip_ctx(r)
    out["_pk"] = f"{out['account_id']}:{out['track_id']}"
    return out


def _coerce_device_row(r):
    out = _strip_ctx(r)
    out["is_restricted"] = strict_bool(out, "is_restricted")
    out["is_private_session"] = strict_bool(out, "is_private_session")
    out["volume_percent"] = strict_int(out, "volume_percent")
    return out


def _coerce_playback_row(r):
    out = _strip_ctx(r)
    out["progress_ms"] = strict_int(out, "progress_ms")
    out["is_playing"] = strict_bool(out, "is_playing")
    out["shuffle_state"] = strict_bool(out, "shuffle_state")
    return out


def _plain(filename, table):
    return lambda: [_strip_ctx(r) for r in _load(filename, table)]


def _coerced(filename, table, coercer):
    return lambda: [coercer(r) for r in _load(filename, table)]


_store.register("accounts", primary_key="id", initial_loader=_plain("accounts.json", "accounts"))
_store.register("users", primary_key="id", initial_loader=_plain("users.json", "users"))
_store.register("artists", primary_key="id", row_coercer=_coerce_artist_row,
                initial_loader=_coerced("artists.json", "artists", _coerce_artist_row))
_store.register("albums", primary_key="id", initial_loader=_plain("albums.json", "albums"))
_store.register("tracks", primary_key="id", row_coercer=_coerce_track_row,
                initial_loader=_coerced("tracks.json", "tracks", _coerce_track_row))
_store.register("shows", primary_key="id", initial_loader=_plain("shows.json", "shows"))
_store.register("episodes", primary_key="id", row_coercer=_coerce_episode_row,
                initial_loader=_coerced("episodes.json", "episodes", _coerce_episode_row))
_store.register("playlists", primary_key="id", row_coercer=_coerce_playlist_row,
                initial_loader=_coerced("playlists.json", "playlists", _coerce_playlist_row))
_store.register("playlist_items", primary_key="id", row_coercer=_coerce_item_row,
                initial_loader=_coerced("playlist_items.json", "playlist_items", _coerce_item_row))
_store.register("playlist_follows", primary_key="_pk", row_coercer=_coerce_follow_row,
                initial_loader=_coerced("playlist_follows.json", "playlist_follows", _coerce_follow_row))
_store.register("saved_tracks", primary_key="_pk", row_coercer=_coerce_saved_row,
                initial_loader=_coerced("saved_tracks.json", "saved_tracks", _coerce_saved_row))
_store.register("devices", primary_key="id", row_coercer=_coerce_device_row,
                initial_loader=_coerced("devices.json", "devices", _coerce_device_row))
_store.register("playback", primary_key="account_id", row_coercer=_coerce_playback_row,
                initial_loader=_coerced("playback.json", "playback", _coerce_playback_row))

auth = ConnectorAuth(_API, store=_store, data_dir=DATA_DIR)


class SpotifyError:
    """A Spotify error envelope and the HTTP status it is served with."""

    def __init__(self, status, message, reason=None):
        self.status = status
        error = {"status": status, "message": message}
        if reason:
            error["reason"] = reason
        self.body = {"error": error}


def _bad(message):
    return SpotifyError(400, message)


def _not_found(message="Not found."):
    return SpotifyError(404, message)


def _no_active_device():
    return SpotifyError(404, "Player command failed: No active device found", "NO_ACTIVE_DEVICE")


def _restricted():
    return SpotifyError(403, "Player command failed: Restriction violated", "UNKNOWN")


def _now():
    return _mock_clock.now(timezone.utc)


def _iso(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_id():
    n = uuid.uuid4().int
    out = ""
    for _ in range(22):
        n, r = divmod(n, 62)
        out += _B62[r]
    return out


def _snapshot():
    return base64.b64encode(uuid.uuid4().bytes + uuid.uuid4().bytes[:8]).decode()


def _account(account_id):
    return _store.table("accounts").get(account_id)


def _user_id(account_id):
    acct = _account(account_id)
    return acct["user_id"] if acct else ""


# --- paging -----------------------------------------------------------------------------------

def _check_window(limit, offset, max_limit, default_limit, max_offset=None):
    size = default_limit if limit is None else limit
    start = 0 if offset is None else offset
    if size < 1 or size > max_limit:
        return _bad(f"Invalid limit: must be between 1 and {max_limit}")
    if start < 0 or (max_offset is not None and start > max_offset):
        return _bad("Invalid offset")
    return size, start


def _paging(items, limit, offset, path, params=None):
    """A Spotify paging object over ``items``; ``path`` is relative to /v1."""
    def href(off):
        query = urlencode({**(params or {}), "offset": off, "limit": limit})
        return f"/v1/{path}?{query}"
    window = items[offset:offset + limit]
    return {"href": href(offset), "items": window, "limit": limit,
            "next": href(offset + limit) if offset + limit < len(items) else None,
            "offset": offset, "previous": href(max(0, offset - limit)) if offset > 0 else None,
            "total": len(items)}


# --- uris and views ---------------------------------------------------------------------------

def _uri(kind, row_id):
    return f"spotify:{kind}:{row_id}"


def _parse_uri(value):
    parts = (value or "").split(":")
    if len(parts) != 3 or parts[0] != "spotify" or not parts[1] or not parts[2]:
        return None
    return parts[1], parts[2]


def _links(kind, row_id):
    return {"external_urls": {"spotify": f"{WEB_BASE}/{kind}/{row_id}"},
            "href": f"{API_BASE}/{kind}s/{row_id}"}


def _images(row_id):
    return [{"url": f"https://cdn.mock-spotify.example/i/{row_id}.jpg", "height": 640, "width": 640}]


def _artist_simple(a):
    return {**_links("artist", a["id"]), "id": a["id"], "name": a["name"], "type": "artist",
            "uri": _uri("artist", a["id"])}


def _artist_full(a):
    return {**_artist_simple(a), "followers": {"href": None, "total": a["followers"]},
            "genres": a["genres"], "images": _images(a["id"]), "popularity": a["popularity"]}


def _album_simple(album, artists):
    total = len(_store.table("tracks").find(lambda t: t["album_id"] == album["id"]))
    return {"album_type": album["album_type"], "total_tracks": total, **_links("album", album["id"]),
            "id": album["id"], "images": _images(album["id"]), "name": album["name"],
            "release_date": album["release_date"], "release_date_precision": "day", "type": "album",
            "uri": _uri("album", album["id"]), "is_playable": True,
            "artists": [_artist_simple(a) for a in artists.get(album["artist_id"], [])]}


def _catalog():
    """Lookup maps used to build views without a store read per row."""
    artists = {a["id"]: a for a in _store.table("artists").rows()}
    return {"artists": {k: [v] for k, v in artists.items()}, "artist_rows": artists,
            "albums": {a["id"]: a for a in _store.table("albums").rows()},
            "shows": {s["id"]: s for s in _store.table("shows").rows()}}


def _track_view(t, cat):
    album = cat["albums"].get(t["album_id"])
    return {"album": _album_simple(album, cat["artists"]) if album else None,
            "artists": [_artist_simple(cat["artist_rows"][i]) for i in t["artist_ids"] if i in cat["artist_rows"]],
            "disc_number": t["disc_number"], "duration_ms": t["duration_ms"], "explicit": t["explicit"],
            **_links("track", t["id"]), "id": t["id"], "is_local": False, "is_playable": True,
            "name": t["name"], "popularity": t["popularity"], "preview_url": None,
            "track_number": t["track_number"], "type": "track", "uri": _uri("track", t["id"])}


def _show_view(s):
    total = len(_store.table("episodes").find(lambda e: e["show_id"] == s["id"]))
    return {"description": s["description"], "explicit": False, **_links("show", s["id"]), "id": s["id"],
            "images": _images(s["id"]), "is_externally_hosted": False, "languages": [s["language"]],
            "media_type": "audio", "name": s["name"], "publisher": s["publisher"],
            "total_episodes": total, "type": "show", "uri": _uri("show", s["id"])}


def _episode_view(e, cat):
    show = cat["shows"].get(e["show_id"])
    return {"description": e["description"], "duration_ms": e["duration_ms"], "explicit": e["explicit"],
            **_links("episode", e["id"]), "id": e["id"], "images": _images(e["show_id"]),
            "is_externally_hosted": False, "is_playable": True, "languages": [show["language"]] if show else [],
            "name": e["name"], "release_date": e["release_date"], "release_date_precision": "day",
            "type": "episode", "uri": _uri("episode", e["id"]),
            "show": _show_view(show) if show else None}


def _user_ref(user_id):
    user = _store.table("users").get(user_id)
    return {"display_name": user["display_name"] if user else user_id,
            "external_urls": {"spotify": f"{WEB_BASE}/user/{user_id}"},
            "href": f"{API_BASE}/users/{user_id}", "id": user_id, "type": "user",
            "uri": _uri("user", user_id)}


def _playlist_view(p, full=False):
    items = _store.table("playlist_items").find(lambda i: i["playlist_id"] == p["id"])
    view = {"collaborative": p["collaborative"], "description": p["description"], **_links("playlist", p["id"]),
            "id": p["id"], "images": _images(p["id"]), "name": p["name"], "owner": _user_ref(p["owner_id"]),
            "public": p["public"], "snapshot_id": p["snapshot_id"],
            "tracks": {"href": f"{API_BASE}/playlists/{p['id']}/tracks", "total": len(items)},
            "type": "playlist", "uri": _uri("playlist", p["id"])}
    if full:
        followers = _store.table("playlist_follows").find(lambda f: f["playlist_id"] == p["id"])
        view["followers"] = {"href": None, "total": len(followers)}
        view["tracks"] = {"href": f"{API_BASE}/playlists/{p['id']}/tracks", "items": [], "limit": 100,
                          "next": None, "offset": 0, "previous": None, "total": len(items)}
    return view


def _item_row(kind, row_id):
    return _store.table("tracks" if kind == "track" else "episodes").get(row_id)


def _item_view(kind, row, cat):
    return _track_view(row, cat) if kind == "track" else _episode_view(row, cat)


def _resolve_item_uri(value):
    """``(kind, row)`` for a spotify:track/episode uri that exists in the catalog, else None."""
    parsed = _parse_uri(value)
    if parsed is None or parsed[0] not in ITEM_KINDS:
        return None
    row = _item_row(*parsed)
    return (parsed[0], row) if row is not None else None


# --- search -------------------------------------------------------------------------------------

def _matches(terms, *haystacks):
    text = " ".join(h for h in haystacks if h).casefold()
    return all(term in text for term in terms)


def search(q, types, limit=None, offset=None):
    if q is None or not q.strip():
        return _bad("No search query")
    if not types:
        return _bad("Missing parameter type")
    kinds = [t.strip() for t in types.split(",") if t.strip()]
    for kind in kinds:
        if kind not in SEARCH_TYPES:
            return _bad(f"Invalid type: {kind}. Must be one of {', '.join(SEARCH_TYPES)}")
    window = _check_window(limit, offset, 50, 20, max_offset=1000)
    if isinstance(window, SpotifyError):
        return window
    size, start = window
    terms = q.casefold().split()
    cat = _catalog()
    artist_names = lambda ids: " ".join(cat["artist_rows"][i]["name"] for i in ids if i in cat["artist_rows"])
    body = {}
    for kind in dict.fromkeys(kinds):
        if kind == "track":
            rows = [t for t in _store.table("tracks").rows() if _matches(
                terms, t["name"], artist_names(t["artist_ids"]),
                cat["albums"][t["album_id"]]["name"] if t["album_id"] in cat["albums"] else "")]
            rows.sort(key=lambda t: (-t["popularity"], t["name"]))
            views = [_track_view(t, cat) for t in rows]
        elif kind == "album":
            rows = [a for a in cat["albums"].values() if _matches(
                terms, a["name"], artist_names([a["artist_id"]]))]
            rows.sort(key=lambda a: (a["release_date"], a["name"]), reverse=True)
            views = [_album_simple(a, cat["artists"]) for a in rows]
        elif kind == "artist":
            rows = [a for a in cat["artist_rows"].values() if _matches(terms, a["name"], " ".join(a["genres"]))]
            rows.sort(key=lambda a: (-a["popularity"], a["name"]))
            views = [_artist_full(a) for a in rows]
        elif kind == "playlist":
            rows = [p for p in _store.table("playlists").rows()
                    if p["public"] and _matches(terms, p["name"], p["description"])]
            rows.sort(key=lambda p: p["name"].casefold())
            views = [_playlist_view(p) for p in rows]
        elif kind == "show":
            rows = [s for s in cat["shows"].values() if _matches(terms, s["name"], s["publisher"], s["description"])]
            rows.sort(key=lambda s: s["name"].casefold())
            views = [_show_view(s) for s in rows]
        else:
            rows = [e for e in _store.table("episodes").rows() if _matches(
                terms, e["name"], e["description"], cat["shows"][e["show_id"]]["name"] if e["show_id"] in cat["shows"] else "")]
            rows.sort(key=lambda e: (e["release_date"], e["name"]), reverse=True)
            views = [_episode_view(e, cat) for e in rows]
        body[kind + "s"] = _paging(views, size, start, "search", {"q": q, "type": ",".join(kinds)})
    return body


# --- library --------------------------------------------------------------------------------------

def list_saved_tracks(account_id, limit=None, offset=None):
    window = _check_window(limit, offset, 50, 20)
    if isinstance(window, SpotifyError):
        return window
    size, start = window
    saved = sorted(_store.table("saved_tracks").find(lambda s: s["account_id"] == account_id),
                   key=lambda s: (s["added_at"], s["track_id"]), reverse=True)
    cat = _catalog()
    items = []
    for s in saved:
        track = _store.table("tracks").get(s["track_id"])
        if track is not None:
            items.append({"added_at": s["added_at"], "track": _track_view(track, cat)})
    return _paging(items, size, start, "me/tracks")


def _followed_ids(account_id):
    return {f["playlist_id"] for f in _store.table("playlist_follows").find(lambda f: f["account_id"] == account_id)}


def list_my_playlists(account_id, limit=None, offset=None):
    window = _check_window(limit, offset, 50, 20)
    if isinstance(window, SpotifyError):
        return window
    size, start = window
    user_id = _user_id(account_id)
    followed = _followed_ids(account_id)
    rows = _store.table("playlists").rows()
    owned = [p for p in rows if p["owner_id"] == user_id]
    others = [p for p in rows if p["id"] in followed and p["owner_id"] != user_id]
    return _paging([_playlist_view(p) for p in owned + others], size, start, "me/playlists")


def _readable_playlist(playlist_id, account_id):
    p = _store.table("playlists").get(playlist_id)
    if p is None:
        return None
    if p["public"] or p["owner_id"] == _user_id(account_id) or playlist_id in _followed_ids(account_id):
        return p
    return None


def list_playlist_tracks(playlist_id, account_id, limit=None, offset=None):
    window = _check_window(limit, offset, 100, 100)
    if isinstance(window, SpotifyError):
        return window
    size, start = window
    if _readable_playlist(playlist_id, account_id) is None:
        return _not_found("Not found.")
    rows = sorted(_store.table("playlist_items").find(lambda i: i["playlist_id"] == playlist_id),
                  key=lambda i: i["position"])
    cat = _catalog()
    items = []
    for r in rows:
        resolved = _resolve_item_uri(r["item_uri"])
        if resolved is None:
            continue
        items.append({"added_at": r["added_at"], "added_by": _user_ref(r["added_by_id"]),
                      "is_local": False, "track": _item_view(resolved[0], resolved[1], cat)})
    return _paging(items, size, start, f"playlists/{playlist_id}/tracks")


# --- playlists (create / update / add) -------------------------------------------------------------

def create_playlist(account_id, name, description=None, public=None, collaborative=None):
    if not name or not name.strip():
        return _bad("Playlist name is required")
    public = True if public is None else public
    collaborative = bool(collaborative)
    if collaborative and public:
        return _bad("Only private playlists can be collaborative")
    row = _store.table("playlists").upsert({
        "id": _new_id(), "name": name, "description": description or "", "owner_id": _user_id(account_id),
        "public": public, "collaborative": collaborative, "snapshot_id": _snapshot()})
    return _playlist_view(row, full=True)


def update_playlist(playlist_id, account_id, changes):
    """``changes`` holds only the body keys the caller sent (name, description, public, collaborative)."""
    p = _readable_playlist(playlist_id, account_id)
    if p is None:
        return _not_found("Not found.")
    if p["owner_id"] != _user_id(account_id):
        return SpotifyError(403, "You cannot change this playlist")
    if not changes:
        return _bad("No changes supplied: send name, description, public or collaborative")
    patch = {}
    if "name" in changes:
        if not changes["name"] or not changes["name"].strip():
            return _bad("Playlist name must not be empty")
        patch["name"] = changes["name"]
    if "description" in changes:
        patch["description"] = changes["description"] or ""
    for key in ("public", "collaborative"):
        if key in changes:
            if changes[key] is None:
                return _bad(f"{key} must be true or false")
            patch[key] = changes[key]
    if patch.get("collaborative", p["collaborative"]) and patch.get("public", p["public"]):
        return _bad("Only private playlists can be collaborative")
    _store.table("playlists").patch(playlist_id, patch)
    return None


def add_playlist_items(playlist_id, account_id, uris, position=None):
    p = _readable_playlist(playlist_id, account_id)
    if p is None:
        return _not_found("Not found.")
    mine = p["owner_id"] == _user_id(account_id)
    if not mine and not (p["collaborative"] and playlist_id in _followed_ids(account_id)):
        return SpotifyError(403, "You cannot add tracks to a playlist you don't own.")
    if not uris:
        return _bad("No uris provided")
    if len(uris) > MAX_ADD_URIS:
        return _bad(f"A maximum of {MAX_ADD_URIS} items can be added in one request")
    for uri in uris:
        if _resolve_item_uri(uri) is None:
            return _bad(f"Invalid track uri: {uri}")
    rows = sorted(_store.table("playlist_items").find(lambda i: i["playlist_id"] == playlist_id),
                  key=lambda i: i["position"])
    at = len(rows) if position is None else position
    if at < 0 or at > len(rows):
        return _bad("Index out of bounds")
    for row in rows[at:]:
        _store.table("playlist_items").patch(row["id"], {"position": row["position"] + len(uris)})
    stamp = _iso(_now())
    for offset, uri in enumerate(uris):
        _store.table("playlist_items").upsert({
            "id": "pt-" + uuid.uuid4().hex[:12], "playlist_id": playlist_id, "position": at + offset,
            "item_uri": uri, "added_at": stamp, "added_by_id": _user_id(account_id)})
    snapshot = _snapshot()
    _store.table("playlists").patch(playlist_id, {"snapshot_id": snapshot})
    return {"snapshot_id": snapshot}


# --- player ----------------------------------------------------------------------------------------

def _device_view(d, active_id):
    return {"id": d["id"], "is_active": d["id"] == active_id, "is_private_session": d["is_private_session"],
            "is_restricted": d["is_restricted"], "name": d["name"], "supports_volume": True,
            "type": d["type"], "volume_percent": d["volume_percent"]}


def _playback(account_id):
    return _store.table("playback").get(account_id)


def list_devices(account_id):
    state = _playback(account_id)
    active = state["device_id"] if state else ""
    rows = _store.table("devices").find(lambda d: d["account_id"] == account_id)
    return {"devices": [_device_view(d, active) for d in rows]}


def _owned_device(device_id, account_id):
    d = _store.table("devices").get(device_id)
    if d is None or d["account_id"] != account_id:
        return None
    return d


def _context_items(kind, row_id, account_id):
    """Ordered item uris for a context, or a SpotifyError."""
    if kind == "album":
        if _store.table("albums").get(row_id) is None:
            return _bad("Invalid context uri: album not found")
        rows = sorted(_store.table("tracks").find(lambda t: t["album_id"] == row_id),
                      key=lambda t: (t["disc_number"], t["track_number"]))
        return [_uri("track", t["id"]) for t in rows]
    if kind == "artist":
        if _store.table("artists").get(row_id) is None:
            return _bad("Invalid context uri: artist not found")
        rows = sorted(_store.table("tracks").find(lambda t: row_id in t["artist_ids"]),
                      key=lambda t: (-t["popularity"], t["name"]))
        return [_uri("track", t["id"]) for t in rows]
    if kind == "show":
        if _store.table("shows").get(row_id) is None:
            return _bad("Invalid context uri: show not found")
        rows = sorted(_store.table("episodes").find(lambda e: e["show_id"] == row_id),
                      key=lambda e: (e["release_date"], e["id"]), reverse=True)
        return [_uri("episode", e["id"]) for e in rows]
    if _readable_playlist(row_id, account_id) is None:
        return _bad("Invalid context uri: playlist not found")
    rows = sorted(_store.table("playlist_items").find(lambda i: i["playlist_id"] == row_id),
                  key=lambda i: i["position"])
    return [r["item_uri"] for r in rows]


def _pick_offset(items, offset, context_kind):
    """Index of the starting item, or a SpotifyError."""
    if not offset:
        return 0
    if context_kind in ("artist", "show"):
        return _bad(f"offset is not supported for {context_kind} contexts")
    if ("position" in offset) == ("uri" in offset):
        return _bad("offset must contain exactly one of position or uri")
    if "position" in offset:
        if offset["position"] < 0 or offset["position"] >= len(items):
            return _bad("offset position is out of range")
        return offset["position"]
    if offset["uri"] not in items:
        return _bad("offset uri is not in the context")
    return items.index(offset["uri"])


def start_playback(account_id, device_id=None, context_uri=None, uris=None, offset=None, position_ms=None):
    state = _playback(account_id)
    if device_id:
        device = _owned_device(device_id, account_id)
        if device is None:
            return SpotifyError(404, "Device not found", "DEVICE_NOT_FOUND")
    elif state and state["device_id"] and _owned_device(state["device_id"], account_id):
        device = _owned_device(state["device_id"], account_id)
    else:
        return _no_active_device()
    if device["is_restricted"]:
        return _restricted()
    if context_uri and uris is not None:
        return _bad("Send either context_uri or uris, not both")
    if uris is not None and not uris:
        return _bad("uris must not be empty")
    if position_ms is not None and position_ms < 0:
        return _bad("position_ms must not be negative")
    if offset is not None and not context_uri and uris is None:
        return _bad("offset requires context_uri or uris")
    context, item = "", ""
    if context_uri:
        parsed = _parse_uri(context_uri)
        if parsed is None or parsed[0] not in CONTEXT_KINDS:
            return _bad(f"Invalid context uri: {context_uri}")
        items = _context_items(parsed[0], parsed[1], account_id)
        if isinstance(items, SpotifyError):
            return items
        if not items:
            return _bad("The context has no playable items")
        index = _pick_offset(items, offset, parsed[0])
        if isinstance(index, SpotifyError):
            return index
        context, item = context_uri, items[index]
    elif uris is not None:
        for uri in uris:
            if _resolve_item_uri(uri) is None:
                return _bad(f"Invalid track uri: {uri}")
        index = _pick_offset(uris, offset, "uris")
        if isinstance(index, SpotifyError):
            return index
        item = uris[index]
    else:
        if not state or not state["item_uri"]:
            return _bad("Nothing to resume: send context_uri or uris")
        context, item = state["context_uri"], state["item_uri"]
    resolved = _resolve_item_uri(item)
    if position_ms is not None and position_ms > resolved[1]["duration_ms"]:
        return _bad("position_ms is beyond the end of the item")
    keeps_position = context_uri is None and uris is None
    progress = position_ms if position_ms is not None else (state["progress_ms"] if keeps_position and state else 0)
    _store.table("playback").upsert({
        "account_id": account_id, "device_id": device["id"], "context_uri": context, "item_uri": item,
        "progress_ms": progress, "is_playing": True,
        "shuffle_state": state["shuffle_state"] if state else False,
        "repeat_state": state["repeat_state"] if state else "off", "updated_at": _iso(_now())})
    return None


def _context_view(context_uri):
    parsed = _parse_uri(context_uri)
    if not context_uri or parsed is None:
        return None
    return {"type": parsed[0], "href": f"{API_BASE}/{parsed[0]}s/{parsed[1]}",
            "external_urls": {"spotify": f"{WEB_BASE}/{parsed[0]}/{parsed[1]}"}, "uri": context_uri}


def currently_playing(account_id, additional_types=None):
    if additional_types is not None:
        for kind in (k.strip() for k in additional_types.split(",") if k.strip()):
            if kind not in ITEM_KINDS:
                return _bad(f"Invalid additional_types value: {kind}")
    state = _playback(account_id)
    if state is None or not state["item_uri"]:
        return None
    resolved = _resolve_item_uri(state["item_uri"])
    if resolved is None:
        return None
    moment = datetime.strptime(state["updated_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return {"timestamp": int(moment.timestamp() * 1000), "context": _context_view(state["context_uri"]),
            "progress_ms": state["progress_ms"], "item": _item_view(resolved[0], resolved[1], _catalog()),
            "currently_playing_type": resolved[0], "is_playing": state["is_playing"]}


def transfer_playback(account_id, device_ids, play=None):
    if len(device_ids) != 1:
        return _bad("Exactly one device id is supported")
    device = _owned_device(device_ids[0], account_id)
    if device is None:
        return SpotifyError(404, "Device not found", "DEVICE_NOT_FOUND")
    if device["is_restricted"]:
        return _restricted()
    state = _playback(account_id)
    if play and (not state or not state["item_uri"]):
        return _bad("Nothing to play: start playback with context_uri or uris first")
    row = dict(state) if state else {"account_id": account_id, "context_uri": "", "item_uri": "",
                                     "progress_ms": 0, "is_playing": False, "shuffle_state": False,
                                     "repeat_state": "off"}
    row["device_id"] = device["id"]
    row["is_playing"] = True if play else row["is_playing"]
    row["updated_at"] = _iso(_now())
    _store.table("playback").upsert(row)
    return None


_store.eager_load()
