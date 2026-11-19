"""Data access module for the Google Drive API mock service.

Serves exactly the seven Google Drive connector operations the client ranks --
files, upload, permissions, comments, revisions, search, list -- for the files
one connected account owns. Every read and write is scoped to the files the
presented token's connected account owns; a file of another account answers
``404 notFound`` exactly like a file that does not exist.

Drive also lists, as Google files of their owner, every document, spreadsheet,
presentation and form the google-docs-api, google-sheets-api, google-slides-api
and google-forms-api mocks hold: a file is the connected account's when its
``owner_account_id`` is the account id the token names. Drive and those mocks
are one system, as in Google: when an editor mock is deployed in the run, every
Drive call first reads its live files over the peer routes (_linked_peer.py), so
a file created, renamed, edited or deleted there shows here at once, and a
rename, delete or Google-file create made here is made there too. A Google Doc
exports as text/plain from the Docs mock's live paragraphs. An editor mock that
is deployed but does not answer is a 503 and a row in ``peer_failures``, never
its seed served as if it were current. An editor mock that is not deployed
cannot change, so its seed (beside this service in the harness layout, or in
``linked/`` inside this service's folder, where a delivered bundle's packagers
copy it) is the truth.

An account id the token names that accounts.json does not have is served as an
empty Drive of its own (no files beyond those Google files), never an error.

Uploads take raw bytes (uploadType=media), a multipart body of metadata and
content (uploadType=multipart), or a JSON body carrying text in ``content``;
content comes back byte for byte from files.get with alt=media.

Mock simplifications (also stated in api_test_results.md): only a Google Doc
exports and only as text/plain, and a file has exactly one parent.
"""

import base64
import functools
import hashlib
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent

sys.path.insert(0, str(DATA_DIR.parent))
import _linked_peer  # noqa: E402
import _mock_clock  # noqa: E402
from _mutable_store import get_store, read_seed_with_ctx, strict_bool  # noqa: E402
from _connector_auth import ConnectorAuth  # noqa: E402

_API = "google-drive-api"
_store = get_store(_API)

FOLDER_MIME = "application/vnd.google-apps.folder"
NATIVE_PREFIX = "application/vnd.google-apps."
DOC_MIME = "application/vnd.google-apps.document"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"
SLIDES_MIME = "application/vnd.google-apps.presentation"
FORM_MIME = "application/vnd.google-apps.form"
# The Google editor mocks' seeds Drive lists, and the Docs paragraphs export reads.
LINKED_SEEDS = (("google-docs-api", "documents", DOC_MIME), ("google-sheets-api", "spreadsheets", SHEET_MIME),
                ("google-slides-api", "presentations", SLIDES_MIME), ("google-forms-api", "forms", FORM_MIME))
# Every seed _linked_seed reads; both bundle packagers copy exactly these into linked/.
LINKED_TABLES = (("google-docs-api", "documents"), ("google-sheets-api", "spreadsheets"),
                 ("google-slides-api", "presentations"), ("google-forms-api", "forms"),
                 ("google-docs-api", "paragraphs"))
LINKED_DIR = DATA_DIR / "linked"
FILE_FIELDS = ("kind", "id", "name", "mimeType", "parents", "owners", "createdTime", "modifiedTime",
               "size", "starred", "trashed", "explicitlyTrashed", "shared", "ownedByMe", "webViewLink",
               "description", "headRevisionId")
PERMISSION_FIELDS = ("kind", "id", "type", "role", "emailAddress", "displayName", "domain",
                     "allowFileDiscovery", "deleted")
COMMENT_FIELDS = ("kind", "id", "content", "htmlContent", "author", "createdTime", "modifiedTime",
                  "resolved", "deleted", "quotedFileContent", "replies")
REPLY_FIELDS = ("kind", "id", "content", "htmlContent", "author", "createdTime", "modifiedTime",
                "deleted", "action")
REVISION_FIELDS = ("kind", "id", "mimeType", "modifiedTime", "keepForever", "published",
                   "publishedLink", "publishedOutsideDomain", "lastModifyingUser", "originalFilename",
                   "size")
ORDER_KEYS = ("name", "modifiedTime", "createdTime")
FILE_SORT = {"name": "name", "modifiedTime": "modified_time", "createdTime": "created_time"}
PERMISSION_TYPES = ("user", "group", "domain", "anyone")
GRANTABLE_ROLES = ("reader", "commenter", "writer")
STATUS_NAMES = {400: "INVALID_ARGUMENT", 401: "UNAUTHENTICATED", 403: "PERMISSION_DENIED",
                404: "NOT_FOUND", 409: "ABORTED", 503: "UNAVAILABLE"}
# The editor mock that holds each Google file type.
LINKED_API_BY_MIME = {mime: api for api, _table, mime in LINKED_SEEDS}


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _coerce_file_row(r):
    out = _strip_ctx(r)
    out["starred"] = strict_bool(out, "starred")
    out["trashed"] = strict_bool(out, "trashed")
    return out


def _coerce_permission_row(r):
    out = _strip_ctx(r)
    out["allow_file_discovery"] = strict_bool(out, "allow_file_discovery")
    out["_pk"] = f"{out['file_id']}:{out['id']}"
    return out


def _coerce_comment_row(r):
    out = _strip_ctx(r)
    out["resolved"] = strict_bool(out, "resolved")
    return out


def _coerce_revision_row(r):
    out = _strip_ctx(r)
    out["keep_forever"] = strict_bool(out, "keep_forever")
    out["published"] = strict_bool(out, "published")
    return out


def _linked_seed(api, table):
    """A Google editor mock's seed rows, read the way that mock reads them: beside this service, else
    from the copy a delivered bundle carries in ``linked/``; none when neither has them."""
    for folder in (DATA_DIR.parent / api, LINKED_DIR / api):
        path = folder / f"{table}.json"
        if path.exists() or path.with_suffix(".csv").exists():
            return [_strip_ctx(r) for r in read_seed_with_ctx(path, api, table)]
    return []


# Drive files that are an editor mock's file (id -> that mock), and the content
# fingerprint each was last seen with, so an edit made there moves modifiedTime here.
_linked_ids = {}
_linked_marks = {}


