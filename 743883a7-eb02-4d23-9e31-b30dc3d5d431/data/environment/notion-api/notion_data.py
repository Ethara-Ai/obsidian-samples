"""Data access module for the Notion mock service.

Serves exactly the operations the connector needs -- search pages and
databases, get a page, create a page, update page properties, query a database
with a filter and sorts, list a block's children, and append blocks to a page
-- in the shape of the Notion API (api.notion.com/v1, Notion-Version
2022-06-28). Every read and write is scoped to the workspace the presented
token's connected account owns: Alex Carter's "Contoso Platform" workspace,
the team the outlook-calendar-api and outlook-contacts-api seeds describe.

Mock simplifications (also stated in api_test_results.md): text rich text
only, no formulas, rollups, comments, files or uploads, a subset of block
types, and everything in the workspace is shared with the integration.
"""

import json
import re
import secrets
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent

sys.path.insert(0, str(DATA_DIR.parent))
import _mock_clock  # noqa: E402
from _mutable_store import get_store, opt_bool, opt_int, read_seed_with_ctx  # noqa: E402
from _connector_auth import ConnectorAuth  # noqa: E402

_API = "notion-api"
_store = get_store(_API)

NOTION_VERSION = "2022-06-28"
MAX_PAGE_SIZE = 100
TEXT_LIMIT = 2000
ANNOTATIONS = {"bold": False, "italic": False, "strikethrough": False, "underline": False, "code": False,
               "color": "default"}
# Block types this mock writes: the keys each one's object takes, and whether it can hold child blocks.
BLOCK_TYPES = {
    "paragraph": (("rich_text", "color"), True),
    "heading_1": (("rich_text", "color", "is_toggleable"), False),
    "heading_2": (("rich_text", "color", "is_toggleable"), False),
    "heading_3": (("rich_text", "color", "is_toggleable"), False),
    "bulleted_list_item": (("rich_text", "color"), True),
    "numbered_list_item": (("rich_text", "color"), True),
    "to_do": (("rich_text", "checked", "color"), True),
    "toggle": (("rich_text", "color"), True),
    "quote": (("rich_text", "color"), True),
    "callout": (("rich_text", "icon", "color"), True),
    "code": (("rich_text", "language", "caption"), False),
    "divider": ((), False),
}
READ_ONLY_TYPES = ("created_time", "last_edited_time", "created_by", "last_edited_by", "formula", "rollup")
FAMILY = {"title": "text", "rich_text": "text", "url": "text", "email": "text", "phone_number": "text",
          "number": "number", "checkbox": "checkbox", "select": "select", "status": "select",
          "multi_select": "multi_select", "date": "date", "created_time": "date", "last_edited_time": "date",
          "people": "people", "relation": "relation"}
CONDITIONS = {
    "text": ("equals", "does_not_equal", "contains", "does_not_contain", "starts_with", "ends_with", "is_empty",
             "is_not_empty"),
    "number": ("equals", "does_not_equal", "greater_than", "less_than", "greater_than_or_equal_to",
               "less_than_or_equal_to", "is_empty", "is_not_empty"),
    "checkbox": ("equals", "does_not_equal"),
    "select": ("equals", "does_not_equal", "is_empty", "is_not_empty"),
    "multi_select": ("contains", "does_not_contain", "is_empty", "is_not_empty"),
    "date": ("equals", "before", "after", "on_or_before", "on_or_after", "is_empty", "is_not_empty", "past_week",
             "past_month", "past_year", "next_week", "next_month", "next_year"),
    "people": ("contains", "does_not_contain", "is_empty", "is_not_empty"),
    "relation": ("contains", "does_not_contain", "is_empty", "is_not_empty"),
}
RELATIVE = {"past_week": -7, "past_month": -30, "past_year": -365, "next_week": 7, "next_month": 30, "next_year": 365}


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _json_cell(value, empty):
    """A JSON-encoded cell (as a CSV overlay carries it) decoded; ``empty`` for a blank one."""
    if isinstance(value, str) and value.strip()[:1] in ("[", "{"):
        try:
            return json.loads(value)
        except ValueError:
            return empty
    if value is None or value == "":
        return empty
    return value


def _coerce_database(r):
    out = _strip_ctx(r)
    out["parent"] = _json_cell(out.get("parent"), {})
    out["properties"] = _json_cell(out.get("properties"), {})
    out["icon"] = _json_cell(out.get("icon"), None) or None
    for key in ("title", "description"):
        out[key] = str(out.get(key) or "")
    out["is_inline"] = opt_bool(out, "is_inline")
    out["archived"] = opt_bool(out, "archived")
    return out


def _coerce_page(r):
    out = _strip_ctx(r)
    out["parent"] = _json_cell(out.get("parent"), {})
    out["properties"] = _json_cell(out.get("properties"), {})
    out["icon"] = _json_cell(out.get("icon"), None) or None
    out["cover"] = _json_cell(out.get("cover"), None) or None
    out["archived"] = opt_bool(out, "archived")
    return out


def _coerce_block(r):
    out = _strip_ctx(r)
    out["parent"] = _json_cell(out.get("parent"), {})
    out["payload"] = _json_cell(out.get("payload"), {})
    out["position"] = opt_int(out, "position", 0)
    out["archived"] = opt_bool(out, "archived")
    return out


_store.register("workspaces", primary_key="account_id",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("workspaces.json", "workspaces")])
_store.register("users", primary_key="id",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("users.json", "users")])
_store.register("databases", primary_key="id",
                initial_loader=lambda: [_coerce_database(r) for r in _load("databases.json", "databases")],
                row_coercer=_coerce_database)
