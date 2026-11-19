"""Data access module for the Outlook Contacts (Microsoft Graph) mock service.

Serves exactly the contact operations the connector needs -- list contacts,
get a contact, create, update and delete a contact, and filter them by name or
email -- in the shape of Microsoft Graph v1.0 (graph.microsoft.com/v1.0/me/
contacts). Every read and write is scoped to the mailbox the presented token's
connected account owns: Alex Carter's at Contoso, the same mailbox outlook-api
serves. Mock simplifications (also stated in api_test_results.md): the default
contacts folder only, no photos or extensions, and a subset of OData $filter.
"""

import base64
import hashlib
import json
import operator
import re
import secrets
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlencode

DATA_DIR = Path(__file__).parent

sys.path.insert(0, str(DATA_DIR.parent))
import _mock_clock  # noqa: E402
from _mutable_store import get_store, read_seed_with_ctx  # noqa: E402
from _connector_auth import ConnectorAuth  # noqa: E402

_API = "outlook-contacts-api"
_store = get_store(_API)

GRAPH = "https://graph.microsoft.com/v1.0"
DEFAULT_TOP, MAX_TOP = 10, 1000
# (Graph property, seed column, kind) for every writable contact property, in the order Graph returns them.
PROPERTIES = (
    ("categories", "categories", "list"), ("birthday", "birthday", "date"), ("fileAs", "file_as", "str"),
    ("displayName", "display_name", "str"), ("givenName", "given_name", "str"), ("initials", "initials", "str"),
    ("middleName", "middle_name", "str"), ("nickName", "nickname", "str"), ("surname", "surname", "str"),
    ("title", "title", "str"), ("yomiGivenName", "yomi_given_name", "str"), ("yomiSurname", "yomi_surname", "str"),
    ("yomiCompanyName", "yomi_company_name", "str"), ("generation", "generation", "str"),
    ("imAddresses", "im_addresses", "list"), ("jobTitle", "job_title", "str"), ("companyName", "company_name", "str"),
    ("department", "department", "str"), ("officeLocation", "office_location", "str"),
    ("profession", "profession", "str"), ("businessHomePage", "business_home_page", "str"),
    ("assistantName", "assistant_name", "str"), ("manager", "manager", "str"), ("homePhones", "home_phones", "list"),
    ("mobilePhone", "mobile_phone", "str"), ("businessPhones", "business_phones", "list"),
    ("spouseName", "spouse_name", "str"), ("personalNotes", "personal_notes", "str"),
    ("children", "children", "list"), ("emailAddresses", "email_addresses", "emails"),
    ("homeAddress", "home_address", "address"), ("businessAddress", "business_address", "address"),
    ("otherAddress", "other_address", "address"),
)
ADDRESS_KEYS = ("street", "city", "state", "countryOrRegion", "postalCode")
# Outlook keeps three email addresses, two business and two home phones, and three IM addresses per contact.
LIMITS = {"emailAddresses": 3, "businessPhones": 2, "homePhones": 2, "imAddresses": 3}
NAME_PARTS = ("givenName", "middleName", "surname")


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _parsed(value, empty):
    """A JSON-encoded cell (as a CSV overlay carries it) decoded; ``empty`` for a blank one."""
    if isinstance(value, str) and value.strip()[:1] in ("[", "{"):
        try:
            return json.loads(value)
        except ValueError:
            return empty
    if value is None or value == "":
        return empty
    return value


def _list(value):
    value = _parsed(value, [])
    if isinstance(value, str):
        return [part.strip() for part in value.split(";") if part.strip()]
    return list(value) if isinstance(value, (list, tuple)) else []


def _coerce_contact_row(r):
    out = _strip_ctx(r)
    for _name, column, kind in PROPERTIES:
        value = out.get(column)
        if kind in ("str", "date"):
            out[column] = "" if value is None else str(value)
        elif kind == "list":
            out[column] = [str(v) for v in _list(value)]
        elif kind == "emails":
            out[column] = [{"name": str(e.get("name") or ""), "address": str(e.get("address") or "")}
                           if isinstance(e, dict) else {"name": "", "address": str(e)} for e in _list(value)]
        else:
            value = _parsed(value, {})
            out[column] = {k: str(v) for k, v in value.items() if k in ADDRESS_KEYS and v} \
                if isinstance(value, dict) else {}
    return out