def _load_files():
    """files.json, plus a Drive file for every Doc, Sheet, Slides deck and Form files.json does not name."""
    rows = [_coerce_file_row(r) for r in _load("files.json", "files")]
    seen = {r["id"] for r in rows}
    stamp = max((r["modified_time"] for r in rows), default=_drive_time(_now()))
    for api, table, mime in LINKED_SEEDS:
        for item in _linked_seed(api, table):
            owner = item.get("owner_account_id") or ""
            if owner:
                _linked_ids[item["id"]] = api
            if item["id"] in seen or not owner:
                continue
            seen.add(item["id"])
            rows.append({"id": item["id"], "name": item.get("document_title") or item.get("title") or "Untitled",
                         "mime_type": mime, "parent_id": _root_id(owner), "owner_account_id": owner,
                         "created_time": item.get("created_time") or stamp,
                         "modified_time": item.get("updated_time") or stamp, "size": "", "starred": False,
                         "trashed": False, "trashed_via": "", "description": "", "head_revision_id": ""})
    return rows


_store.register("accounts", primary_key="id",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("accounts.json", "accounts")])
_store.register("directory", primary_key="email",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("directory.json", "directory")])
_store.register("files", primary_key="id", initial_loader=_load_files, row_coercer=_coerce_file_row)
_store.register("permissions", primary_key="_pk",
                initial_loader=lambda: [_coerce_permission_row(r)
                                        for r in _load("permissions.json", "permissions")],
                row_coercer=_coerce_permission_row)
_store.register("comments", primary_key="id",
                initial_loader=lambda: [_coerce_comment_row(r) for r in _load("comments.json", "comments")],
                row_coercer=_coerce_comment_row)
_store.register("replies", primary_key="id",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("replies.json", "replies")])
_store.register("revisions", primary_key="id",
                initial_loader=lambda: [_coerce_revision_row(r) for r in _load("revisions.json", "revisions")],
                row_coercer=_coerce_revision_row)
# Every time a deployed editor mock did not answer: the run's evidence of an environment fault.
_store.register("peer_failures", primary_key="id", initial_loader=lambda: [])

auth = ConnectorAuth(_API, store=_store, data_dir=DATA_DIR)


class DriveError:
    """A Google API error envelope and the HTTP status it is served with."""

    def __init__(self, status, message, reason, location=None, location_type="parameter"):
        self.status = status
        entry = {"message": message, "domain": "global", "reason": reason}
        if location:
            entry["location"] = location
            entry["locationType"] = location_type
        self.body = {"error": {"code": status, "message": message, "errors": [entry],
                               "status": STATUS_NAMES.get(status, "UNKNOWN")}}


def _missing(file_id):
    return DriveError(404, f"File not found: {file_id}.", "notFound", "fileId")


def _invalid(message, reason="invalid", location=None):
    return DriveError(400, message, reason, location)


def _now():
    return _mock_clock.now(timezone.utc)


def _drive_time(moment):
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _new_id(prefix, length):
    return prefix + base64.urlsafe_b64encode(uuid.uuid4().bytes + uuid.uuid4().bytes).decode()[:length]


def _derived_id(key):
    """Stable 19-digit permission id for a grantee (the same one the seed uses)."""
    return str(int(hashlib.sha1(key.encode()).hexdigest(), 16) % 10**19).zfill(19)


def _account(account_id):
    """The account, or an empty Drive of its own for an id accounts.json does not have."""
    return _store.table("accounts").get(account_id) or {
        "id": account_id, "email": "", "display_name": account_id, "domain": "",
        "root_folder_id": "0A" + base64.urlsafe_b64encode(hashlib.sha256(account_id.encode()).digest()).decode()[:16]}


def _owned(file_id, account_id):
    row = _store.table("files").get(file_id)
    if row is None or row.get("owner_account_id") != account_id:
        return None
    return row


def _root_id(account_id):
    return _account(account_id)["root_folder_id"]


def _resolve_folder(folder_id, account_id):
    return _root_id(account_id) if folder_id == "root" else folder_id


# --- the Google editor mocks, live ------------------------------------------------------------

def _linked_peer_of(f):
    """The live peer of the editor mock holding Drive file ``f``, or None (not a Google
    editor file, or its mock is not deployed in this run)."""
    api = LINKED_API_BY_MIME.get(f["mime_type"])
    return _linked_peer.peer_for(api) if api else None


def _sync_linked():
    """Bring Drive's view of every deployed editor mock's files up to its live state: files
    created there appear, files deleted there go, a new title is the name, and changed
    content moves modifiedTime."""
    files = _store.table("files")
    for api, _table, mime in LINKED_SEEDS:
        peer = _linked_peer.peer_for(api)
        if peer is None:
            continue
        live = {e["id"]: e for e in peer.files()}
        gone = {fid for fid, owner_api in _linked_ids.items() if owner_api == api and fid not in live}
        if gone:
            _drop_files(gone)
        now = _drive_time(_now())
        for entry in live.values():
            fid, owner = entry["id"], entry["owner_account_id"]
            if not owner:
                continue
            _linked_ids[fid] = api
            last = _linked_marks.get(fid, entry.get("baseline") or "")
            _linked_marks[fid] = entry["fingerprint"]
            row = files.get(fid)
            if row is None:
                files.upsert({"id": fid, "name": entry["title"], "mime_type": mime, "parent_id": _root_id(owner),
                              "owner_account_id": owner, "created_time": now, "modified_time": now, "size": "",
                              "starred": False, "trashed": False, "trashed_via": "", "description": "",
                              "head_revision_id": ""})
                _add_owner_permission(fid, owner)
                continue
            patch = {}
            if row["name"] != entry["title"]:
                patch["name"] = entry["title"]
            if row["owner_account_id"] != owner:
                patch.update(owner_account_id=owner, parent_id=_root_id(owner))
            if entry["fingerprint"] != last:
                patch["modified_time"] = now
            if patch:
                files.patch(fid, patch)
            if "owner_account_id" in patch:
                _add_owner_permission(fid, owner)


def _unavailable(exc):
    """A deployed editor mock did not answer: record it and refuse, rather than answer from a seed
    that may no longer be true."""
    detail = str(exc)
    print(f"[google-drive-api] linked editor mock unavailable: {detail}", file=sys.stderr, flush=True)
    _store.table("peer_failures").upsert({"id": _new_id("pf", 16), "time": _drive_time(_now()),
                                          "detail": detail})
    return DriveError(503, "The service is currently unavailable.", "backendError")


