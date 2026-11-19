"""Data access module for the Google Contacts (People API) mock service.

Serves exactly the six contact operations the connector needs -- list the
connected account's contacts, get one, search them by name, email or phone,
create one, update one, and delete one -- in the shape of the Google People
API v1 (people.googleapis.com). Every read and write is scoped to the contacts
the presented token's connected account owns.

A contact is stored as one row: names, nicknames, email addresses, phone
numbers, organizations, addresses, a birthday, a note (biography), URLs and a
starred flag. Rendering adds the People API's per-field metadata, the
CONTACT source, the etag and the contact-group memberships. Mock
simplifications (also stated in api_test_results.md): only the CONTACT source
exists (no profile or domain data), memberships cover the myContacts and
starred system groups, and sync tokens are not served.
"""

import base64
import hashlib
import json
import re
import secrets
import sys
from datetime import timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent

sys.path.insert(0, str(DATA_DIR.parent))
import _mock_clock  # noqa: E402
from _mutable_store import get_store, opt_bool, read_seed_with_ctx  # noqa: E402
from _connector_auth import ConnectorAuth  # noqa: E402

_API = "google-contacts-api"
_store = get_store(_API)

PERSON_FIELDS = (
    "addresses", "ageRanges", "biographies", "birthdays", "calendarUrls", "clientData", "coverPhotos",
    "emailAddresses", "events", "externalIds", "genders", "imClients", "interests", "locales", "locations",
    "memberships", "metadata", "miscKeywords", "names", "nicknames", "occupations", "organizations",
    "phoneNumbers", "photos", "relations", "sipAddresses", "skills", "urls", "userDefined",
)
UPDATABLE_FIELDS = ("addresses", "biographies", "birthdays", "emailAddresses", "names", "nicknames",
                    "organizations", "phoneNumbers", "urls")
SORT_ORDERS = ("LAST_MODIFIED_ASCENDING", "LAST_MODIFIED_DESCENDING", "FIRST_NAME_ASCENDING",
               "LAST_NAME_ASCENDING")
DOCS = "https://developers.google.com/people/api/rest/v1/people"
STATUS_NAMES = {400: "INVALID_ARGUMENT", 401: "UNAUTHENTICATED", 403: "PERMISSION_DENIED", 404: "NOT_FOUND"}
TYPE_LABELS = {"home": "Home", "work": "Work", "mobile": "Mobile", "other": "Other", "main": "Main",
               "homeFax": "Home Fax", "workFax": "Work Fax", "pager": "Pager", "workMobile": "Work Mobile",
               "homePage": "Home Page", "blog": "Blog", "profile": "Profile", "school": "School"}


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _parsed(value):
    """A JSON-shaped column as data; an overlay CSV cell carries it as JSON text."""
    if isinstance(value, str) and value.strip()[:1] in ("[", "{"):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def _coerce_contact_row(r):
    out = _strip_ctx(r)
    for key in ("emails", "phones", "organizations", "addresses", "urls"):
        value = _parsed(out.get(key))
        out[key] = [dict(v) for v in value if isinstance(v, dict)] if isinstance(value, list) else []
    nicknames = _parsed(out.get("nicknames"))
    out["nicknames"] = [str(n) for n in nicknames] if isinstance(nicknames, list) else []
    for key in ("given_name", "middle_name", "family_name", "honorific_prefix", "biography"):
        out[key] = out.get(key) or ""
    birthday = _parsed(out.get("birthday"))
    out["birthday"] = {k: int(v) for k, v in birthday.items() if k in ("year", "month", "day") and v} \
        if isinstance(birthday, dict) else None
    out["starred"] = opt_bool(out, "starred")
    return out


_store.register("contacts", primary_key="id",
                initial_loader=lambda: [_coerce_contact_row(r) for r in _load("contacts.json", "contacts")],
                row_coercer=_coerce_contact_row)

auth = ConnectorAuth(_API, store=_store, data_dir=DATA_DIR)


class GoogleError:
    """A Google API error envelope (google.rpc.Status) and the HTTP status it is served with."""

    def __init__(self, status, message, status_name=None, field=None):
        self.status = status
        error = {"code": status, "message": message, "status": status_name or STATUS_NAMES.get(status, "UNKNOWN")}
        if field is not None:
            violation = {"field": field, "description": message} if field else {"description": message}
            error["details"] = [{"@type": "type.googleapis.com/google.rpc.BadRequest",
                                 "fieldViolations": [violation]}]
        self.body = {"error": error}