_store.register("mailboxes", primary_key="account_id",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("mailboxes.json", "mailboxes")])
_store.register("contacts", primary_key="id",
                initial_loader=lambda: [_coerce_contact_row(r) for r in _load("contacts.json", "contacts")],
                row_coercer=_coerce_contact_row)

auth = ConnectorAuth(_API, store=_store, data_dir=DATA_DIR)


class GraphError:
    """A Microsoft Graph error envelope and the HTTP status it is served with."""

    def __init__(self, status, code, message):
        self.status = status
        request_id = str(uuid.uuid4())
        self.body = {"error": {"code": code, "message": message, "innerError": {
            "date": _mock_clock.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            "request-id": request_id, "client-request-id": request_id}}}


def bad_request(message, code="ErrorInvalidRequest"):
    return GraphError(400, code, message)


def _not_found():
    return GraphError(404, "ErrorItemNotFound", "The specified object was not found in the store.")


def _no_mailbox():
    return GraphError(404, "MailboxNotEnabledForRESTAPI",
                      "The mailbox is either inactive, soft-deleted, or is hosted on-premise.")


def _now():
    return _mock_clock.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- OData $filter, a subset -------------------------------------------------------------------

_TOKEN = re.compile(r"\s*(?:(\()|(\))|(,)|('(?:[^']|'')*')|(-?\d+(?:\.\d+)?(?![\w:-]))|"
                    r"(\d{4}-\d{2}-\d{2}(?:T[\d:.]+(?:Z|[+-]\d{2}:\d{2})?)?)|"
                    r"([A-Za-z_][\w/]*(?::\s*[A-Za-z_][\w/]*)?))")
_FUNCTIONS = ("startswith", "endswith", "contains")
_OPS = {"eq": operator.eq, "ne": operator.ne, "gt": operator.gt, "ge": operator.ge, "lt": operator.lt,
        "le": operator.le}
_STAMP = re.compile(r"\d{4}-\d{2}-\d{2}")


class FilterError(ValueError):
    pass


def _tokens(text):
    out, pos = [], 0
    while text[pos:].strip():
        match = _TOKEN.match(text, pos)
        if not match:
            raise FilterError(f"Syntax error at position {pos} in '{text}'.")
        lp, rp, comma, string, number, stamp, word = match.groups()
        if lp or rp or comma:
            out.append((lp or rp or comma, None))
        elif string is not None:
            out.append(("str", string[1:-1].replace("''", "'")))
        elif number is not None:
            out.append(("num", float(number) if "." in number else int(number)))
        elif stamp is not None:
            out.append(("str", stamp))
        else:
            out.append(("word", word))
        pos = match.end()
    return out