def _live(fn):
    """Run a Drive operation on the editor mocks' live state."""
    @functools.wraps(fn)
    def run(*args, **kwargs):
        try:
            _sync_linked()
            return fn(*args, **kwargs)
        except _linked_peer.PeerUnavailable as exc:
            return _unavailable(exc)
    return run


# --- fields projection ----------------------------------------------------------------

def _parse_fields(spec):
    """Parse a Drive ``fields`` selector into {name: subtree-or-None}, or a DriveError."""
    text = spec.replace(" ", "")
    pos = 0

    def bad():
        return _invalid(f"Invalid field selection {spec}", "invalidParameter", "fields")

    def parse_list(depth):
        nonlocal pos
        tree = {}
        while True:
            match = re.compile(r"[A-Za-z_*][A-Za-z0-9_]*").match(text, pos)
            if not match:
                return None
            name = match.group(0)
            pos = match.end()
            sub = None
            if pos < len(text) and text[pos] == "(":
                pos += 1
                sub = parse_list(depth + 1)
                if sub is None or pos >= len(text) or text[pos] != ")":
                    return None
                pos += 1
            tree[name] = sub
            if pos < len(text) and text[pos] == ",":
                pos += 1
                continue
            return tree

    tree = parse_list(0)
    if tree is None or pos != len(text):
        return bad()
    return tree


def _select(value, tree):
    if tree is None or "*" in tree:
        return value
    if isinstance(value, list):
        return [_select(v, tree) for v in value]
    if isinstance(value, dict):
        return {k: _select(value[k], tree[k]) for k in tree if k in value}
    return value


def _shape(view, fields, allowed, item_key=None, item_allowed=None):
    """Apply ``fields`` to a response, rejecting unknown top-level names like Drive does."""
    if not fields:
        return view
    tree = _parse_fields(fields)
    if isinstance(tree, DriveError):
        return tree
    for name, sub in tree.items():
        if name != "*" and name not in allowed:
            return _invalid(f"Invalid field selection {name}", "invalidParameter", "fields")
        if name == item_key and sub is not None and item_allowed is not None:
            for inner in sub:
                if inner != "*" and inner not in item_allowed:
                    return _invalid(f"Invalid field selection {inner}", "invalidParameter", "fields")
    return _select(view, tree)


# --- paging ------------------------------------------------------------------------------

def _token(index):
    return base64.urlsafe_b64encode(f"gd:{index}".encode()).decode().rstrip("=")


def _token_index(token):
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode()
        prefix, _, index = raw.partition(":")
        if prefix != "gd" or int(index) < 0:
            raise ValueError(raw)
        return int(index)
    except (ValueError, UnicodeDecodeError):
        return None


def _page(items, page_size, page_token, default_size, max_size):
    """Window ``items``; returns (window, next_token) or a DriveError."""
    size = default_size if page_size is None else page_size
    if size < 1 or size > max_size:
        return _invalid(f"Invalid value '{size}'. Values must be within the range: [1, {max_size}]",
                        "invalid", "pageSize")
    start = 0
    if page_token:
        start = _token_index(page_token)
        if start is None:
            return _invalid("Invalid Value", "invalid", "pageToken")
    window = items[start:start + size]
    nxt = _token(start + size) if start + size < len(items) else None
    return window, nxt


# --- views ----------------------------------------------------------------------------------

def _owner_view(account):
    return {"kind": "drive#user", "displayName": account["display_name"],
            "emailAddress": account["email"], "me": True,
            "permissionId": _derived_id(account["email"])}


def _web_link(f):
    mime, fid = f["mime_type"], f["id"]
    if mime == FOLDER_MIME:
        return f"https://drive.google.com/drive/folders/{fid}"
    kinds = {DOC_MIME: "document", SHEET_MIME: "spreadsheets", SLIDES_MIME: "presentation", FORM_MIME: "forms"}
    if mime in kinds:
        return f"https://docs.google.com/{kinds[mime]}/d/{fid}/edit"
    return f"https://drive.google.com/file/d/{fid}/view"


def _file_view(f, account, shared_ids):
    view = {"kind": "drive#file", "id": f["id"], "name": f["name"], "mimeType": f["mime_type"],
            "parents": [f["parent_id"]] if f["parent_id"] else [],
            "owners": [_owner_view(account)], "createdTime": f["created_time"],
            "modifiedTime": f["modified_time"], "starred": f["starred"], "trashed": f["trashed"],
            "explicitlyTrashed": f["trashed"] and not f.get("trashed_via"),
            "shared": f["id"] in shared_ids, "ownedByMe": True, "webViewLink": _web_link(f)}
    if f.get("description"):
        view["description"] = f["description"]
    if f.get("size"):
        view["size"] = f["size"]
    if f.get("head_revision_id"):
        view["headRevisionId"] = f["head_revision_id"]
    return view


def _shared_ids():
    """File ids with at least one permission besides the owner's."""
    return {p["file_id"] for p in _store.table("permissions").find(lambda p: p["role"] != "owner")}


def _single_file_view(f, account_id):
    return _file_view(f, _account(account_id), _shared_ids())


def _author_view(name, email, me):
    return {"kind": "drive#user", "displayName": name, "emailAddress": email, "me": me}


def _permission_view(p):
    view = {"kind": "drive#permission", "id": p["id"], "type": p["type"], "role": p["role"],
            "deleted": False}
    if p.get("email_address"):
        view["emailAddress"] = p["email_address"]
    if p.get("display_name"):
        view["displayName"] = p["display_name"]
    if p.get("domain"):
        view["domain"] = p["domain"]
    if p["type"] in ("domain", "anyone"):
        view["allowFileDiscovery"] = p["allow_file_discovery"]
    return view


def _reply_view(r, account):
    return {"kind": "drive#reply", "id": r["id"], "content": r["content"], "htmlContent": r["content"],
            "author": _author_view(r["author_name"], r["author_email"], r["author_email"] == account["email"]),
            "createdTime": r["created_time"], "modifiedTime": r["modified_time"], "deleted": False}


def _comment_view(c, replies, account):
    view = {"kind": "drive#comment", "id": c["id"], "content": c["content"], "htmlContent": c["content"],
            "author": _author_view(c["author_name"], c["author_email"], c["author_email"] == account["email"]),
            "createdTime": c["created_time"], "modifiedTime": c["modified_time"],
            "resolved": c["resolved"], "deleted": False,
            "replies": [_reply_view(r, account) for r in replies]}
    if c.get("quoted_content"):
        view["quotedFileContent"] = {"mimeType": c.get("quoted_mime_type") or "text/plain",
                                     "value": c["quoted_content"]}
    return view