def _invalid(message, field=None):
    return GoogleError(400, message, field=field)


def _missing():
    return GoogleError(404, "Requested entity was not found.")


def _now():
    return _mock_clock.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _etag(row, prefix):
    digest = hashlib.sha256(repr(sorted((k, repr(v)) for k, v in row.items() if k != "etag")).encode()).digest()
    return prefix + base64.b64encode(digest[:18]).decode()


def _source_id(contact_id):
    return format(int(contact_id[1:]), "x")


def _new_contact_id():
    return "c" + str(secrets.randbelow(9 * 10 ** 18) + 10 ** 18)


# --- masks ------------------------------------------------------------------------------

def parse_mask(value, name, method, allowed=PERSON_FIELDS):
    """The field names of a ``personFields``-style mask, or a GoogleError for a missing or unknown path."""
    paths = [p.strip() for p in (value or "").split(",") if p.strip()]
    if not paths:
        label = name if name.endswith("Mask") else f"{name} mask"
        return _invalid(f"{label} is required. Please specify one or more valid paths. Valid paths are "
                        f"documented at {DOCS}/{method}.", field=name)
    for path in paths:
        base = path[len("person."):] if path.startswith("person.") else path
        if base not in allowed:
            return _invalid(f'Invalid {name} mask path: "{path}". Valid paths are documented at {DOCS}/{method}.',
                            field=name)
    return {p[len("person."):] if p.startswith("person.") else p for p in paths}


# --- rendering ------------------------------------------------------------------------------

def _label(kind):
    return TYPE_LABELS.get(kind, kind)


def _canonical_phone(value):
    digits = re.sub(r"\D", "", value or "")
    if (value or "").strip().startswith("+") and 8 <= len(digits) <= 15:
        return "+" + digits
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return None


def display_name(row):
    return " ".join(p for p in (row["honorific_prefix"], row["given_name"], row["middle_name"], row["family_name"])
                    if p)


def _formatted_address(a):
    city_line = ", ".join(p for p in (a.get("city"), " ".join(p for p in (a.get("region"), a.get("postal_code"))
                                                               if p)) if p)
    return "\n".join(p for p in (a.get("street_address"), a.get("extended_address"), city_line,
                                 a.get("country")) if p)


def _render(row, fields):
    sid = _source_id(row["id"])

    def meta(i):
        out = {"source": {"type": "CONTACT", "id": sid}}
        if i == 0:
            out = {"primary": True, "sourcePrimary": True, **out}
        return out

    view = {"resourceName": f"people/{row['id']}", "etag": row["etag"]}
    if "metadata" in fields:
        view["metadata"] = {"sources": [{"type": "CONTACT", "id": sid, "etag": "#" + row["etag"][3:],
                                         "updateTime": row["update_time"]}], "objectType": "PERSON"}
    if "names" in fields and (row["given_name"] or row["family_name"]):
        name = {"metadata": meta(0), "displayName": display_name(row),
                "familyName": row["family_name"], "givenName": row["given_name"],
                "displayNameLastFirst": ", ".join(p for p in (row["family_name"], " ".join(
                    p for p in (row["honorific_prefix"], row["given_name"], row["middle_name"]) if p)) if p),
                "unstructuredName": display_name(row)}
        if row["middle_name"]:
            name["middleName"] = row["middle_name"]
        if row["honorific_prefix"]:
            name["honorificPrefix"] = row["honorific_prefix"]
        view["names"] = [{k: v for k, v in name.items() if v != ""}]
    if "nicknames" in fields and row["nicknames"]:
        view["nicknames"] = [{"metadata": meta(i), "value": n} for i, n in enumerate(row["nicknames"])]
    if "emailAddresses" in fields and row["emails"]:
        view["emailAddresses"] = [
            {"metadata": meta(i), "value": e["value"],
             **({"type": e["type"], "formattedType": _label(e["type"])} if e.get("type") else {})}
            for i, e in enumerate(row["emails"])]
    if "phoneNumbers" in fields and row["phones"]:
        phones = []
        for i, p in enumerate(row["phones"]):
            item = {"metadata": meta(i), "value": p["value"]}
            canonical = _canonical_phone(p["value"])
            if canonical:
                item["canonicalForm"] = canonical
            if p.get("type"):
                item.update(type=p["type"], formattedType=_label(p["type"]))
            phones.append(item)
        view["phoneNumbers"] = phones
    if "organizations" in fields and row["organizations"]:
        view["organizations"] = [
            {"metadata": meta(i), **{k: o[k] for k in ("name", "title", "department") if o.get(k)},
             **({"type": o["type"], "formattedType": _label(o["type"])} if o.get("type") else {})}
            for i, o in enumerate(row["organizations"])]
    if "addresses" in fields and row["addresses"]:
        view["addresses"] = [
            {"metadata": meta(i), "formattedValue": _formatted_address(a),
             **({"type": a["type"], "formattedType": _label(a["type"])} if a.get("type") else {}),
             **{camel: a[snake] for snake, camel in (("street_address", "streetAddress"),
                                                     ("extended_address", "extendedAddress"), ("city", "city"),
                                                     ("region", "region"), ("postal_code", "postalCode"),
                                                     ("country", "country"), ("country_code", "countryCode"))
                if a.get(snake)}}
            for i, a in enumerate(row["addresses"])]
    if "birthdays" in fields and row["birthday"]:
        view["birthdays"] = [{"metadata": meta(0), "date": dict(row["birthday"])}]
    if "biographies" in fields and row["biography"]:
        view["biographies"] = [{"metadata": meta(0), "value": row["biography"], "contentType": "TEXT_PLAIN"}]
    if "urls" in fields and row["urls"]:
        view["urls"] = [{"metadata": meta(i), "value": u["value"],
                         **({"type": u["type"], "formattedType": _label(u["type"])} if u.get("type") else {})}
                        for i, u in enumerate(row["urls"])]
    if "memberships" in fields:
        groups = ["myContacts"] + (["starred"] if row["starred"] else [])
        view["memberships"] = [{"metadata": {"source": {"type": "CONTACT", "id": sid}},
                                "contactGroupMembership": {"contactGroupId": g,
                                                           "contactGroupResourceName": f"contactGroups/{g}"}}
                               for g in groups]
    return view