class _Parser:
    """Recursive-descent parser for the OData boolean expressions this mock evaluates."""

    def __init__(self, text, fields):
        self.items, self.i, self.fields = _tokens(text), 0, fields

    def peek(self, offset=0):
        j = self.i + offset
        return self.items[j] if j < len(self.items) else (None, None)

    def keyword(self, word):
        kind, value = self.peek()
        if kind == "word" and value.lower() == word:
            self.i += 1
            return True
        return False

    def take(self, kind):
        found, value = self.peek()
        if found != kind:
            raise FilterError(f"Expected {kind} in the filter expression.")
        self.i += 1
        return value

    def parse(self):
        node = self.or_expr()
        if self.peek()[0] is not None:
            kind, value = self.peek()
            raise FilterError(f"Unexpected '{value if value is not None else kind}' in the filter expression.")
        return node

    def or_expr(self):
        node = self.and_expr()
        while self.keyword("or"):
            node = ("or", node, self.and_expr())
        return node

    def and_expr(self):
        node = self.unary()
        while self.keyword("and"):
            node = ("and", node, self.unary())
        return node

    def unary(self):
        if self.keyword("not"):
            return ("not", self.unary())
        return self.primary()

    def primary(self):
        kind, value = self.peek()
        if kind == "(":
            self.i += 1
            node = self.or_expr()
            self.take(")")
            return node
        if kind == "word" and value.lower() in _FUNCTIONS and self.peek(1)[0] == "(":
            self.i += 2
            field = self.property()
            self.take(",")
            text = self.take("str")
            self.take(")")
            return (value.lower(), field, text)
        if kind == "word" and value.endswith("/any") and self.peek(1)[0] == "(":
            return self.any_expr()
        field = self.property()
        op = self.take("word").lower()
        if op not in _OPS:
            raise FilterError(f"Unsupported operator '{op}' in the filter expression.")
        return ("cmp", op, field, self.literal())

    def any_expr(self):
        collection = self.take("word")[:-len("/any")]
        if collection not in self.fields:
            raise FilterError(self.unknown(collection))
        self.take("(")
        variable, _, path = self.take("word").partition(":")
        path = path.strip()
        if path != variable and not path.startswith(variable + "/"):
            raise FilterError("Expected a lambda such as a:a/address eq 'priya.nair@contoso.com' inside any().")
        op = self.take("word").lower()
        if op not in ("eq", "ne"):
            raise FilterError(f"Unsupported operator '{op}' inside any().")
        literal = self.literal()
        self.take(")")
        return ("any", collection, path[len(variable) + 1:], op, literal)

    def property(self):
        kind, value = self.peek()
        if kind != "word":
            raise FilterError("Expected a property name in the filter expression.")
        if value not in self.fields:
            raise FilterError(self.unknown(value))
        self.i += 1
        return value

    def literal(self):
        kind, value = self.peek()
        if kind == "word" and value.lower() in ("true", "false", "null"):
            self.i += 1
            return {"true": True, "false": False, "null": None}[value.lower()]
        if kind in ("str", "num"):
            self.i += 1
            return value
        raise FilterError("Expected a literal after the comparison operator.")

    @staticmethod
    def unknown(name):
        return f"Could not find a property named '{name}' on type 'microsoft.graph.contact'."


def _value_of(view, path):
    node = view
    for part in path.split("/") if path else ():
        node = node.get(part) if isinstance(node, dict) else None
    return node


def _compare(op, left, right):
    if isinstance(left, str) and isinstance(right, str):
        left, right = left.casefold(), right.casefold()
        if _STAMP.match(left) and _STAMP.match(right):
            left, right = left[:19], right.rstrip("z")[:19]
    try:
        return _OPS[op](left, right)
    except TypeError:
        return False


def _evaluate(node, view):
    kind = node[0]
    if kind == "and":
        return _evaluate(node[1], view) and _evaluate(node[2], view)
    if kind == "or":
        return _evaluate(node[1], view) or _evaluate(node[2], view)
    if kind == "not":
        return not _evaluate(node[1], view)
    if kind in _FUNCTIONS:
        text = _value_of(view, node[1])
        if not isinstance(text, str):
            return False
        test = {"startswith": str.startswith, "endswith": str.endswith, "contains": str.__contains__}[kind]
        return test(text.casefold(), node[2].casefold())
    if kind == "any":
        _any, collection, path, op, literal = node
        return any(_compare(op, _value_of(item, path) if path else item, literal)
                   for item in _value_of(view, collection) or [])
    _cmp, op, field, literal = node
    return _compare(op, _value_of(view, field), literal)


def compile_filter(text, fields):
    """A predicate over a view dict for an OData ``$filter`` string, or a GraphError."""
    try:
        tree = _Parser(text, fields).parse()
    except FilterError as exc:
        return bad_request(f"Invalid filter clause: {exc}", code="BadRequest")
    return lambda view: _evaluate(tree, view)


def compile_orderby(text, fields):
    """A list of (path, descending) for an OData ``$orderby``, or a GraphError."""
    out = []
    for part in [p.strip() for p in (text or "").split(",") if p.strip()]:
        bits = part.split()
        if bits[0] not in fields or len(bits) > 2 or (len(bits) == 2 and bits[1].lower() not in ("asc", "desc")):
            return bad_request(f"Invalid $orderby clause '{part}'; this mock orders by {', '.join(fields)}.",
                               code="BadRequest")
        out.append((bits[0], len(bits) == 2 and bits[1].lower() == "desc"))
    return out


def _ordered(views, order):
    """``views`` sorted by ``order``, earlier keys first, missing values last."""
    for path, descending in reversed(order):
        views = sorted(views, reverse=descending, key=lambda v, path=path: (
            _value_of(v, path) is None, str(_value_of(v, path)).casefold()))
    return views