_store.register("pages", primary_key="id",
                initial_loader=lambda: [_coerce_page(r) for r in _load("pages.json", "pages")],
                row_coercer=_coerce_page)
_store.register("blocks", primary_key="id",
                initial_loader=lambda: [_coerce_block(r) for r in _load("blocks.json", "blocks")],
                row_coercer=_coerce_block)

auth = ConnectorAuth(_API, store=_store, data_dir=DATA_DIR)


class NotionError:
    """A Notion error object and the HTTP status it is served with."""

    def __init__(self, status, code, message):
        self.status = status
        self.body = {"object": "error", "status": status, "code": code, "message": message,
                     "request_id": str(uuid.uuid4())}


class _Invalid(Exception):
    """Raised while reading a request body; carries the NotionError to answer with."""

    def __init__(self, message):
        super().__init__(message)
        self.error = NotionError(400, "validation_error", message)


def _show(value):
    return "undefined" if value is _MISSING else json.dumps(value)


_MISSING = object()


def _not_found(kind, object_id):
    return NotionError(404, "object_not_found", f"Could not find {kind} with ID: {object_id}. Make sure the "
                                                "relevant pages and databases are shared with your integration.")


def _now():
    return _mock_clock.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:00.000Z")


def canonical_id(text):
    """A Notion id in its dashed lowercase form, from either form; None when it is not one."""
    raw = str(text or "").replace("-", "").lower()
    if not re.fullmatch(r"[0-9a-f]{32}", raw):
        return None
    return f"{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:]}"


def bad_path_id(name, value):
    return NotionError(400, "validation_error", f"path failed validation: path.{name} should be a valid uuid, "
                                                f"instead was `{json.dumps(value)}`.")


def _short_id():
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    return "".join(secrets.choice(alphabet) for _ in range(4))


# --- lookup -------------------------------------------------------------------------------------

def _workspace(account_id):
    return _store.table("workspaces").get(account_id)


def _user(user_id, account_id):
    row = _store.table("users").get(user_id)
    return row if row is not None and row["account_id"] == account_id else None


def _page(page_id, account_id):
    row = _store.table("pages").get(page_id)
    return row if row is not None and row["account_id"] == account_id else None


def _database(database_id, account_id):
    row = _store.table("databases").get(database_id)
    return row if row is not None and row["account_id"] == account_id else None


def _block(block_id, account_id):
    row = _store.table("blocks").get(block_id)
    return row if row is not None and row["account_id"] == account_id else None


def _parent_id(parent):
    return parent.get(parent.get("type", ""), "") if isinstance(parent, dict) else ""


def _children(parent_id, account_id):
    return sorted(_store.table("blocks").find(lambda b: b["account_id"] == account_id and not b["archived"]
                                              and _parent_id(b["parent"]) == parent_id),
                  key=lambda b: (b["position"], b["id"]))


def _schema(page):
    """The property schema a page's values follow: its database's, or a lone title for any other page."""
    if page["parent"].get("type") == "database_id":
        database = _store.table("databases").get(page["parent"]["database_id"])
        if database is not None:
            return database["properties"]
    return {"title": {"id": "title", "name": "title", "type": "title", "title": {}}}


def _resolve(schema, key):
    """The property a request names, by name or by id; None when the schema has no such property."""
    if key in schema:
        return key, schema[key]
    for name, spec in schema.items():
        if spec.get("id") == key:
            return name, spec
    return None, None


# --- rendering ------------------------------------------------------------------------------

def _rich(text):
    return [] if not text else [{"type": "text", "text": {"content": text, "link": None},
                                 "annotations": dict(ANNOTATIONS), "plain_text": text, "href": None}]


def plain(rich_text):
    return "".join(item.get("plain_text", "") for item in rich_text or [])


def _title_of(page):
    for name, spec in _schema(page).items():
        if spec["type"] == "title":
            return plain(page["properties"].get(name))
    return ""


def _url(title, object_id):
    slug = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-")
    return "https://www.notion.so/" + (slug + "-" if slug else "") + object_id.replace("-", "")


def _user_view(user_id, account_id):
    row = _user(user_id, account_id)
    if row is None:
        return {"object": "user", "id": user_id}
    if row["type"] == "bot":
        return {"object": "user", "id": row["id"], "name": row["name"], "avatar_url": None, "type": "bot", "bot": {}}
    return {"object": "user", "id": row["id"], "name": row["name"], "avatar_url": row.get("avatar_url") or None,
            "type": "person", "person": {"email": row["email"]}}


def _option(spec, name):
    config = spec.get(spec["type"]) or {}
    return next((o for o in config.get("options", []) if o["name"] == name), None)


def _value_view(spec, value, page):
    kind = spec["type"]
    if kind in ("title", "rich_text"):
        return list(value or [])
    if kind in ("select", "status"):
        option = _option(spec, value) if value else None
        return dict(option) if option else None
    if kind == "multi_select":
        return [dict(o) for o in (_option(spec, name) for name in value or []) if o]
    if kind == "people":
        return [_user_view(user_id, page["account_id"]) for user_id in value or []]
    if kind == "relation":
        return [{"id": page_id} for page_id in value or []]
    if kind == "checkbox":
        return bool(value)
    if kind == "created_time":
        return page["created_time"]
    if kind == "last_edited_time":
        return page["last_edited_time"]
    if kind in ("created_by", "last_edited_by"):
        return {"object": "user", "id": page[kind]}
    return value if value not in ("", []) else None