# --- lookup and paging ------------------------------------------------------------------------

def _contacts(account_id):
    return _store.table("contacts").find(lambda r: r.get("owner_account_id") == account_id)


def _owned(person_id, account_id):
    row = _store.table("contacts").get(person_id)
    if row is None or row.get("owner_account_id") != account_id:
        return None
    return row


def _token(offset):
    return base64.urlsafe_b64encode(f"gc:{offset}".encode()).decode().rstrip("=")


def _offset(token):
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode()
        prefix, _, value = raw.partition(":")
        if prefix != "gc" or not value.isdigit():
            raise ValueError(raw)
        return int(value)
    except (ValueError, UnicodeDecodeError):
        return None


def _sort_key(order):
    if order == "FIRST_NAME_ASCENDING":
        return lambda r: (r["given_name"].casefold() or "~", r["family_name"].casefold(), r["id"])
    if order == "LAST_NAME_ASCENDING":
        return lambda r: (r["family_name"].casefold() or "~", r["given_name"].casefold(), r["id"])
    return lambda r: (r["update_time"], r["id"])


# --- operations ------------------------------------------------------------------------------

def list_connections(account_id, person_fields, page_size=100, page_token=None,
                     sort_order="LAST_MODIFIED_ASCENDING"):
    fields = parse_mask(person_fields, "personFields", "connections/list")
    if isinstance(fields, GoogleError):
        return fields
    if not 1 <= page_size <= 1000:
        return _invalid("pageSize must be between 1 and 1000.", field="page_size")
    start = 0
    if page_token:
        start = _offset(page_token)
        if start is None:
            return _invalid("Page token is invalid.", field="page_token")
    rows = sorted(_contacts(account_id), key=_sort_key(sort_order),
                  reverse=sort_order == "LAST_MODIFIED_DESCENDING")
    window = rows[start:start + page_size]
    out = {}
    if window:
        out["connections"] = [_render(r, fields) for r in window]
    if start + page_size < len(rows):
        out["nextPageToken"] = _token(start + page_size)
    out["totalPeople"] = len(rows)
    out["totalItems"] = len(rows)
    return out


def get_person(person_id, account_id, person_fields):
    fields = parse_mask(person_fields, "personFields", "get")
    if isinstance(fields, GoogleError):
        return fields
    row = _owned(person_id, account_id)
    if row is None:
        return _missing()
    return _render(row, fields)