def _selection(select):
    """The property names ``$select`` asks for (None for every property), or a GraphError."""
    if not select:
        return None
    names = [s.strip() for s in select.split(",") if s.strip()]
    unknown = [n for n in names if n not in SELECTABLE]
    if unknown:
        return bad_request(f"Could not find a property named '{unknown[0]}' on type 'microsoft.graph.contact'.",
                           code="BadRequest")
    return names


def _pick(view, names):
    if names is None:
        return view
    out = {k: view[k] for k in ("@odata.etag", "id") if k in view}
    out.update((n, view.get(n)) for n in names)
    return out


def _paged(views, top, skip, link, query, context):
    for name, value in (("$top", top), ("$skip", skip)):
        if value is not None and value < 0:
            return bad_request(f"Invalid value '{value}' for {name} query option found. The {name} query option "
                               "requires a non-negative integer value.", code="BadRequest")
    if top is not None and top > MAX_TOP:
        return bad_request(f"The limit of '{MAX_TOP}' for Top query has been exceeded. The value from the incoming "
                           f"request is '{top}'.", code="BadRequest")
    size, start = DEFAULT_TOP if top is None else top, skip or 0
    out = {"@odata.context": context, "value": views[start:start + size]}
    if size and start + size < len(views):
        params = {k: v for k, v in query.items() if v is not None}
        params["$skip"] = start + size
        out["@odata.nextLink"] = f"{link}?{urlencode(params, safe='$')}"
    return out


# --- rendering ------------------------------------------------------------------------------

def _etag(row):
    digest = hashlib.sha256(json.dumps(row, sort_keys=True, default=str).encode()).digest()
    return 'W/"' + base64.b64encode(digest[:21]).decode() + '"'


def _contact_view(row):
    etag = _etag(row)
    view = {"@odata.etag": etag, "id": row["id"], "createdDateTime": row["created"],
            "lastModifiedDateTime": row["last_modified"], "changeKey": etag[3:-1],
            "parentFolderId": row["parent_folder_id"]}
    for name, column, kind in PROPERTIES:
        value = row[column]
        if kind == "emails":
            view[name] = [{"name": e["name"] or e["address"], "address": e["address"]} for e in value]
        elif kind in ("list", "address"):
            view[name] = list(value) if kind == "list" else dict(value)
        else:
            view[name] = value or None
    return view


SELECTABLE = ("id", "createdDateTime", "lastModifiedDateTime", "changeKey", "parentFolderId",
              *(name for name, _column, _kind in PROPERTIES))
FILTERABLE = ("id", "displayName", "givenName", "middleName", "surname", "nickName", "fileAs", "companyName",
              "jobTitle", "department", "officeLocation", "mobilePhone", "birthday", "createdDateTime",
              "lastModifiedDateTime", "parentFolderId", "emailAddresses", "categories", "businessPhones",
              "homePhones")
ORDERABLE = ("displayName", "givenName", "surname", "fileAs", "companyName", "jobTitle", "createdDateTime",
             "lastModifiedDateTime")


# --- lookup -------------------------------------------------------------------------------------

def _mailbox(account_id):
    return _store.table("mailboxes").get(account_id)


def _context(mailbox, what):
    return f"{GRAPH}/$metadata#users('{quote(mailbox['owner_address'])}')/{what}"


def _contact(contact_id, account_id):
    row = _store.table("contacts").get(contact_id)
    return row if row is not None and row["owner_account_id"] == account_id else None


# --- writes ----------------------------------------------------------------------------------------

def _birthday(value):
    """A stored birthday from a date or a date and time, or a GraphError."""
    text = str(value).strip()
    try:
        day = date.fromisoformat(text[:10])
        if len(text) > 10:
            datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return GraphError(400, "RequestBodyRead", f"Cannot convert the literal '{value}' to the expected type "
                                                  "'Edm.DateTimeOffset'.")
    return f"{day.isoformat()}T00:00:00Z"


def _display_name(fields):
    names = " ".join(fields.get(column) or "" for column in ("given_name", "middle_name", "surname")).split()
    if names:
        return " ".join(names)
    if fields.get("company_name"):
        return fields["company_name"]
    emails = fields.get("email_addresses") or []
    return emails[0]["address"] if emails else ""