def page_view(page):
    properties = {}
    for name, spec in _schema(page).items():
        properties[name] = {"id": spec["id"], "type": spec["type"],
                            spec["type"]: _value_view(spec, page["properties"].get(name), page)}
        if spec["type"] == "relation":
            properties[name]["has_more"] = False
    return {"object": "page", "id": page["id"], "created_time": page["created_time"],
            "last_edited_time": page["last_edited_time"], "created_by": {"object": "user", "id": page["created_by"]},
            "last_edited_by": {"object": "user", "id": page["last_edited_by"]}, "cover": page["cover"],
            "icon": page["icon"], "parent": page["parent"], "archived": page["archived"], "properties": properties,
            "url": _url(_title_of(page), page["id"]), "public_url": None}


def database_view(database):
    properties = {name: {"id": spec["id"], "name": name, "type": spec["type"], spec["type"]: spec.get(spec["type"], {})}
                  for name, spec in database["properties"].items()}
    return {"object": "database", "id": database["id"], "cover": None, "icon": database["icon"],
            "created_time": database["created_time"], "created_by": {"object": "user", "id": database["created_by"]},
            "last_edited_by": {"object": "user", "id": database["last_edited_by"]},
            "last_edited_time": database["last_edited_time"], "title": _rich(database["title"]),
            "description": _rich(database["description"]), "is_inline": database["is_inline"],
            "properties": properties, "parent": database["parent"], "url": _url("", database["id"]),
            "public_url": None, "archived": database["archived"]}


def block_view(block):
    payload = dict(block["payload"])
    if block["type"] == "child_page":
        page = _store.table("pages").get(block["id"])
        payload = {"title": _title_of(page) if page else ""}
    elif block["type"] == "child_database":
        database = _store.table("databases").get(block["id"])
        payload = {"title": database["title"] if database else ""}
    return {"object": "block", "id": block["id"], "parent": block["parent"], "created_time": block["created_time"],
            "last_edited_time": block["last_edited_time"],
            "created_by": {"object": "user", "id": block["created_by"]},
            "last_edited_by": {"object": "user", "id": block["last_edited_by"]},
            "has_children": bool(_children(block["id"], block["account_id"])), "archived": block["archived"],
            "type": block["type"], block["type"]: payload}


def _listing(results, next_cursor, kind):
    return {"object": "list", "results": results, "next_cursor": next_cursor, "has_more": next_cursor is not None,
            "type": kind, kind: {}}


def _paginate(items, start_cursor, page_size, where):
    """One page of ``items`` (each with an ``id``) from a cursor; the cursor is the id of the first item it starts at."""
    if page_size is not None and not 1 <= page_size <= MAX_PAGE_SIZE:
        bound = "≤ `100`" if page_size > MAX_PAGE_SIZE else "≥ `1`"
        raise _Invalid(f"{where}.page_size should be a number {bound}, instead was `{page_size}`.")
    size, start = page_size or MAX_PAGE_SIZE, 0
    if start_cursor is not None:
        cursor = canonical_id(start_cursor)
        start = next((i for i, item in enumerate(items) if item["id"] == cursor), None)
        if start is None:
            raise _Invalid(f"{where}.start_cursor should be a cursor from an earlier response's next_cursor, "
                           f"instead was `{json.dumps(start_cursor)}`.")
    window = items[start:start + size]
    return window, (items[start + size]["id"] if start + size < len(items) else None)


# --- request bodies: rich text, blocks and property values ------------------------------------------

def _rich_text_input(items, where):
    if not isinstance(items, list):
        raise _Invalid(f"{where} should be an array, instead was `{_show(items)}`.")
    out = []
    for i, item in enumerate(items):
        at = f"{where}[{i}]"
        if not isinstance(item, dict):
            raise _Invalid(f"{at} should be an object, instead was `{_show(item)}`.")
        for key in item:
            if key not in ("type", "text", "annotations", "plain_text", "href"):
                raise _Invalid(f"{at}.{key} should be not present, instead was `{_show(item[key])}`.")
        if item.get("type", "text") != "text" or not isinstance(item.get("text"), dict):
            raise _Invalid(f"{at}.text should be defined, instead was `{_show(item.get('text', _MISSING))}`. This "
                           "mock writes text rich text only; mentions and equations are not supported.")
        text = item["text"]
        for key in text:
            if key not in ("content", "link"):
                raise _Invalid(f"{at}.text.{key} should be not present, instead was `{_show(text[key])}`.")
        content = text.get("content")
        if not isinstance(content, str):
            raise _Invalid(f"{at}.text.content should be a string, instead was `{_show(text.get('content', _MISSING))}`.")
        if len(content) > TEXT_LIMIT:
            raise _Invalid(f"{at}.text.content.length should be ≤ `{TEXT_LIMIT}`, instead was `{len(content)}`.")
        link = text.get("link")
        if link is not None and (not isinstance(link, dict) or set(link) != {"url"} or not isinstance(link["url"], str)):
            raise _Invalid(f"{at}.text.link should be an object with a url, or `null`, instead was `{_show(link)}`.")
        annotations = item.get("annotations") or {}
        if not isinstance(annotations, dict):
            raise _Invalid(f"{at}.annotations should be an object, instead was `{_show(annotations)}`.")
        for key, value in annotations.items():
            if key not in ANNOTATIONS:
                raise _Invalid(f"{at}.annotations.{key} should be not present, instead was `{_show(value)}`.")
            if (key == "color") != isinstance(value, str) or (key != "color" and not isinstance(value, bool)):
                raise _Invalid(f"{at}.annotations.{key} should be a {'string' if key == 'color' else 'boolean'}, "
                               f"instead was `{_show(value)}`.")
        url = link["url"] if link else None
        out.append({"type": "text", "text": {"content": content, "link": {"url": url} if url else None},
                    "annotations": {**ANNOTATIONS, **annotations}, "plain_text": content, "href": url})
    return out