def _words(text):
    return [w for w in re.split(r"[^0-9a-z@._+'-]+", (text or "").casefold()) if w]


def _name_tokens(row):
    tokens = set()
    for text in (row["given_name"], row["middle_name"], row["family_name"], *row["nicknames"],
                 *(o.get("name", "") for o in row["organizations"])):
        tokens.update(_words(text.replace("-", " ").replace("'", "")))
        tokens.update(_words(text))
    for e in row["emails"]:
        value = e["value"].casefold()
        tokens.add(value)
        tokens.update(w for w in re.split(r"[.@_+-]", value) if w)
    return tokens


def _phone_digits(row):
    forms = set()
    for p in row["phones"]:
        digits = re.sub(r"\D", "", p["value"])
        canonical = _canonical_phone(p["value"])
        forms.add(digits)
        if canonical:
            forms.add(canonical[1:])
            if canonical.startswith("+1"):
                forms.add(canonical[2:])
                forms.add(canonical[-7:])
    return forms


def _matches(row, query):
    stripped = query.strip()
    digits = re.sub(r"\D", "", stripped)
    if digits and len(digits) >= 3 and not re.search(r"[a-z]", stripped.casefold()):
        return any(form.startswith(digits) for form in _phone_digits(row))
    tokens = _name_tokens(row)
    words = _words(stripped)
    return bool(words) and all(any(t.startswith(w) for t in tokens) for w in words)


def search_contacts(account_id, query, read_mask, page_size=10):
    fields = parse_mask(read_mask, "readMask", "searchContacts")
    if isinstance(fields, GoogleError):
        return fields
    if not 0 <= page_size <= 30:
        return _invalid("pageSize must be between 0 and 30.", field="page_size")
    if not query.strip():
        return {}
    hits = sorted((r for r in _contacts(account_id) if _matches(r, query)),
                  key=lambda r: (display_name(r).casefold(), r["id"]))
    hits = hits[:page_size or 10]
    return {"results": [{"person": _render(r, fields)} for r in hits]} if hits else {}


def _clean(value):
    return value.strip() if isinstance(value, str) else ""


def _row_fields(person, fields):
    """The stored columns for every field in ``fields``, taken from a request ``person`` (camelCase)."""
    out = {}
    if "names" in fields:
        names = person.get("names") or []
        if len(names) > 1:
            return _invalid("names is a singleton field for contacts; send at most one name.",
                            field="person.names")
        name = names[0] if names else {}
        given, family = _clean(name.get("givenName")), _clean(name.get("familyName"))
        if not (given or family) and _clean(name.get("unstructuredName") or name.get("displayName")):
            parts = _clean(name.get("unstructuredName") or name.get("displayName")).split()
            given, family = parts[0], " ".join(parts[1:])
        out.update(given_name=given, family_name=family, middle_name=_clean(name.get("middleName")),
                   honorific_prefix=_clean(name.get("honorificPrefix")))
    if "nicknames" in fields:
        out["nicknames"] = [_clean(n.get("value")) for n in person.get("nicknames") or [] if _clean(n.get("value"))]
    if "emailAddresses" in fields:
        emails = []
        for i, e in enumerate(person.get("emailAddresses") or []):
            value = _clean(e.get("value"))
            if not value:
                return _invalid(f"Invalid emailAddresses[{i}]: value must be set.",
                                field=f"person.email_addresses[{i}].value")
            emails.append({"value": value, "type": _clean(e.get("type"))})
        out["emails"] = emails
    if "phoneNumbers" in fields:
        phones = []
        for i, p in enumerate(person.get("phoneNumbers") or []):
            value = _clean(p.get("value"))
            if not value:
                return _invalid(f"Invalid phoneNumbers[{i}]: value must be set.",
                                field=f"person.phone_numbers[{i}].value")
            phones.append({"value": value, "type": _clean(p.get("type"))})
        out["phones"] = phones
    if "organizations" in fields:
        out["organizations"] = [{k: _clean(o.get(k)) for k in ("name", "title", "department", "type")}
                                for o in person.get("organizations") or []]
    if "addresses" in fields:
        addresses = []
        for a in person.get("addresses") or []:
            stored = {snake: _clean(a.get(camel)) for snake, camel in (
                ("street_address", "streetAddress"), ("extended_address", "extendedAddress"), ("city", "city"),
                ("region", "region"), ("postal_code", "postalCode"), ("country", "country"),
                ("country_code", "countryCode"), ("type", "type"))}
            if not any(stored[k] for k in ("street_address", "city", "region", "postal_code", "country")):
                lines = [ln.strip() for ln in _clean(a.get("formattedValue")).splitlines() if ln.strip()]
                stored["street_address"] = ", ".join(lines)
            addresses.append(stored)
        out["addresses"] = addresses
    if "birthdays" in fields:
        birthdays = person.get("birthdays") or []
        if len(birthdays) > 1:
            return _invalid("birthdays is a singleton field for contacts; send at most one birthday.",
                            field="person.birthdays")
        date = (birthdays[0].get("date") or {}) if birthdays else {}
        if birthdays and not (date.get("month") and date.get("day")):
            return _invalid("Invalid birthdays[0]: date.month and date.day must be set.",
                            field="person.birthdays[0].date")
        if date and not (1 <= date["month"] <= 12 and 1 <= date["day"] <= 31):
            return _invalid("Invalid birthdays[0]: date is not a valid calendar date.",
                            field="person.birthdays[0].date")
        out["birthday"] = {k: date[k] for k in ("year", "month", "day") if date.get(k)} if date else None
    if "biographies" in fields:
        bios = person.get("biographies") or []
        if len(bios) > 1:
            return _invalid("biographies is a singleton field for contacts; send at most one biography.",
                            field="person.biographies")
        out["biography"] = _clean(bios[0].get("value")) if bios else ""
    if "urls" in fields:
        out["urls"] = [{"value": _clean(u.get("value")), "type": _clean(u.get("type"))}
                       for u in person.get("urls") or [] if _clean(u.get("value"))]
    return out