def _revision_view(rev, file_row):
    view = {"kind": "drive#revision", "id": rev["id"], "mimeType": rev["mime_type"],
            "modifiedTime": rev["modified_time"], "keepForever": rev["keep_forever"],
            "published": rev["published"], "publishedOutsideDomain": False,
            "lastModifyingUser": {"kind": "drive#user", "displayName": rev["last_modifying_name"],
                                  "emailAddress": rev["last_modifying_email"]}}
    if rev["published"]:
        view["publishedLink"] = _web_link(file_row).rsplit("/", 1)[0] + "/pub"
    if rev.get("original_filename"):
        view["originalFilename"] = rev["original_filename"]
    if rev.get("size"):
        view["size"] = rev["size"]
    return view


def _list_response(kind, items, token, key):
    body = {"kind": kind}
    if token:
        body["nextPageToken"] = token
    body[key] = items
    return body


# --- the Drive q subset -----------------------------------------------------------------------

class QueryError(ValueError):
    """The ``q`` string is outside the supported Drive query subset."""


_TOKEN_RE = re.compile(r"\s*(?:(?P<str>'(?:[^'\\]|\\.)*')|(?P<op>!=|>=|<=|=|>|<|\(|\))"
                       r"|(?P<word>[A-Za-z_][A-Za-z0-9_]*))")
_RFC3339_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")
_TIME_OPS = (">", ">=", "<", "<=")


def _tokenize(text):
    tokens, pos = [], 0
    while pos < len(text):
        if text[pos:].strip() == "":
            break
        match = _TOKEN_RE.match(text, pos)
        if not match:
            raise QueryError(f"unexpected character near position {pos}")
        pos = match.end()
        if match.group("str") is not None:
            tokens.append(("str", re.sub(r"\\(.)", r"\1", match.group("str")[1:-1])))
        elif match.group("op") is not None:
            tokens.append(("op", match.group("op")))
        else:
            tokens.append(("word", match.group("word")))
    return tokens


def parse_rfc3339(value):
    """Aware datetime for an RFC 3339 instant; QueryError for anything else."""
    if not _RFC3339_RE.match(value):
        raise QueryError(f"'{value}' is not an RFC 3339 timestamp")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise QueryError(f"'{value}' is not an RFC 3339 timestamp")


class _QueryParser:
    """Recursive-descent parser: ``or`` < ``and`` < parenthesised terms.

    Produces a nested-tuple AST and records whether any term mentions ``trashed``.
    """

    def __init__(self, text):
        self.tokens = _tokenize(text)
        self.pos = 0
        self.mentions_trashed = False

    def _peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else (None, None)

    def _take(self, kind=None, value=None):
        tok = self._peek()
        if tok[0] is None or (kind and tok[0] != kind) or (value is not None and tok[1].lower() != value):
            raise QueryError(f"unexpected {tok[1]!r}" if tok[0] else "unexpected end of query")
        self.pos += 1
        return tok

    def _is_word(self, value):
        tok = self._peek()
        return tok[0] == "word" and tok[1].lower() == value

    def parse(self):
        if not self.tokens:
            raise QueryError("empty query")
        node = self._or()
        if self.pos != len(self.tokens):
            raise QueryError(f"unexpected {self._peek()[1]!r}")
        return node

    def _or(self):
        node = self._and()
        while self._is_word("or"):
            self.pos += 1
            node = ("or", node, self._and())
        return node

    def _and(self):
        node = self._primary()
        while self._is_word("and"):
            self.pos += 1
            node = ("and", node, self._primary())
        return node

    def _primary(self):
        if self._peek() == ("op", "("):
            self.pos += 1
            node = self._or()
            self._take("op", ")")
            return node
        return self._term()

    def _term(self):
        kind, value = self._take()
        if kind == "str":
            self._take("word", "in")
            self._take("word", "parents")
            return ("parent", value)
        if kind != "word":
            raise QueryError(f"unexpected {value!r}")
        if value in ("name", "fullText", "mimeType"):
            op = self._take()
            if op[0] == "word" and op[1].lower() == "contains" and value in ("name", "fullText"):
                return (value + ".contains", self._take("str")[1])
            if op == ("op", "=") and value in ("name", "mimeType"):
                return (value + ".eq", self._take("str")[1])
            if op == ("op", "!=") and value == "mimeType":
                return ("mimeType.ne", self._take("str")[1])
            raise QueryError(f"unsupported operator {op[1]!r} for {value}")
        if value in ("trashed", "starred"):
            self._take("op", "=")
            flag = self._take("word")[1].lower()
            if flag not in ("true", "false"):
                raise QueryError(f"{value} must be compared with true or false")
            if value == "trashed":
                self.mentions_trashed = True
            return (value, flag == "true")
        if value == "sharedWithMe":
            if self._peek() != ("op", "="):
                return ("sharedWithMe", True)
            self.pos += 1
            flag = self._take("word")[1].lower()
            if flag not in ("true", "false"):
                raise QueryError("sharedWithMe must be compared with true or false")
            return ("sharedWithMe", flag == "true")
        if value == "modifiedTime":
            op = self._take("op")[1]
            if op not in _TIME_OPS:
                raise QueryError(f"unsupported operator {op!r} for modifiedTime")
            return ("modifiedTime", op, parse_rfc3339(self._take("str")[1]))
        raise QueryError(f"unsupported field {value!r}")


def compile_query(text, root_id=""):
    """Return ``(predicate(file_row, head_content), mentions_trashed)`` for a Drive q string.

    ``root_id`` is the folder the ``root`` alias stands for.
    """
    parser = _QueryParser(text)
    tree = parser.parse()

    def evaluate(node, f, content):
        op = node[0]
        if op == "and":
            return evaluate(node[1], f, content) and evaluate(node[2], f, content)
        if op == "or":
            return evaluate(node[1], f, content) or evaluate(node[2], f, content)
        if op == "parent":
            return f["parent_id"] == (root_id if node[1] == "root" else node[1])
        if op == "name.eq":
            return f["name"].casefold() == node[1].casefold()
        if op == "name.contains":
            return node[1].casefold() in f["name"].casefold()
        if op == "fullText.contains":
            needle = node[1].casefold()
            return any(needle in (hay or "").casefold() for hay in (f["name"], f.get("description"), content))
        if op == "mimeType.eq":
            return f["mime_type"] == node[1]
        if op == "mimeType.ne":
            return f["mime_type"] != node[1]
        if op in ("trashed", "starred"):
            return f[op] == node[1]
        if op == "sharedWithMe":
            return node[1] is False  # every file listed is the account's own (ownedByMe), none shared with it
        stored = parse_rfc3339(f["modified_time"])
        cmp = node[1]
        return (stored > node[2] if cmp == ">" else stored >= node[2] if cmp == ">=" else
                stored < node[2] if cmp == "<" else stored <= node[2])

    return (lambda f, content: evaluate(tree, f, content)), parser.mentions_trashed