def _block_input(item, where, depth):
    """(type, payload, children) for one block of a request body."""
    if not isinstance(item, dict):
        raise _Invalid(f"{where} should be an object, instead was `{_show(item)}`.")
    kinds = [k for k in item if k not in ("object", "type")]
    if len(kinds) != 1 or (item.get("type") not in (None, kinds[0])) or kinds[0] not in BLOCK_TYPES:
        named = item.get("type") or (kinds[0] if kinds else "")
        raise _Invalid(f"{where} should name one block type this mock writes ({', '.join(BLOCK_TYPES)}), instead "
                       f"was `{named or 'undefined'}`.")
    kind = kinds[0]
    keys, nestable = BLOCK_TYPES[kind]
    body = item[kind]
    if not isinstance(body, dict):
        raise _Invalid(f"{where}.{kind} should be an object, instead was `{_show(body)}`.")
    for key in body:
        if key not in keys and key != "children":
            raise _Invalid(f"{where}.{kind}.{key} should be not present, instead was `{_show(body[key])}`.")
    payload = {}
    if "rich_text" in keys:
        payload["rich_text"] = _rich_text_input(body.get("rich_text", []), f"{where}.{kind}.rich_text")
    if "color" in keys:
        payload["color"] = body.get("color") or ("gray_background" if kind == "callout" else "default")
    if kind.startswith("heading_"):
        payload["is_toggleable"] = bool(body.get("is_toggleable", False))
        nestable = payload["is_toggleable"]
    if kind == "to_do":
        payload["checked"] = bool(body.get("checked", False))
    if kind == "callout":
        payload["icon"] = _icon_input(body.get("icon") or {"type": "emoji", "emoji": "💡"}, f"{where}.callout.icon")
    if kind == "code":
        payload["caption"] = _rich_text_input(body.get("caption", []), f"{where}.code.caption")
        payload["language"] = body.get("language") or "plain text"
    children = body.get("children") or []
    if children and not nestable:
        raise _Invalid(f"{where}.{kind}.children should be not present: a {kind} block cannot hold child blocks.")
    if children and depth >= 2:
        raise _Invalid(f"{where}.{kind}.children should be not present: a request nests blocks two levels deep "
                       "at most.")
    if not isinstance(children, list):
        raise _Invalid(f"{where}.{kind}.children should be an array, instead was `{_show(children)}`.")
    nested = [_block_input(child, f"{where}.{kind}.children[{i}]", depth + 1) for i, child in enumerate(children)]
    return kind, payload, nested


def _blocks_input(children, where):
    if not isinstance(children, list):
        raise _Invalid(f"{where} should be an array, instead was `{_show(children)}`.")
    if len(children) > 100:
        raise _Invalid(f"{where}.length should be ≤ `100`, instead was `{len(children)}`.")
    return [_block_input(child, f"{where}[{i}]", 1) for i, child in enumerate(children)]


def _icon_input(icon, where):
    if icon is None:
        return None
    if not isinstance(icon, dict):
        raise _Invalid(f"{where} should be an object, instead was `{_show(icon)}`.")
    kind = icon.get("type") or ("emoji" if "emoji" in icon else "external")
    if kind == "emoji" and set(icon) <= {"type", "emoji"} and isinstance(icon.get("emoji"), str):
        return {"type": "emoji", "emoji": icon["emoji"]}
    if kind == "external" and set(icon) <= {"type", "external"} and isinstance(icon.get("external"), dict) \
            and set(icon["external"]) == {"url"}:
        return {"type": "external", "external": {"url": str(icon["external"]["url"])}}
    raise _Invalid(f"{where} should be an emoji ({{\"emoji\": ...}}) or an external file ({{\"external\": "
                   f"{{\"url\": ...}}}}), instead was `{_show(icon)}`.")


def _date_input(value, where):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise _Invalid(f"{where} should be an object or `null`, instead was `{_show(value)}`.")
    for key in value:
        if key not in ("start", "end", "time_zone"):
            raise _Invalid(f"{where}.{key} should be not present, instead was `{_show(value[key])}`.")
    start, end = value.get("start"), value.get("end")
    if _moment(start) is None:
        raise _Invalid(f"{where}.start should be an ISO 8601 date or date-time, instead was "
                       f"`{_show(value.get('start', _MISSING))}`.")
    if end is not None and (_moment(end) is None or _moment(end) < _moment(start)):
        raise _Invalid(f"{where}.end should be an ISO 8601 date or date-time no earlier than start, instead was "
                       f"`{_show(end)}`.")
    return {"start": start, "end": end, "time_zone": value.get("time_zone")}


def _option_input(spec, ref, where, create):
    """The option name a select, status or multi_select value names, adding a select option when it is new."""
    if not isinstance(ref, dict) or not set(ref) <= {"id", "name", "color"} or not (ref.get("name") or ref.get("id")):
        raise _Invalid(f"{where} should be an object with a name or an id, instead was `{_show(ref)}`.")
    config = spec.setdefault(spec["type"], {})
    options = config.setdefault("options", [])
    found = next((o for o in options if (ref.get("id") and o["id"] == ref["id"])
                  or (ref.get("name") and o["name"] == ref["name"])), None)
    if found is not None:
        return found["name"]
    if not create or not ref.get("name"):
        raise _Invalid(f"{where} names an option the property does not have: `{_show(ref)}`. A status option must "
                       "already exist.")
    name = str(ref["name"])
    if "," in name or len(name) > 100:
        raise _Invalid(f"{where}.name should be at most 100 characters with no commas, instead was `{_show(name)}`.")
    options.append({"id": _short_id(), "name": name, "color": ref.get("color") or "default"})
    return name