def _apply_body(row, body):
    """``row`` with the properties of a contact body applied, or a GraphError."""
    out = dict(row)
    for name, column, kind in PROPERTIES:
        if name not in body:
            continue
        value = body[name]
        if kind in ("list", "emails") and len(value or []) > LIMITS.get(name, 1000):
            return bad_request(f"A contact holds at most {LIMITS[name]} {name}; this request sends "
                               f"{len(value)}.", code="ErrorInvalidProperty")
        if kind == "str":
            out[column] = value or ""
        elif kind == "date":
            out[column] = "" if not value else _birthday(value)
            if isinstance(out[column], GraphError):
                return out[column]
        elif kind == "list":
            out[column] = [str(v) for v in value or []]
        elif kind == "emails":
            emails = []
            for item in value or []:
                address = (item.get("address") or "").strip()
                if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", address):
                    return bad_request(f"Each of emailAddresses needs an address like name@example.com; "
                                       f"'{address}' is not one.", code="ErrorInvalidProperty")
                emails.append({"name": item.get("name") or "", "address": address})
            out[column] = emails
        else:
            out[column] = {k: v for k, v in (value or {}).items() if k in ADDRESS_KEYS and v}
    if "displayName" not in body:
        renamed = any(name in body for name in NAME_PARTS + ("companyName", "emailAddresses"))
        if not row["display_name"] or (renamed and row["display_name"] == _display_name(row)):
            out["display_name"] = _display_name(out)
    out["last_modified"] = _now()
    return out


# --- operations ------------------------------------------------------------------------------------

def list_contacts(account_id, link, filter_text=None, orderby=None, select=None, top=None, skip=None):
    mailbox = _mailbox(account_id)
    if mailbox is None:
        return _no_mailbox()
    predicate = compile_filter(filter_text, FILTERABLE) if filter_text else None
    if isinstance(predicate, GraphError):
        return predicate
    order = compile_orderby(orderby, ORDERABLE) if orderby else [("displayName", False)]
    if isinstance(order, GraphError):
        return order
    names = _selection(select)
    if isinstance(names, GraphError):
        return names
    views = [_contact_view(c) for c in _store.table("contacts").find(lambda c: c["owner_account_id"] == account_id)]
    if predicate is not None:
        views = [v for v in views if predicate(v)]
    views = [_pick(v, names) for v in _ordered(views, order)]
    return _paged(views, top, skip, link, {"$filter": filter_text, "$orderby": orderby, "$select": select,
                                           "$top": top}, _context(mailbox, "contacts"))


def get_contact(contact_id, account_id, select=None):
    mailbox = _mailbox(account_id)
    if mailbox is None:
        return _no_mailbox()
    row = _contact(contact_id, account_id)
    if row is None:
        return _not_found()
    names = _selection(select)
    if isinstance(names, GraphError):
        return names
    return {"@odata.context": _context(mailbox, "contacts/$entity"), **_pick(_contact_view(row), names)}


def create_contact(account_id, body):
    mailbox = _mailbox(account_id)
    if mailbox is None:
        return _no_mailbox()
    now = _now()
    row = {"id": "AAMkAGcnt" + secrets.token_hex(6), "owner_account_id": account_id,
           "parent_folder_id": mailbox["contacts_folder_id"], "created": now, "last_modified": now}
    row = _coerce_contact_row(row)
    row = _apply_body(row, body)
    if isinstance(row, GraphError):
        return row
    _store.table("contacts").upsert(row)
    return {"@odata.context": _context(mailbox, "contacts/$entity"),
            **_contact_view(_store.table("contacts").get(row["id"]))}


def update_contact(contact_id, account_id, body):
    mailbox = _mailbox(account_id)
    if mailbox is None:
        return _no_mailbox()
    row = _contact(contact_id, account_id)
    if row is None:
        return _not_found()
    if body:
        changed = _apply_body(row, body)
        if isinstance(changed, GraphError):
            return changed
        _store.table("contacts").upsert(changed)
    return {"@odata.context": _context(mailbox, "contacts/$entity"),
            **_contact_view(_store.table("contacts").get(contact_id))}


def delete_contact(contact_id, account_id):
    if _mailbox(account_id) is None:
        return _no_mailbox()
    if _contact(contact_id, account_id) is None:
        return _not_found()
    _store.table("contacts").delete(contact_id)
    return None


_store.eager_load()
