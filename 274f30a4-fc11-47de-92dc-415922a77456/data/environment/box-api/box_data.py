"""Data access module for the Box API mock service.

Serves exactly the six content operations the connector needs -- list a
folder's items, get a file's details, search by name, create a folder, upload a
small file, and create a shared link for a file -- in the shape of the Box
Platform API (api.box.com/2.0, with uploads on upload.box.com/api/2.0). Every
read and write is scoped to the items the presented token's connected account
owns.

Folders and files are rows keyed by Box's numeric ids, and the root folder is
"0" ("All Files"). A file row carries its parent, size, SHA-1, current version,
timestamps, the users who created and last modified it, and its shared link
when it has one. Mock simplifications (also stated in api_test_results.md): no
trash, no version history, no collaborations, comments, tags or metadata, no
file download, and an upload is capped at 1 MiB.
"""

import hashlib
import secrets
import string
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent

sys.path.insert(0, str(DATA_DIR.parent))
import _mock_clock  # noqa: E402
from _mutable_store import get_store, read_seed_with_ctx  # noqa: E402
from _connector_auth import ConnectorAuth  # noqa: E402

_API = "box-api"
_store = get_store(_API)

ROOT_ID = "0"
HELP_URL = "http://developers.box.com/docs/#errors"
UPLOAD_LIMIT = 1024 * 1024
NAME_LIMIT = 255
ORDER = [{"by": "type", "direction": "ASC"}, {"by": "name", "direction": "ASC"}]
BASE_FIELDS = ("type", "id", "etag")
FILE_FIELDS = ("type", "id", "file_version", "sequence_id", "etag", "sha1", "name", "description", "size",
               "path_collection", "created_at", "modified_at", "trashed_at", "purged_at", "content_created_at",
               "content_modified_at", "created_by", "modified_by", "owned_by", "shared_link", "parent",
               "item_status", "extension")
FOLDER_FIELDS = ("type", "id", "sequence_id", "etag", "name", "description", "size", "path_collection",
                 "created_at", "modified_at", "trashed_at", "purged_at", "content_created_at", "content_modified_at",
                 "created_by", "modified_by", "owned_by", "shared_link", "folder_upload_email", "parent",
                 "item_status", "item_collection")
STANDARD_FILE = tuple(f for f in FILE_FIELDS if f != "extension")
STANDARD_FOLDER = FOLDER_FIELDS
SORTS = ("id", "name", "date", "size")
ACCESS_LEVELS = ("open", "company", "collaborators")
SEARCH_TYPES = ("file", "folder", "web_link")
CONTENT_TYPES = ("name", "description")


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _coerce_item(r):
    out = _strip_ctx(r)
    out["description"] = out.get("description") or ""
    out["parent_id"] = out.get("parent_id") or ""
    if "size" in out:
        out["size"] = int(out.get("size") or 0)
    return out


_store.register("users", primary_key="id",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("users.json", "users")])
_store.register("folders", primary_key="id",
                initial_loader=lambda: [_coerce_item(r) for r in _load("folders.json", "folders")],
                row_coercer=_coerce_item)
_store.register("files", primary_key="id",
                initial_loader=lambda: [_coerce_item(r) for r in _load("files.json", "files")],
                row_coercer=_coerce_item)

auth = ConnectorAuth(_API, store=_store, data_dir=DATA_DIR)


class BoxError:
    """A Box client error body and the HTTP status it is served with."""

    def __init__(self, status, code, message, context_info=None):
        self.status = status
        body = {"type": "error", "status": status, "code": code}
        if context_info is not None:
            body["context_info"] = context_info
        body.update({"help_url": HELP_URL, "message": message,
                     "request_id": hashlib.sha1(f"{code}:{message}".encode()).hexdigest()[:20]})
        self.body = body


def invalid(name, message):
    return BoxError(400, "bad_request", "Bad Request",
                    {"errors": [{"reason": "invalid_parameter", "name": name, "message": message}]})