def _property_input(name, spec, value, where, account_id):
    """The stored value for one property of a request body."""
    kind = spec["type"]
    if kind in READ_ONLY_TYPES:
        raise _Invalid(f"{name} is a {kind} property, which is read-only.")
    if kind == "title" and isinstance(value, list):
        value = {"title": value}
    if not isinstance(value, dict) or kind not in value:
        raise _Invalid(f"{name} is expected to be {kind}.")
    for key in value:
        if key not in (kind, "type", "id"):
            raise _Invalid(f"{where}.{key} should be not present, instead was `{_show(value[key])}`.")
    raw, at = value[kind], f"{where}.{kind}"
    if kind in ("title", "rich_text"):
        return _rich_text_input(raw, at)
    if kind == "number":
        if raw is not None and (isinstance(raw, bool) or not isinstance(raw, (int, float))):
            raise _Invalid(f"{at} should be a number or `null`, instead was `{_show(raw)}`.")
        return raw
    if kind == "checkbox":
        if not isinstance(raw, bool):
            raise _Invalid(f"{at} should be a boolean, instead was `{_show(raw)}`.")
        return raw
    if kind in ("url", "email", "phone_number"):
        if raw is not None and not isinstance(raw, str):
            raise _Invalid(f"{at} should be a string or `null`, instead was `{_show(raw)}`.")
        return raw or None
    if kind in ("select", "status"):
        return None if raw is None else _option_input(spec, raw, at, create=kind == "select")
    if kind == "multi_select":
        if not isinstance(raw, list):
            raise _Invalid(f"{at} should be an array, instead was `{_show(raw)}`.")
        return [_option_input(spec, ref, f"{at}[{i}]", create=True) for i, ref in enumerate(raw)]
    if kind == "date":
        return _date_input(raw, at)
    if kind in ("people", "relation"):
        if not isinstance(raw, list):
            raise _Invalid(f"{at} should be an array, instead was `{_show(raw)}`.")
        out = []
        for i, ref in enumerate(raw):
            if not isinstance(ref, dict) or not set(ref) <= {"id", "object"} or canonical_id(ref.get("id")) is None:
                raise _Invalid(f"{at}[{i}] should be an object with a valid id, instead was `{_show(ref)}`.")
            ref_id = canonical_id(ref["id"])
            if kind == "people" and _user(ref_id, account_id) is None:
                raise _Invalid(f"{at}[{i}].id names no user in this workspace: `{ref['id']}`.")
            if kind == "relation":
                target = _page(ref_id, account_id)
                related = (spec.get("relation") or {}).get("database_id")
                if target is None or target["parent"].get("database_id") != related:
                    raise _Invalid(f"{at}[{i}].id names no page in the related database: `{ref['id']}`.")
            out.append(ref_id)
        return out
    raise _Invalid(f"{name} is a {kind} property, which this mock does not write.")


def _properties_input(schema, properties, where, account_id):
    if not isinstance(properties, dict):
        raise _Invalid(f"{where} should be an object, instead was `{_show(properties)}`.")
    values = {}
    for key, value in properties.items():
        name, spec = _resolve(schema, key)
        if spec is None:
            raise _Invalid(f"{key} is not a property that exists.")
        values[name] = _property_input(name, spec, value, f"{where}.{key}", account_id)
    return values


# --- database query: filters and sorts --------------------------------------------------------------

def _moment(text):
    """An aware UTC datetime for a Notion date or date-time string; None when it is neither."""
    if not isinstance(text, str):
        return None
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment.astimezone(timezone.utc) if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _date_test(condition, operand, start):
    if condition in ("is_empty", "is_not_empty"):
        return (start is None) == (condition == "is_empty")
    if start is None:
        return False
    if condition in RELATIVE:
        today = _mock_clock.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        bound = today + timedelta(days=RELATIVE[condition])
        low, high = (bound, today + timedelta(days=1)) if RELATIVE[condition] < 0 else (today, bound + timedelta(days=1))
        return low <= _moment(start) < high
    if len(operand) == 10:
        left, right = _moment(start).date().isoformat() if len(start) > 10 else start[:10], operand
    else:
        left, right = _moment(start), _moment(operand)
    return {"equals": left == right, "before": left < right, "after": left > right, "on_or_before": left <= right,
            "on_or_after": left >= right}[condition]


def _operand(family, condition, operand, at):
    if condition in ("is_empty", "is_not_empty"):
        if operand is not True:
            raise _Invalid(f"{at} should be `true`, instead was `{_show(operand)}`.")
        return operand
    if condition in RELATIVE:
        if operand != {}:
            raise _Invalid(f"{at} should be an empty object, instead was `{_show(operand)}`.")
        return operand
    expected = {"number": ((int, float), "number"), "checkbox": (bool, "boolean")}.get(family, (str, "string"))
    if not isinstance(operand, expected[0]) or (family == "number" and isinstance(operand, bool)):
        raise _Invalid(f"{at} should be a {expected[1]}, instead was `{_show(operand)}`.")
    if family == "date" and _moment(operand) is None:
        raise _Invalid(f"{at} should be an ISO 8601 date or date-time, instead was `{_show(operand)}`.")
    if family in ("people", "relation"):
        if canonical_id(operand) is None:
            raise _Invalid(f"{at} should be a valid uuid, instead was `{_show(operand)}`.")
        return canonical_id(operand)
    return operand


def _condition(node, family, where):
    if not isinstance(node, dict) or len(node) != 1:
        raise _Invalid(f"{where} should be an object with exactly one condition, instead was `{_show(node)}`.")
    condition, operand = next(iter(node.items()))
    if condition not in CONDITIONS[family]:
        raise _Invalid(f"{where}.{condition} should be one of {', '.join(CONDITIONS[family])}.")
    return condition, _operand(family, condition, operand, f"{where}.{condition}")