def _parse_order(order_by):
    keys = []
    for part in order_by.split(","):
        bits = part.split()
        if not bits or len(bits) > 2 or bits[0] not in ORDER_KEYS or (len(bits) == 2 and bits[1] != "desc"):
            return _invalid(f"Invalid Value: orderBy must be one of {', '.join(ORDER_KEYS)} "
                            "with an optional ' desc'", "invalid", "orderBy")
        keys.append((FILE_SORT[bits[0]], len(bits) == 2))
    return keys


def _sorted_files(rows, keys):
    def stable(rows_, column, reverse):
        if column == "name":
            return sorted(rows_, key=lambda r: (r["name"].casefold(), r["id"]), reverse=reverse)
        return sorted(rows_, key=lambda r: (r[column], r["id"]), reverse=reverse)
    for column, reverse in reversed(keys):
        rows = stable(rows, column, reverse)
    return rows


# --- files -------------------------------------------------------------------------------------

@_live
def list_files(account_id, q=None, page_size=None, page_token=None, order_by=None, fields=None):
    account = _account(account_id)
    keys = [("modified_time", True)]
    if order_by:
        keys = _parse_order(order_by)
        if isinstance(keys, DriveError):
            return keys
    predicate, mentions_trashed = None, False
    if q is not None and q.strip():
        try:
            predicate, mentions_trashed = compile_query(q, account["root_folder_id"])
        except QueryError as exc:
            return DriveError(400, f"Invalid Value: invalid query ({exc})", "invalidQuery", "q")
    rows = _store.table("files").find(lambda f: f["owner_account_id"] == account_id)
    if not mentions_trashed:
        rows = [f for f in rows if not f["trashed"]]
    if predicate is not None:
        heads = {r["id"]: r["content"] for r in _store.table("revisions").rows()}
        rows = [f for f in rows if predicate(f, heads.get(f.get("head_revision_id"), ""))]
    rows = _sorted_files(rows, keys)
    paged = _page(rows, page_size, page_token, 100, 1000)
    if isinstance(paged, DriveError):
        return paged
    window, token = paged
    shared = _shared_ids()
    body = _list_response("drive#fileList", [_file_view(f, account, shared) for f in window], token, "files")
    body["incompleteSearch"] = False
    return _shape(body, fields, ("kind", "nextPageToken", "incompleteSearch", "files"),
                  "files", FILE_FIELDS)


@_live
def get_file(file_id, account_id, fields=None):
    f = _owned(file_id, account_id)
    if f is None:
        return _missing(file_id)
    return _shape(_single_file_view(f, account_id), fields, FILE_FIELDS)


@_live
def export_file(file_id, account_id, mime_type):
    """A Google Doc's text, as files.export gives it for text/plain; a DriveError otherwise."""
    f = _owned(file_id, account_id)
    if f is None:
        return _missing(file_id)
    if not mime_type:
        return _invalid("Required parameter: mimeType", "required", "mimeType")
    if not f["mime_type"].startswith(NATIVE_PREFIX) or f["mime_type"] == FOLDER_MIME:
        return DriveError(403, "Export only supports Docs Editors files.", "fileNotExportable", "fileId")
    if f["mime_type"] != DOC_MIME or mime_type != "text/plain":
        return _invalid("The requested conversion is not supported.", "badRequest", "convertTo")
    peer = _linked_peer_of(f)
    if peer is None:
        return _linked_peer.doc_plain_text(p for p in _linked_seed("google-docs-api", "paragraphs")
                                           if p["document_id"] == file_id)
    try:
        return peer.export(file_id, mime_type)
    except _linked_peer.PeerRefused:
        return _missing(file_id)


def _check_parent(parent_id, account_id):
    """The folder a file may be placed in, or a DriveError."""
    resolved = _resolve_folder(parent_id, account_id)
    if resolved == _root_id(account_id):
        return {"id": resolved, "mime_type": FOLDER_MIME, "trashed": False}
    parent = _owned(resolved, account_id)
    if parent is None:
        return _missing(parent_id)
    if parent["mime_type"] != FOLDER_MIME:
        return _invalid(f"The specified parent {parent_id} is not a folder.", "invalidParent", "parents")
    return parent


def _initial_parent(parents, account_id):
    if parents is None or not parents:
        return _root_id(account_id)
    if len(parents) > 1:
        return _invalid("A file can have only one parent; multiple parents are not supported.",
                        "multipleParentsNotSupported", "parents")
    parent = _check_parent(parents[0], account_id)
    if isinstance(parent, DriveError):
        return parent
    return parent["id"]


@_live
def create_file(account_id, name=None, mime_type=None, parents=None, description=None, starred=None):
    parent_id = _initial_parent(parents, account_id)
    if isinstance(parent_id, DriveError):
        return parent_id
    if name is not None and not name.strip():
        return _invalid("The file name must not be empty.", "invalid", "name")
    file_id = _new_id("1", 33)
    api = LINKED_API_BY_MIME.get(mime_type or "")
    peer = _linked_peer.peer_for(api) if api else None
    if peer is not None:
        # A Google file made in Drive is a real document, spreadsheet, deck or form of its editor.
        try:
            made = peer.create(account_id, name)
        except _linked_peer.PeerRefused as exc:
            return _invalid(f"The file could not be created: {exc}", "invalid", "mimeType")
        file_id, name = made["id"], made["title"]
        _linked_ids[file_id], _linked_marks[file_id] = api, made["fingerprint"]
    now = _drive_time(_now())
    row = {"id": file_id, "name": name or "Untitled", "mime_type": mime_type or "application/octet-stream",
           "parent_id": parent_id, "owner_account_id": account_id, "created_time": now,
           "modified_time": now, "size": "", "starred": bool(starred), "trashed": False,
           "trashed_via": "", "description": description or "", "head_revision_id": ""}
    stored = _store.table("files").upsert(row)
    _add_owner_permission(stored["id"], account_id)
    return _single_file_view(stored, account_id)