def create_contact(account_id, person, person_fields=None):
    fields = parse_mask(person_fields, "personFields", "createContact") if person_fields else set(PERSON_FIELDS)
    if isinstance(fields, GoogleError):
        return fields
    stored = _row_fields(person, UPDATABLE_FIELDS)
    if isinstance(stored, GoogleError):
        return stored
    if not (stored["given_name"] or stored["family_name"] or stored["emails"] or stored["phones"]
            or stored["organizations"]):
        return _invalid("Request person must have a name, an email address, a phone number or an organization.",
                        field="person")
    starred = any(((m.get("contactGroupMembership") or {}).get("contactGroupResourceName") == "contactGroups/starred"
                   or (m.get("contactGroupMembership") or {}).get("contactGroupId") == "starred")
                  for m in person.get("memberships") or [])
    now = _now()
    row = {"id": _new_contact_id(), "owner_account_id": account_id, "created_time": now, "update_time": now,
           "starred": starred, **stored}
    row["etag"] = _etag(row, "%Eh")
    _store.table("contacts").upsert(row)
    return _render(_store.table("contacts").get(row["id"]), fields)


def update_contact(person_id, account_id, person, update_person_fields, person_fields=None):
    mask = parse_mask(update_person_fields, "updatePersonFields", "updateContact", allowed=UPDATABLE_FIELDS)
    if isinstance(mask, GoogleError):
        return mask
    fields = parse_mask(person_fields, "personFields", "updateContact") if person_fields else set(PERSON_FIELDS)
    if isinstance(fields, GoogleError):
        return fields
    row = _owned(person_id, account_id)
    if row is None:
        return _missing()
    sent = person.get("etag") or next((s.get("etag") for s in ((person.get("metadata") or {}).get("sources") or [])
                                       if s.get("etag")), None)
    if not sent:
        return _invalid("Request must set person.etag or person.metadata.sources.etag for the source that is "
                        "being updated.", field="person.etag")
    if sent not in (row["etag"], "#" + row["etag"][3:]):
        return GoogleError(400, "Request person.etag is different than the current person.etag. Get the latest "
                                "person and merge your changes into it.", status_name="FAILED_PRECONDITION")
    changes = _row_fields(person, mask)
    if isinstance(changes, GoogleError):
        return changes
    changed = {**row, **changes, "update_time": _now()}
    changed["etag"] = _etag(changed, "%Eh")
    _store.table("contacts").upsert(changed)
    return _render(_store.table("contacts").get(person_id), fields)


def delete_contact(person_id, account_id):
    if _owned(person_id, account_id) is None:
        return _missing()
    _store.table("contacts").delete(person_id)
    return {}


_store.eager_load()