def _test(name, spec, condition, operand, page):
    kind, family = spec["type"], FAMILY[spec["type"]]
    value = page["properties"].get(name)
    if family == "date":
        start = page[kind] if kind in ("created_time", "last_edited_time") else (value or {}).get("start")
        return _date_test(condition, operand, start)
    if family == "text":
        text = (plain(value) if kind in ("title", "rich_text") else value or "").casefold()
        if condition in ("is_empty", "is_not_empty"):
            return (text == "") == (condition == "is_empty")
        operand = operand.casefold()
        return {"equals": text == operand, "does_not_equal": text != operand, "contains": operand in text,
                "does_not_contain": operand not in text, "starts_with": text.startswith(operand),
                "ends_with": text.endswith(operand)}[condition]
    if condition in ("is_empty", "is_not_empty"):
        return (value in (None, "", [])) == (condition == "is_empty")
    if family == "number":
        if value is None:
            return condition == "does_not_equal"
        return {"equals": value == operand, "does_not_equal": value != operand, "greater_than": value > operand,
                "less_than": value < operand, "greater_than_or_equal_to": value >= operand,
                "less_than_or_equal_to": value <= operand}[condition]
    if family == "checkbox":
        return (bool(value) == operand) == (condition == "equals")
    if family == "select":
        return (value == operand) == (condition == "equals")
    return (operand in (value or [])) == (condition == "contains")


def _compile_filter(node, schema, where, depth=0):
    """A predicate over a database's page rows for a Notion filter object."""
    if not isinstance(node, dict):
        raise _Invalid(f"{where} should be an object, instead was `{_show(node)}`.")
    joins = [k for k in ("and", "or") if k in node]
    if joins:
        if len(node) != 1:
            raise _Invalid(f"{where} should hold `and` or `or` alone.")
        if depth >= 2:
            raise _Invalid(f"{where}.{joins[0]} nests compound filters deeper than two levels.")
        parts = node[joins[0]]
        if not isinstance(parts, list):
            raise _Invalid(f"{where}.{joins[0]} should be an array, instead was `{_show(parts)}`.")
        tests = [_compile_filter(part, schema, f"{where}.{joins[0]}[{i}]", depth + 1) for i, part in enumerate(parts)]
        if joins[0] == "and":
            return lambda page: all(test(page) for test in tests)
        return lambda page: any(test(page) for test in tests)
    if "timestamp" in node:
        stamp = node["timestamp"]
        if stamp not in ("created_time", "last_edited_time") or set(node) != {"timestamp", stamp}:
            raise _Invalid(f"{where} should be a timestamp filter on created_time or last_edited_time, instead was "
                           f"`{_show(node)}`.")
        condition, operand = _condition(node[stamp], "date", f"{where}.{stamp}")
        return lambda page: _date_test(condition, operand, page[stamp])
    if "property" not in node:
        raise _Invalid(f"{where}.property should be defined, instead was `undefined`.")
    name, spec = _resolve(schema, node["property"])
    if spec is None:
        raise _Invalid(f"Could not find property with name or id: {node['property']}")
    keys = [k for k in node if k != "property"]
    accepted = (spec["type"], "rich_text") if spec["type"] == "title" else (spec["type"],)
    if len(keys) != 1 or keys[0] not in accepted:
        raise _Invalid(f"{where} should filter {name} with a `{spec['type']}` condition, instead was "
                       f"`{_show(node)}`.")
    family = FAMILY.get(spec["type"])
    if family is None:
        raise _Invalid(f"{name} is a {spec['type']} property, which this mock does not filter.")
    condition, operand = _condition(node[keys[0]], family, f"{where}.{keys[0]}")
    return lambda page: _test(name, spec, condition, operand, page)


def _sort_key(name, spec, page):
    kind = spec["type"]
    value = page[kind] if kind in ("created_time", "last_edited_time") else page["properties"].get(name)
    if value in (None, "", []):
        return None
    if kind in ("title", "rich_text"):
        return plain(value).casefold()
    if kind in ("select", "status"):
        options = [o["name"] for o in (spec.get(kind) or {}).get("options", [])]
        return options.index(value) if value in options else len(options)
    if kind == "multi_select":
        options = [o["name"] for o in (spec.get(kind) or {}).get("options", [])]
        return [options.index(v) if v in options else len(options) for v in value]
    if kind == "date":
        return _moment(value.get("start"))
    if kind in ("created_time", "last_edited_time"):
        return _moment(value)
    if kind == "people":
        return [(_user(user_id, page["account_id"]) or {}).get("name", "") for user_id in value]
    if kind == "relation":
        return len(value)
    if kind == "checkbox":
        return bool(value)
    return value.casefold() if isinstance(value, str) else value


def _compile_sorts(sorts, schema, where):
    """(key function, descending) pairs, most significant first."""
    if sorts is None:
        return [(lambda page: page["created_time"], True)]
    if not isinstance(sorts, list):
        raise _Invalid(f"{where} should be an array, instead was `{_show(sorts)}`.")
    out = []
    for i, item in enumerate(sorts):
        at = f"{where}[{i}]"
        if not isinstance(item, dict) or not set(item) <= {"property", "timestamp", "direction"} \
                or ("property" in item) == ("timestamp" in item):
            raise _Invalid(f"{at} should be an object with a property or a timestamp, and a direction, instead was "
                           f"`{_show(item)}`.")
        if item.get("direction") not in ("ascending", "descending"):
            raise _Invalid(f"{at}.direction should be `ascending` or `descending`, instead was "
                           f"`{_show(item.get('direction', _MISSING))}`.")
        descending = item["direction"] == "descending"
        if "timestamp" in item:
            if item["timestamp"] not in ("created_time", "last_edited_time"):
                raise _Invalid(f"{at}.timestamp should be `created_time` or `last_edited_time`, instead was "
                               f"`{_show(item['timestamp'])}`.")
            out.append((lambda page, stamp=item["timestamp"]: page[stamp], descending))
            continue
        name, spec = _resolve(schema, item["property"])
        if spec is None:
            raise _Invalid(f"Could not find sort property with name or id: {item['property']}")
        out.append((lambda page, name=name, spec=spec: _sort_key(name, spec, page), descending))
    return out