def _add_owner_permission(file_id, account_id):
    account = _account(account_id)
    owner_id = _derived_id(account["email"])
    _store.table("permissions").upsert({
        "_pk": f"{file_id}:{owner_id}", "file_id": file_id, "id": owner_id, "type": "user", "role": "owner",
        "email_address": account["email"], "display_name": account["display_name"], "domain": "",
        "allow_file_discovery": False})


def _is_descendant(folder_id, ancestor_id, by_id):
    seen = set()
    while folder_id and folder_id not in seen:
        if folder_id == ancestor_id:
            return True
        seen.add(folder_id)
        row = by_id.get(folder_id)
        folder_id = row["parent_id"] if row else ""
    return False


def _split_ids(value):
    return [part.strip() for part in value.split(",") if part.strip()] if value else []


@_live
def update_file(file_id, account_id, changes, add_parents=None, remove_parents=None):
    """``changes`` holds only the body keys the caller sent (name, description, starred, trashed)."""
    f = _owned(file_id, account_id)
    if f is None:
        return _missing(file_id)
    patch = {}
    if "name" in changes:
        if not changes["name"] or not changes["name"].strip():
            return _invalid("The file name must not be empty.", "invalid", "name")
        patch["name"] = changes["name"]
    if "description" in changes:
        patch["description"] = changes["description"] or ""
    if "starred" in changes:
        if changes["starred"] is None:
            return _invalid("starred must be true or false.", "invalid", "starred")
        patch["starred"] = changes["starred"]
    if "trashed" in changes:
        if changes["trashed"] is None:
            return _invalid("trashed must be true or false.", "invalid", "trashed")
        patch["trashed"] = changes["trashed"]
        patch["trashed_via"] = ""
    adds, removes = _split_ids(add_parents), _split_ids(remove_parents)
    if adds or removes:
        by_id = {r["id"]: r for r in _store.table("files").find(lambda r: r["owner_account_id"] == account_id)}
        adds = [_resolve_folder(p, account_id) for p in adds]
        removes = [_resolve_folder(p, account_id) for p in removes]
        for pid in removes:
            if pid != f["parent_id"]:
                return _invalid(f"The file {file_id} is not in the folder {pid}.", "invalidParent", "removeParents")
        parents = [p for p in ([f["parent_id"]] if f["parent_id"] else []) if p not in removes]
        for pid in adds:
            parent = _check_parent(pid, account_id)
            if isinstance(parent, DriveError):
                return parent
            if _is_descendant(parent["id"], file_id, by_id):
                return _invalid("A folder cannot be moved into itself or one of its subfolders.",
                                "cannotMoveIntoSelf", "addParents")
            if parent["id"] not in parents:
                parents.append(parent["id"])
        if not parents:
            return _invalid("A file must have a parent folder; use addParents to move it.", "invalid", "removeParents")
        if len(parents) > 1:
            return _invalid("A file can have only one parent; multiple parents are not supported.",
                            "multipleParentsNotSupported", "addParents")
        patch["parent_id"] = parents[0]
    peer = _linked_peer_of(f) if "name" in patch and patch["name"] != f["name"] else None
    if peer is not None:
        # The title lives in the editor: renaming the Drive file renames the document.
        try:
            _linked_marks[file_id] = peer.rename(file_id, patch["name"])["fingerprint"]
        except _linked_peer.PeerRefused:
            return _missing(file_id)
    if patch:
        patch["modified_time"] = _drive_time(_now())
        updated = _store.table("files").patch(file_id, patch)
        if "trashed" in patch and f["mime_type"] == FOLDER_MIME:
            _cascade_trash(file_id, account_id, patch["trashed"])
    else:
        updated = f
    return _single_file_view(_store.table("files").get(file_id) or updated, account_id)


def _cascade_trash(folder_id, account_id, trashed):
    """Trashing a folder trashes what is inside it; restoring it restores only that."""
    files = _store.table("files")
    rows = files.find(lambda r: r["owner_account_id"] == account_id)
    children = {}
    for r in rows:
        children.setdefault(r["parent_id"], []).append(r)
    stack = [folder_id]
    while stack:
        for child in children.get(stack.pop(), []):
            if trashed and not child["trashed"]:
                files.patch(child["id"], {"trashed": True, "trashed_via": folder_id})
            elif not trashed and child["trashed"] and child.get("trashed_via") == folder_id:
                files.patch(child["id"], {"trashed": False, "trashed_via": ""})
            if child["mime_type"] == FOLDER_MIME:
                stack.append(child["id"])


# --- upload, content update, download, delete -------------------------------------------------------

def _content_columns(content):
    """The revision columns and byte size of uploaded text or bytes: text kept as text, other bytes in
    base64, so either comes back byte for byte."""
    data = content.encode("utf-8") if isinstance(content, str) else bytes(content)
    try:
        return {"content": data.decode("utf-8"), "content_b64": ""}, len(data)
    except UnicodeDecodeError:
        return {"content": "", "content_b64": base64.b64encode(data).decode("ascii")}, len(data)


def _content_type_refused(mime_type):
    if mime_type == FOLDER_MIME:
        return _invalid("A folder cannot carry content; create it with POST /drive/v3/files.", "invalid", "mimeType")
    if mime_type.startswith(NATIVE_PREFIX):
        return _invalid(f"Conversion to {mime_type} is not supported by this mock; upload a plain "
                        "content type such as text/plain.", "invalid", "mimeType")
    return None


def _new_revision(file_id, account_id, name, mime_type, content, now):
    columns, size = _content_columns(content)
    account = _account(account_id)
    revision = _store.table("revisions").upsert({
        "id": _new_id("0B", 30), "file_id": file_id, "modified_time": now, "size": str(size),
        "keep_forever": False, "published": False, "mime_type": mime_type, "original_filename": name,
        "last_modifying_email": account["email"], "last_modifying_name": account["display_name"], **columns})
    return revision["id"], str(size)