def not_found(name="item", value=""):
    detail = f"Invalid value '{value}'. '{name}' with value '{value}' not found" if value else "Not Found"
    return BoxError(404, "not_found", "Not Found",
                    {"errors": [{"reason": "invalid_parameter", "name": name, "message": detail}]})


# --- time ---------------------------------------------------------------------------------------

def _central_offset(moment):
    """The studio's Chicago offset at a UTC instant: CDT between the US DST transitions, CST outside."""
    year = moment.year
    march = datetime(year, 3, 8, 8, tzinfo=timezone.utc)
    start = march + timedelta(days=(6 - march.weekday()) % 7)
    november = datetime(year, 11, 1, 7, tzinfo=timezone.utc)
    end = november + timedelta(days=(6 - november.weekday()) % 7)
    return timedelta(hours=-5) if start <= moment < end else timedelta(hours=-6)


def box_time(moment=None):
    moment = (moment or _mock_clock.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    return moment.astimezone(timezone(_central_offset(moment))).isoformat()


def parse_time(text):
    try:
        moment = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else None


# --- lookup -------------------------------------------------------------------------------------

def _folder(folder_id, account_id):
    row = _store.table("folders").get(folder_id)
    if row is None or row.get("owner_account_id") != account_id:
        return None
    return row


def _file(file_id, account_id):
    row = _store.table("files").get(file_id)
    if row is None or row.get("owner_account_id") != account_id:
        return None
    return row


def _children(folder_id, account_id):
    folders = _store.table("folders").find(
        lambda r: r["parent_id"] == folder_id and r.get("owner_account_id") == account_id)
    files = _store.table("files").find(
        lambda r: r["parent_id"] == folder_id and r.get("owner_account_id") == account_id)
    return folders, files


def _ancestors(row):
    """Folder rows from the root down to ``row``'s parent."""
    chain = []
    seen = set()
    parent_id = row["parent_id"]
    while parent_id and parent_id not in seen:
        seen.add(parent_id)
        parent = _store.table("folders").get(parent_id)
        if parent is None:
            break
        chain.append(parent)
        parent_id = parent["parent_id"]
    return list(reversed(chain))


def _subtree_size(folder_id, account_id):
    total = 0
    pending = [folder_id]
    seen = set()
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        folders, files = _children(current, account_id)
        total += sum(f["size"] for f in files)
        pending.extend(f["id"] for f in folders)
    return total


# --- rendering ----------------------------------------------------------------------------------

def _user(user_id):
    user = _store.table("users").get(user_id) or {}
    return {"type": "user", "id": user_id, "name": user.get("name", ""), "login": user.get("login", "")}


def _folder_mini(row):
    if row["id"] == ROOT_ID:
        return {"type": "folder", "id": ROOT_ID, "sequence_id": None, "etag": None, "name": "All Files"}
    return {"type": "folder", "id": row["id"], "sequence_id": str(row["sequence_id"]),
            "etag": str(row["sequence_id"]), "name": row["name"]}


def _version(row):
    return {"type": "file_version", "id": row["file_version_id"], "sha1": row["sha1"]}


def _file_mini(row):
    return {"type": "file", "id": row["id"], "file_version": _version(row), "sequence_id": str(row["sequence_id"]),
            "etag": str(row["sequence_id"]), "sha1": row["sha1"], "name": row["name"]}


def _path_collection(row):
    entries = [_folder_mini(f) for f in _ancestors(row)]
    return {"total_count": len(entries), "entries": entries}


def _parent(row):
    parent = _store.table("folders").get(row["parent_id"]) if row["parent_id"] else None
    return _folder_mini(parent) if parent is not None else None


def _shared_link(link):
    if not link:
        return None
    permissions = dict(link.get("permissions") or {})
    if permissions.get("can_edit"):
        effective = "can_edit"
    elif permissions.get("can_download"):
        effective = "can_download"
    else:
        effective = "can_preview"
    return {"url": link["url"], "download_url": link.get("download_url"), "vanity_url": link.get("vanity_url"),
            "vanity_name": link.get("vanity_name"), "access": link["access"], "effective_access": link["access"],
            "effective_permission": effective, "unshared_at": link.get("unshared_at"),
            "is_password_enabled": bool(link.get("password")), "permissions": permissions,
            "download_count": int(link.get("download_count") or 0),
            "preview_count": int(link.get("preview_count") or 0)}


def _file_full(row):
    return {"type": "file", "id": row["id"], "file_version": _version(row), "sequence_id": str(row["sequence_id"]),
            "etag": str(row["sequence_id"]), "sha1": row["sha1"], "name": row["name"],
            "description": row["description"], "size": row["size"], "path_collection": _path_collection(row),
            "created_at": row["created_at"], "modified_at": row["modified_at"], "trashed_at": None,
            "purged_at": None, "content_created_at": row["content_created_at"],
            "content_modified_at": row["content_modified_at"], "created_by": _user(row["created_by"]),
            "modified_by": _user(row["modified_by"]), "owned_by": _user(row["owned_by"]),
            "shared_link": _shared_link(row.get("shared_link")), "parent": _parent(row), "item_status": "active",
            "extension": row["name"].rsplit(".", 1)[1].lower() if "." in row["name"] else ""}


def _folder_full(row, account_id):
    view = {"type": "folder", "id": row["id"], "sequence_id": None if row["id"] == ROOT_ID else str(row["sequence_id"]),
            "etag": None if row["id"] == ROOT_ID else str(row["sequence_id"]),
            "name": "All Files" if row["id"] == ROOT_ID else row["name"], "description": row["description"],
            "size": _subtree_size(row["id"], account_id), "path_collection": _path_collection(row),
            "created_at": row["created_at"], "modified_at": row["modified_at"], "trashed_at": None,
            "purged_at": None, "content_created_at": row["created_at"], "content_modified_at": row["modified_at"],
            "created_by": _user(row["created_by"]), "modified_by": _user(row["modified_by"]),
            "owned_by": _user(row["owned_by"]), "shared_link": None, "folder_upload_email": None,
            "parent": _parent(row), "item_status": "active"}
    folders, files = _children(row["id"], account_id)
    entries = [_folder_mini(f) for f in sorted(folders, key=lambda f: f["name"].lower())]
    entries += [_file_mini(f) for f in sorted(files, key=lambda f: f["name"].lower())]
    view["item_collection"] = {"total_count": len(entries), "entries": entries[:100], "offset": 0, "limit": 100,
                               "order": ORDER}
    return view


def _fields(text):
    """The requested ``fields`` as a list, a BoxError for an unknown name, or None when none were asked."""
    if text is None:
        return None
    wanted = [f.strip() for f in text.split(",") if f.strip()]
    if not wanted:
        return invalid("fields", "Invalid value ''. 'fields' must name at least one field")
    unknown = [f for f in wanted if f not in FILE_FIELDS and f not in FOLDER_FIELDS]
    if unknown:
        return invalid("fields", f"Invalid value '{unknown[0]}'. It is not a field of a file or folder")
    return wanted


def _project(full, wanted, kind):
    allowed = FILE_FIELDS if kind == "file" else FOLDER_FIELDS
    out = {key: full[key] for key in BASE_FIELDS}
    for name in wanted:
        if name in allowed and name in full:
            out[name] = full[name]
    return out


def _render_file(row, wanted, standard=True):
    full = _file_full(row)
    if wanted is not None:
        return _project(full, wanted, "file")
    return {k: full[k] for k in STANDARD_FILE} if standard else _file_mini(row)


def _render_folder(row, account_id, wanted, standard=True):
    if wanted is not None:
        return _project(_folder_full(row, account_id), wanted, "folder")
    return _folder_full(row, account_id) if standard else _folder_mini(row)


def _paging(limit, offset, limit_max):
    if limit < 1 or limit > limit_max:
        return invalid("limit", f"Invalid value '{limit}'. 'limit' must be between 1 and {limit_max}")
    if offset < 0:
        return invalid("offset", f"Invalid value '{offset}'. 'offset' must be zero or more")
    return None


# --- operations ---------------------------------------------------------------------------------

def list_folder_items(folder_id, account_id, fields=None, limit=100, offset=0, sort=None, direction=None):
    folder = _folder(folder_id, account_id)
    if folder is None:
        return not_found("folder", folder_id)
    wanted = _fields(fields)
    if isinstance(wanted, BoxError):
        return wanted
    problem = _paging(limit, offset, 1000)
    if problem:
        return problem
    if sort is not None and sort not in SORTS:
        return invalid("sort", f"Invalid value '{sort}'. 'sort' must be one of id, name, date, size")
    if direction is not None and direction not in ("ASC", "DESC"):
        return invalid("direction", f"Invalid value '{direction}'. 'direction' must be ASC or DESC")
    folders, files = _children(folder_id, account_id)
    key = {"id": lambda r: int(r["id"]), "date": lambda r: parse_time(r["modified_at"]),
           "size": lambda r: r.get("size", 0)}.get(sort or "name", lambda r: r["name"].lower())
    reverse = direction == "DESC"
    if sort == "size":
        sized = {f["id"]: _subtree_size(f["id"], account_id) for f in folders}
        folders.sort(key=lambda r: sized[r["id"]], reverse=reverse)
    else:
        folders.sort(key=key, reverse=reverse)
    files.sort(key=key, reverse=reverse)
    entries = [_render_folder(f, account_id, wanted, standard=False) for f in folders]
    entries += [_render_file(f, wanted, standard=False) for f in files]
    order = [{"by": "type", "direction": "ASC"}, {"by": sort or "name", "direction": direction or "ASC"}]
    return {"total_count": len(entries), "entries": entries[offset:offset + limit], "offset": offset,
            "limit": limit, "order": order}


def get_file(file_id, account_id, fields=None):
    row = _file(file_id, account_id)
    if row is None:
        return not_found("file", file_id)
    wanted = _fields(fields)
    if isinstance(wanted, BoxError):
        return wanted
    return _render_file(row, wanted)


def _split(text, name):
    values = [v.strip() for v in (text or "").split(",") if v.strip()]
    if text is not None and not values:
        return invalid(name, f"Invalid value ''. '{name}' must list at least one value")
    return values


def search(account_id, query, type=None, file_extensions=None, ancestor_folder_ids=None, content_types=None,
           limit=30, offset=0, fields=None):
    terms = [t for t in (query or "").lower().replace('"', " ").split() if t]
    if not terms:
        return invalid("query", "Invalid value ''. 'query' is required and must not be empty")
    if type is not None and type not in SEARCH_TYPES:
        return invalid("type", f"Invalid value '{type}'. 'type' must be one of file, folder, web_link")
    extensions = _split(file_extensions, "file_extensions")
    ancestors = _split(ancestor_folder_ids, "ancestor_folder_ids")
    searched = _split(content_types, "content_types")
    for bad in (extensions, ancestors, searched):
        if isinstance(bad, BoxError):
            return bad
    unknown = [c for c in searched if c not in CONTENT_TYPES]
    if unknown:
        return invalid("content_types", f"Invalid value '{unknown[0]}'. This mock searches name and description")
    wanted = _fields(fields)
    if isinstance(wanted, BoxError):
        return wanted
    problem = _paging(limit, offset, 200)
    if problem:
        return problem
    searched = searched or list(CONTENT_TYPES)
    for folder_id in ancestors:
        if _folder(folder_id, account_id) is None:
            return not_found("ancestor_folder_ids", folder_id)

    def matches(row):
        text = " ".join(row["name"].lower() if c == "name" else row["description"].lower() for c in searched)
        if not all(t in text for t in terms):
            return False
        if ancestors and not ({a["id"] for a in _ancestors(row)} & set(ancestors)):
            return False
        return True

    hits = []
    if type in (None, "folder") and not extensions:
        hits += [("folder", r) for r in _store.table("folders").find(
            lambda r: r.get("owner_account_id") == account_id and r["id"] != ROOT_ID and matches(r))]
    if type in (None, "file"):
        hits += [("file", r) for r in _store.table("files").find(
            lambda r: r.get("owner_account_id") == account_id and matches(r) and (
                not extensions or r["name"].rsplit(".", 1)[-1].lower() in {e.lower().lstrip(".") for e in extensions}))]
    hits.sort(key=lambda hit: parse_time(hit[1]["modified_at"]), reverse=True)
    window = hits[offset:offset + limit]
    entries = [_render_file(r, wanted) if kind == "file" else _render_folder(r, account_id, wanted)
               for kind, r in window]
    return {"total_count": len(hits), "limit": limit, "offset": offset, "type": "search_results_items",
            "entries": entries}


def _check_name(name):
    if not name or not name.strip():
        return invalid("name", "Invalid value ''. 'name' must not be empty")
    if len(name) > NAME_LIMIT:
        return invalid("name", f"Invalid value '{name[:40]}...'. 'name' can be at most {NAME_LIMIT} characters")
    if name in (".", "..") or "/" in name or "\\" in name or name != name.strip():
        return invalid("name", f"Invalid value '{name}'. Names cannot contain '/' or '\\', be '.' or '..', "
                               "or start or end with a space")
    return None


def _new_id(prefix, length):
    return prefix + "".join(secrets.choice(string.digits) for _ in range(length))


def _user_id(account_id):
    user = _store.table("users").find_one(lambda u: u.get("account_id") == account_id and u.get("is_owner"))
    return user["id"] if user else ""


def create_folder(account_id, name, parent_id, description=None, fields=None):
    problem = _check_name(name)
    if problem:
        return problem
    parent = _folder(parent_id, account_id)
    if parent is None:
        return not_found("parent", parent_id)
    wanted = _fields(fields)
    if isinstance(wanted, BoxError):
        return wanted
    folders, files = _children(parent_id, account_id)
    clash = [f for f in folders if f["name"].lower() == name.lower()]
    clash += [f for f in files if f["name"].lower() == name.lower()]
    if clash:
        minis = [_folder_mini(c) if c in folders else _file_mini(c) for c in clash]
        return BoxError(409, "item_name_in_use", "Item with the same name already exists", {"conflicts": minis})
    now = box_time()
    user_id = _user_id(account_id)
    row = {"id": _new_id("3", 11), "name": name, "parent_id": parent_id, "description": description or "",
           "owner_account_id": account_id, "sequence_id": 0, "created_at": now, "modified_at": now,
           "created_by": user_id, "modified_by": user_id, "owned_by": user_id}
    _store.table("folders").upsert(row)
    return _render_folder(_store.table("folders").get(row["id"]), account_id, wanted)


def upload_file(account_id, name, parent_id, content, content_created_at=None, content_modified_at=None,
                fields=None):
    problem = _check_name(name)
    if problem:
        return problem
    parent = _folder(parent_id, account_id)
    if parent is None:
        return not_found("parent", parent_id)
    wanted = _fields(fields)
    if isinstance(wanted, BoxError):
        return wanted
    if len(content) > UPLOAD_LIMIT:
        return BoxError(403, "file_size_limit_exceeded",
                        f"File is larger than this mock's simple-upload limit of {UPLOAD_LIMIT} bytes")
    for label, value in (("content_created_at", content_created_at), ("content_modified_at", content_modified_at)):
        if value is not None and parse_time(value) is None:
            return invalid(label, f"Invalid value '{value}'. '{label}' must be an RFC 3339 date-time with an offset")
    folders, files = _children(parent_id, account_id)
    clash = next((f for f in files if f["name"].lower() == name.lower()), None)
    if clash is not None:
        return BoxError(409, "item_name_in_use", "Item with the same name already exists",
                        {"conflicts": _file_mini(clash)})
    if any(f["name"].lower() == name.lower() for f in folders):
        folder = next(f for f in folders if f["name"].lower() == name.lower())
        return BoxError(409, "item_name_in_use", "Item with the same name already exists",
                        {"conflicts": _folder_mini(folder)})
    now = box_time()
    user_id = _user_id(account_id)
    row = {"id": _new_id("2", 12), "name": name, "parent_id": parent_id, "description": "",
           "owner_account_id": account_id, "size": len(content), "sha1": hashlib.sha1(content).hexdigest(),
           "file_version_id": _new_id("1", 12), "sequence_id": 0, "created_at": now, "modified_at": now,
           "content_created_at": box_time(parse_time(content_created_at)) if content_created_at else now,
           "content_modified_at": box_time(parse_time(content_modified_at)) if content_modified_at else now,
           "created_by": user_id, "modified_by": user_id, "owned_by": user_id, "shared_link": None}
    _store.table("files").upsert(row)
    return {"total_count": 1, "entries": [_render_file(_store.table("files").get(row["id"]), wanted)]}


def _link_token():
    return "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(32))


def add_shared_link(file_id, account_id, spec, fields=None):
    """Create or change ``file_id``'s shared link from the ``shared_link`` object of the request."""
    row = _file(file_id, account_id)
    if row is None:
        return not_found("file", file_id)
    wanted = _fields(fields)
    if isinstance(wanted, BoxError):
        return wanted
    access = spec.get("access") or "open"
    if access not in ACCESS_LEVELS:
        return invalid("shared_link.access", f"Invalid value '{access}'. 'access' must be open, company or collaborators")
    password = spec.get("password")
    if password is not None:
        if access != "open":
            return invalid("shared_link.password", "A password can be set only on a shared link with open access")
        if len(password) < 8 or password.isalpha():
            return invalid("shared_link.password",
                           "The password must be at least 8 characters and contain a number or a special character")
    vanity = spec.get("vanity_name")
    if vanity is not None:
        if len(vanity) < 12 or not all(c.isalnum() or c == "-" for c in vanity):
            return invalid("shared_link.vanity_name",
                           "'vanity_name' must be at least 12 letters, numbers or hyphens")
        taken = _store.table("files").find_one(
            lambda r: r["id"] != file_id and (r.get("shared_link") or {}).get("vanity_name") == vanity)
        if taken is not None:
            return BoxError(400, "bad_request", "Bad Request", {"errors": [{
                "reason": "invalid_parameter", "name": "shared_link.vanity_name",
                "message": f"Invalid value '{vanity}'. That vanity name is already in use"}]})
    unshared_at = spec.get("unshared_at")
    if unshared_at is not None and parse_time(unshared_at) is None:
        return invalid("shared_link.unshared_at",
                       f"Invalid value '{unshared_at}'. 'unshared_at' must be an RFC 3339 date-time with an offset")
    permissions = dict(spec.get("permissions") or {})
    if permissions.get("can_preview") is False:
        return invalid("shared_link.permissions.can_preview", "'can_preview' must be true when it is set")
    can_edit = bool(permissions.get("can_edit", False))
    can_download = bool(permissions.get("can_download", True)) or can_edit
    if can_edit and access == "collaborators":
        return invalid("shared_link.permissions.can_edit",
                       "'can_edit' needs a shared link with open or company access")
    current = row.get("shared_link") or {}
    token = current.get("url", "").rsplit("/", 1)[-1] or _link_token()
    extension = row["name"].rsplit(".", 1)[1].lower() if "." in row["name"] else ""
    link = {"url": f"https://app.box.com/s/{token}",
            "download_url": f"https://app.box.com/shared/static/{token}" + (f".{extension}" if extension else ""),
            "vanity_name": vanity, "vanity_url": f"https://app.box.com/v/{vanity}" if vanity else None,
            "access": access, "password": password, "unshared_at": unshared_at,
            "permissions": {"can_preview": True, "can_download": can_download, "can_edit": can_edit},
            "download_count": int(current.get("download_count") or 0),
            "preview_count": int(current.get("preview_count") or 0)}
    _store.table("files").patch(file_id, {"shared_link": link, "sequence_id": int(row["sequence_id"]) + 1})
    return _render_file(_store.table("files").get(file_id), wanted)


_store.eager_load()