def _sorted(pages, sorts):
    for key, descending in reversed(sorts):
        present = sorted([p for p in pages if key(p) is not None], key=key, reverse=descending)
        pages = present + [p for p in pages if key(p) is None]
    return pages


# --- operations ------------------------------------------------------------------------------------

def _answer(operation):
    """Run ``operation``, answering a request body it could not read with its validation error."""
    try:
        return operation()
    except _Invalid as exc:
        return exc.error


def search(account_id, body):
    def run():
        if _workspace(account_id) is None:
            return NotionError(401, "unauthorized", "API token is invalid.")
        query = (body.get("query") or "").strip().casefold()
        found = body.get("filter")
        if found is not None and (found.get("property") != "object" or found.get("value") not in ("page", "database")):
            raise _Invalid("body.filter should be {\"property\": \"object\", \"value\": \"page\" or \"database\"}, "
                           f"instead was `{_show(found)}`.")
        order = body.get("sort") or {"direction": "descending", "timestamp": "last_edited_time"}
        if order.get("timestamp") != "last_edited_time" or order.get("direction") not in ("ascending", "descending"):
            raise _Invalid("body.sort should sort by last_edited_time, ascending or descending, instead was "
                           f"`{_show(order)}`.")
        items = []
        if found is None or found["value"] == "page":
            items += [(p, _title_of(p), page_view) for p in _store.table("pages").find(
                lambda p: p["account_id"] == account_id and not p["archived"])]
        if found is None or found["value"] == "database":
            items += [(d, d["title"], database_view) for d in _store.table("databases").find(
                lambda d: d["account_id"] == account_id and not d["archived"])]
        items = [i for i in items if query in i[1].casefold()]
        items.sort(key=lambda i: (i[0]["last_edited_time"], i[0]["id"]),
                   reverse=order["direction"] == "descending")
        window, next_cursor = _paginate([{"id": i[0]["id"], "item": i} for i in items], body.get("start_cursor"),
                                        body.get("page_size"), "body")
        return _listing([w["item"][2](w["item"][0]) for w in window], next_cursor, "page_or_database")
    return _answer(run)


def get_page(page_id, account_id):
    page = _page(page_id, account_id)
    if page is None:
        return _not_found("page", page_id)
    return page_view(page)


def query_database(database_id, account_id, body):
    def run():
        database = _database(database_id, account_id)
        if database is None or database["archived"]:
            return _not_found("database", database_id)
        schema = database["properties"]
        test = _compile_filter(body["filter"], schema, "body.filter") if body.get("filter") is not None else None
        sorts = _compile_sorts(body.get("sorts"), schema, "body.sorts")
        pages = _store.table("pages").find(lambda p: p["account_id"] == account_id and not p["archived"]
                                           and p["parent"].get("database_id") == database_id)
        if test is not None:
            pages = [p for p in pages if test(p)]
        window, next_cursor = _paginate(_sorted(sorted(pages, key=lambda p: p["id"]), sorts),
                                        body.get("start_cursor"), body.get("page_size"), "body")
        return _listing([page_view(p) for p in window], next_cursor, "page_or_database")
    return _answer(run)


def list_children(block_id, account_id, start_cursor=None, page_size=None):
    def run():
        if _page(block_id, account_id) is None and _block(block_id, account_id) is None:
            return _not_found("block", block_id)
        window, next_cursor = _paginate(_children(block_id, account_id), start_cursor, page_size, "query")
        return _listing([block_view(b) for b in window], next_cursor, "block")
    return _answer(run)


def _archived_error():
    return NotionError(400, "validation_error", "Can't edit block that is archived. You must unarchive the block "
                                                "before editing.")


def _insert_blocks(parent, account_id, blocks, after=None):
    """Store ``blocks`` (from _blocks_input) under ``parent`` after the sibling ``after``; the new top-level rows."""
    workspace = _workspace(account_id)
    now, parent_id = _now(), _parent_id(parent)
    siblings = _children(parent_id, account_id)
    at = len(siblings) if after is None else next(i for i, b in enumerate(siblings) if b["id"] == after) + 1
    made = []
    for offset, (kind, payload, nested) in enumerate(blocks):
        row = {"id": str(uuid.uuid4()), "account_id": account_id, "parent": parent, "position": 0, "type": kind,
               "payload": payload, "archived": False, "created_time": now, "created_by": workspace["bot_id"],
               "last_edited_time": now, "last_edited_by": workspace["bot_id"]}
        siblings.insert(at + offset, row)
        made.append(row)
        if nested:
            _insert_blocks({"type": "block_id", "block_id": row["id"]}, account_id, nested)
    for position, sibling in enumerate(siblings):
        if sibling["position"] != position or sibling in made:
            _store.table("blocks").upsert({**sibling, "position": position})
    return [_store.table("blocks").get(row["id"]) for row in made]


def _touch(page_id, account_id):
    page = _page(page_id, account_id)
    if page is not None:
        bot = _workspace(account_id)["bot_id"]
        _store.table("pages").upsert({**page, "last_edited_time": _now(), "last_edited_by": bot})