@_live
def upload_file(account_id, name, mime_type, content, parents=None, description=None, upload_type=None):
    """files.create with content (text or bytes); ``name`` None is Drive's ``Untitled``."""
    if upload_type not in (None, "multipart", "media"):
        return _invalid(f"Unsupported uploadType '{upload_type}': this mock accepts media, multipart, or "
                        "the JSON upload body.", "invalid", "uploadType")
    name = "Untitled" if name is None else name
    if not name.strip():
        return _invalid("The file name must not be empty.", "invalid", "name")
    refused = _content_type_refused(mime_type)
    if refused is not None:
        return refused
    parent_id = _initial_parent(parents, account_id)
    if isinstance(parent_id, DriveError):
        return parent_id
    now = _drive_time(_now())
    file_id = _new_id("1", 33)
    revision_id, size = _new_revision(file_id, account_id, name, mime_type, content, now)
    stored = _store.table("files").upsert({
        "id": file_id, "name": name, "mime_type": mime_type, "parent_id": parent_id,
        "owner_account_id": account_id, "created_time": now, "modified_time": now, "size": size,
        "starred": False, "trashed": False, "trashed_via": "", "description": description or "",
        "head_revision_id": revision_id})
    _add_owner_permission(file_id, account_id)
    return _single_file_view(stored, account_id)


@_live
def update_content(file_id, account_id, content, name=None, mime_type=None, description=None):
    """files.update with an upload: the content becomes the file's new head revision; name, mimeType
    and description change only when given."""
    f = _owned(file_id, account_id)
    if f is None:
        return _missing(file_id)
    if f["mime_type"] == FOLDER_MIME or f["mime_type"].startswith(NATIVE_PREFIX):
        return _invalid("Only a file with binary content takes uploaded content; a folder or a Google Docs "
                        "editors file does not.", "invalid", "fileId")
    mime_type = mime_type or f["mime_type"]
    refused = _content_type_refused(mime_type)
    if refused is not None:
        return refused
    if name is not None and not name.strip():
        return _invalid("The file name must not be empty.", "invalid", "name")
    now = _drive_time(_now())
    revision_id, size = _new_revision(file_id, account_id, name or f["name"], mime_type, content, now)
    patch = {"mime_type": mime_type, "size": size, "modified_time": now, "head_revision_id": revision_id}
    if name is not None:
        patch["name"] = name
    if description is not None:
        patch["description"] = description
    return _single_file_view(_store.table("files").patch(file_id, patch), account_id)


@_live
def download_file(file_id, account_id):
    """files.get with alt=media: ``(bytes, mimeType)`` of the head revision, or a DriveError."""
    f = _owned(file_id, account_id)
    if f is None:
        return _missing(file_id)
    if f["mime_type"] == FOLDER_MIME or f["mime_type"].startswith(NATIVE_PREFIX):
        return DriveError(403, "Only files with binary content can be downloaded. Use Export with Docs Editors files.",
                          "fileNotDownloadable", "alt")
    head = _store.table("revisions").get(f.get("head_revision_id") or "")
    if head is None:
        return b"", f["mime_type"]
    if head.get("content_b64"):
        return base64.b64decode(head["content_b64"]), f["mime_type"]
    return (head.get("content") or "").encode("utf-8"), f["mime_type"]


@_live
def delete_file(file_id, account_id):
    """files.delete: the file is gone for good, not trashed; a folder takes everything inside it along."""
    f = _owned(file_id, account_id)
    if f is None:
        return _missing(file_id)
    gone = {file_id}
    if f["mime_type"] == FOLDER_MIME:
        children = {}
        for row in _store.table("files").find(lambda r: r["owner_account_id"] == account_id):
            children.setdefault(row["parent_id"], []).append(row["id"])
        stack = [file_id]
        while stack:
            for child in children.get(stack.pop(), []):
                if child not in gone:
                    gone.add(child)
                    stack.append(child)
    files = _store.table("files")
    for gone_id in sorted(gone):
        peer = _linked_peer_of(files.get(gone_id) or {"mime_type": ""})
        if peer is not None:
            # Deleting the Drive file deletes the document itself.
            try:
                peer.delete(gone_id)
            except _linked_peer.PeerRefused:
                pass
    _drop_files(gone)
    return None


def _drop_files(gone):
    """Remove Drive files and everything Drive keeps about them."""
    for table in ("permissions", "comments", "replies", "revisions"):
        _store.table(table).delete_where(lambda r: r.get("file_id") in gone)
    _store.table("files").delete_where(lambda r: r["id"] in gone)
    for fid in gone:
        _linked_ids.pop(fid, None)
        _linked_marks.pop(fid, None)


# --- permissions ----------------------------------------------------------------------------------

@_live
def list_permissions(file_id, account_id, page_size=None, page_token=None, fields=None):
    if _owned(file_id, account_id) is None:
        return _missing(file_id)
    rows = _store.table("permissions").find(lambda p: p["file_id"] == file_id)
    rows.sort(key=lambda p: (p["role"] != "owner", p["id"]))
    paged = _page(rows, page_size, page_token, 100, 100)
    if isinstance(paged, DriveError):
        return paged
    window, token = paged
    body = _list_response("drive#permissionList", [_permission_view(p) for p in window], token, "permissions")
    return _shape(body, fields, ("kind", "nextPageToken", "permissions"), "permissions", PERMISSION_FIELDS)


@_live
def create_permission(file_id, account_id, type_, role, email_address=None, domain=None,
                      allow_file_discovery=None):
    if _owned(file_id, account_id) is None:
        return _missing(file_id)
    if type_ not in PERMISSION_TYPES:
        return _invalid(f"Invalid value for type: '{type_}'. Must be one of {', '.join(PERMISSION_TYPES)}.",
                        "invalid", "type")
    if role == "owner":
        return DriveError(400, "Ownership transfer is not supported by this mock; grant reader, commenter "
                          "or writer instead.", "invalidSharingRequest", "role")
    if role not in GRANTABLE_ROLES:
        return _invalid(f"Invalid value for role: '{role}'. Must be one of {', '.join(GRANTABLE_ROLES)}.",
                        "invalid", "role")
    if type_ in ("user", "group"):
        if not email_address:
            return _invalid(f"The emailAddress field is required for type {type_}.", "invalidArgument", "emailAddress")
        if domain:
            return _invalid(f"The domain field cannot be used with type {type_}.", "invalidArgument", "domain")
    elif type_ == "domain":
        if not domain:
            return _invalid("The domain field is required for type domain.", "invalidArgument", "domain")
        if email_address:
            return _invalid("The emailAddress field cannot be used with type domain.", "invalidArgument", "emailAddress")
    else:
        if email_address or domain:
            return _invalid("emailAddress and domain cannot be used with type anyone.", "invalidArgument", "type")
    if allow_file_discovery is not None and type_ not in ("domain", "anyone"):
        return _invalid("allowFileDiscovery only applies to type domain or anyone.", "invalidArgument", "allowFileDiscovery")
    account = _account(account_id)
    if type_ in ("user", "group") and email_address.lower() == account["email"].lower():
        return _invalid("The file owner already has full access.", "invalidSharingRequest", "emailAddress")
    discovery = bool(allow_file_discovery)
    display = ""
    if type_ in ("user", "group"):
        email_address = email_address.strip()
        person = _store.table("directory").get(email_address) or \
            _store.table("directory").find_one(lambda r: r["email"].lower() == email_address.lower())
        display = person["display_name"] if person else ""
        pid = _derived_id(person["email"] if person else email_address.lower())
    elif type_ == "domain":
        pid = _derived_id("domain:" + domain.lower())
    else:
        pid = "anyone" if discovery else "anyoneWithLink"
    existing = _store.table("permissions").get(f"{file_id}:{pid}")
    row = {"_pk": f"{file_id}:{pid}", "file_id": file_id, "id": pid, "type": type_, "role": role,
           "email_address": email_address or "", "display_name": display,
           "domain": (domain or "").lower(), "allow_file_discovery": discovery}
    if existing is not None and existing["role"] == "owner":
        return _invalid("The file owner already has full access.", "invalidSharingRequest", "emailAddress")
    stored = _store.table("permissions").upsert(row)
    return _permission_view(stored)


@_live
def delete_permission(file_id, permission_id, account_id):
    if _owned(file_id, account_id) is None:
        return _missing(file_id)
    row = _store.table("permissions").get(f"{file_id}:{permission_id}")
    if row is None:
        return DriveError(404, f"Permission not found: {permission_id}.", "notFound", "permissionId")
    if row["role"] == "owner":
        return DriveError(400, "The owner of a file cannot be removed.", "cannotDeletePermission", "permissionId")
    _store.table("permissions").delete(f"{file_id}:{permission_id}")
    return None


# --- comments ---------------------------------------------------------------------------------------

@_live
def list_comments(file_id, account_id, page_size=None, page_token=None, fields=None):
    if _owned(file_id, account_id) is None:
        return _missing(file_id)
    account = _account(account_id)
    rows = sorted(_store.table("comments").find(lambda c: c["file_id"] == file_id),
                  key=lambda c: (c["created_time"], c["id"]))
    replies = _store.table("replies").find(lambda r: r["file_id"] == file_id)
    paged = _page(rows, page_size, page_token, 20, 100)
    if isinstance(paged, DriveError):
        return paged
    window, token = paged
    views = [_comment_view(c, sorted((r for r in replies if r["comment_id"] == c["id"]),
                                     key=lambda r: (r["created_time"], r["id"])), account) for c in window]
    body = _list_response("drive#commentList", views, token, "comments")
    return _shape(body, fields, ("kind", "nextPageToken", "comments"), "comments", COMMENT_FIELDS)


@_live
def create_comment(file_id, account_id, content, quoted_value=None, quoted_mime_type=None):
    if _owned(file_id, account_id) is None:
        return _missing(file_id)
    if not content or not content.strip():
        return _invalid("The comment content must not be empty.", "required", "content")
    account = _account(account_id)
    now = _drive_time(_now())
    stored = _store.table("comments").upsert({
        "id": _new_id("AAAB", 11), "file_id": file_id, "content": content,
        "author_name": account["display_name"], "author_email": account["email"],
        "created_time": now, "modified_time": now, "resolved": False,
        "quoted_content": quoted_value or "", "quoted_mime_type": (quoted_mime_type or "text/html") if quoted_value else ""})
    return _comment_view(stored, [], account)


# --- revisions ----------------------------------------------------------------------------------------

@_live
def list_revisions(file_id, account_id, page_size=None, page_token=None, fields=None):
    f = _owned(file_id, account_id)
    if f is None:
        return _missing(file_id)
    rows = sorted(_store.table("revisions").find(lambda r: r["file_id"] == file_id),
                  key=lambda r: (r["modified_time"], r["id"]))
    paged = _page(rows, page_size, page_token, 200, 200)
    if isinstance(paged, DriveError):
        return paged
    window, token = paged
    body = _list_response("drive#revisionList", [_revision_view(r, f) for r in window], token, "revisions")
    return _shape(body, fields, ("kind", "nextPageToken", "revisions"), "revisions", REVISION_FIELDS)


def _revision(file_id, revision_id):
    rev = _store.table("revisions").get(revision_id)
    if rev is None or rev["file_id"] != file_id:
        return None
    return rev


@_live
def get_revision(file_id, revision_id, account_id, fields=None):
    f = _owned(file_id, account_id)
    if f is None:
        return _missing(file_id)
    rev = _revision(file_id, revision_id)
    if rev is None:
        return DriveError(404, f"Revision not found: {revision_id}.", "notFound", "revisionId")
    return _shape(_revision_view(rev, f), fields, REVISION_FIELDS)


@_live
def update_revision(file_id, revision_id, account_id, changes):
    """``changes`` holds only the body keys the caller sent (keepForever, published)."""
    f = _owned(file_id, account_id)
    if f is None:
        return _missing(file_id)
    rev = _revision(file_id, revision_id)
    if rev is None:
        return DriveError(404, f"Revision not found: {revision_id}.", "notFound", "revisionId")
    if not changes:
        return _invalid("Provide keepForever or published to update.", "required", "keepForever")
    native = f["mime_type"].startswith(NATIVE_PREFIX)
    patch = {}
    for key, column in (("keepForever", "keep_forever"), ("published", "published")):
        if key not in changes:
            continue
        if changes[key] is None:
            return _invalid(f"{key} must be true or false.", "invalid", key)
        patch[column] = changes[key]
    if "keep_forever" in patch and native:
        return _invalid("keepForever is only supported for files with binary content.", "invalid", "keepForever")
    if "published" in patch and not native:
        return _invalid("published is only supported for Google Docs editors files.", "invalid", "published")
    updated = _store.table("revisions").patch(revision_id, patch)
    return _revision_view(updated, f)


_store.eager_load()