def _page_of(block, account_id):
    """The page a block sits on, climbing through parent blocks."""
    while block is not None and block["parent"].get("type") == "block_id":
        block = _block(block["parent"]["block_id"], account_id)
    return _parent_id(block["parent"]) if block is not None else None


def append_children(block_id, account_id, body):
    def run():
        page, block = _page(block_id, account_id), _block(block_id, account_id)
        if page is None and block is None:
            return _not_found("block", block_id)
        if (page or block)["archived"]:
            return _archived_error()
        if page is None:
            nestable = BLOCK_TYPES.get(block["type"], ((), False))[1] or block["payload"].get("is_toggleable")
            if not nestable:
                raise _Invalid(f"Block type {block['type']} does not support children.")
        blocks = _blocks_input(body.get("children"), "body.children")
        after = body.get("after")
        if after is not None:
            after = canonical_id(after)
            if after is None or after not in {b["id"] for b in _children(block_id, account_id)}:
                raise _Invalid(f"body.after should be the id of a child of {block_id}, instead was "
                               f"`{_show(body['after'])}`.")
        parent = {"type": "page_id", "page_id": block_id} if page else {"type": "block_id", "block_id": block_id}
        made = _insert_blocks(parent, account_id, blocks, after)
        _touch(block_id if page else _page_of(block, account_id), account_id)
        return _listing([block_view(b) for b in made], None, "block")
    return _answer(run)


def create_page(account_id, body):
    def run():
        workspace = _workspace(account_id)
        if workspace is None:
            return NotionError(401, "unauthorized", "API token is invalid.")
        parent = body["parent"]
        kinds = [k for k in ("database_id", "page_id") if parent.get(k)]
        if len(kinds) != 1 or parent.get("type") not in (None, kinds[0]):
            raise _Invalid("body.parent should name one database_id or page_id; an integration cannot create a "
                           f"page at the top of the workspace. Instead it was `{_show(parent)}`.")
        kind = kinds[0]
        parent_id = canonical_id(parent[kind])
        if kind == "database_id":
            database = _database(parent_id, account_id) if parent_id else None
            if database is None or database["archived"]:
                return _not_found("database", parent[kind])
            schema = json.loads(json.dumps(database["properties"]))
        else:
            container = _page(parent_id, account_id) if parent_id else None
            if container is None:
                return _not_found("page", parent[kind])
            if container["archived"]:
                return _archived_error()
            schema = {"title": {"id": "title", "name": "title", "type": "title", "title": {}}}
        values = _properties_input(schema, body.get("properties") or {}, "body.properties", account_id)
        blocks = _blocks_input(body.get("children") or [], "body.children")
        icon = _icon_input(body.get("icon"), "body.icon")
        cover = body.get("cover")
        if cover is not None:
            cover = _icon_input(cover, "body.cover")
            if cover["type"] != "external":
                raise _Invalid("body.cover should be an external file, instead was an emoji.")
        now = _now()
        page = {"id": str(uuid.uuid4()), "account_id": account_id, "parent": {"type": kind, kind: parent_id},
                "properties": values, "icon": icon, "cover": cover, "archived": False, "created_time": now,
                "created_by": workspace["bot_id"], "last_edited_time": now, "last_edited_by": workspace["bot_id"]}
        if kind == "database_id" and schema != database["properties"]:
            _store.table("databases").upsert({**database, "properties": schema, "last_edited_time": now,
                                              "last_edited_by": workspace["bot_id"]})
        _store.table("pages").upsert(page)
        if kind == "page_id":
            siblings = _children(parent_id, account_id)
            _store.table("blocks").upsert({
                "id": page["id"], "account_id": account_id, "parent": {"type": "page_id", "page_id": parent_id},
                "position": len(siblings), "type": "child_page", "payload": {}, "archived": False,
                "created_time": now, "created_by": workspace["bot_id"], "last_edited_time": now,
                "last_edited_by": workspace["bot_id"]})
            _touch(parent_id, account_id)
        if blocks:
            _insert_blocks({"type": "page_id", "page_id": page["id"]}, account_id, blocks)
        return page_view(_store.table("pages").get(page["id"]))
    return _answer(run)


def update_page(page_id, account_id, body):
    def run():
        page = _page(page_id, account_id)
        if page is None:
            return _not_found("page", page_id)
        edits = [k for k in ("properties", "icon", "cover") if k in body]
        if page["archived"] and edits and body.get("archived") is not False:
            return _archived_error()
        changed = dict(page)
        if "archived" in body and body["archived"] is not None:
            changed["archived"] = bool(body["archived"])
        if "properties" in body:
            database = _store.table("databases").get(page["parent"].get("database_id", "")) \
                if page["parent"].get("type") == "database_id" else None
            schema = json.loads(json.dumps(_schema(page)))
            values = _properties_input(schema, body["properties"] or {}, "body.properties", account_id)
            changed["properties"] = {**page["properties"], **values}
            if database is not None and schema != database["properties"]:
                _store.table("databases").upsert({**database, "properties": schema, "last_edited_time": _now(),
                                                  "last_edited_by": _workspace(account_id)["bot_id"]})
        if "icon" in body:
            changed["icon"] = _icon_input(body["icon"], "body.icon")
        if "cover" in body:
            changed["cover"] = _icon_input(body["cover"], "body.cover")
        changed["last_edited_time"] = _now()
        changed["last_edited_by"] = _workspace(account_id)["bot_id"]
        _store.table("pages").upsert(changed)
        child_block = _store.table("blocks").get(page_id)
        if child_block is not None and child_block["archived"] != changed["archived"]:
            _store.table("blocks").upsert({**child_block, "archived": changed["archived"]})
        return page_view(_store.table("pages").get(page_id))
    return _answer(run)


_store.eager_load()
