"""Data access module for the Google Slides API mock service.

Serves exactly the four presentation operations the connector needs -- get a
presentation, create a presentation, get one page, and batchUpdate with
createSlide, insertText and replaceAllText -- in the shape of the Google Slides
API v1 (slides.googleapis.com). Every read and write is scoped to the
presentations the presented token's connected account owns. The seed shares its
presentation ids and titles with google-drive-api, so a deck found through Drive
opens here.

A presentation is one row; each slide is a row in order, and each page element
on a slide (a placeholder or text box with its text, or an image) is a row in
order. Rendering builds the Slides API page structure, with text indexes counted
in UTF-16 code units as the real API counts them. Mock simplifications (also
stated in api_test_results.md): one master with the predefined layouts, no
tables, groups, lines, videos or charts, and text carries no character styling.
"""

import base64
import re
import secrets
import sys
from pathlib import Path

DATA_DIR = Path(__file__).parent

sys.path.insert(0, str(DATA_DIR.parent))
from _mutable_store import get_store, read_seed_with_ctx, strict_int  # noqa: E402
from _connector_auth import ConnectorAuth  # noqa: E402

_API = "google-slides-api"
_store = get_store(_API)

STATUS_NAMES = {400: "INVALID_ARGUMENT", 401: "UNAUTHENTICATED", 403: "PERMISSION_DENIED", 404: "NOT_FOUND"}
EMU = "EMU"
PAGE_WIDTH, PAGE_HEIGHT = 9144000, 5143500
MASTER_ID = "p"
NOTES_MASTER_ID = "n"
# Predefined layouts: (object id, display name, placeholders as (type, x, y, width, height)).
LAYOUTS = {
    "BLANK": ("p1", "Blank", []),
    "CAPTION_ONLY": ("p2", "Caption", [("BODY", 457200, 4114800, 8229600, 685800)]),
    "TITLE": ("p3", "Title slide", [("CENTERED_TITLE", 311700, 744575, 8520600, 2052600),
                                    ("SUBTITLE", 311700, 2834125, 8520600, 792600)]),
    "TITLE_AND_BODY": ("p4", "Title and body", [("TITLE", 311700, 445025, 8520600, 572700),
                                                ("BODY", 311700, 1152475, 8520600, 3416400)]),
    "TITLE_AND_TWO_COLUMNS": ("p5", "Title and two columns", [("TITLE", 311700, 445025, 8520600, 572700),
                                                              ("BODY", 311700, 1152475, 3999900, 3416400),
                                                              ("BODY", 4832400, 1152475, 3999900, 3416400)]),
    "TITLE_ONLY": ("p6", "Title only", [("TITLE", 311700, 445025, 8520600, 572700)]),
    "SECTION_HEADER": ("p7", "Section header", [("TITLE", 311700, 2150850, 8520600, 841800)]),
    "ONE_COLUMN_TEXT": ("p8", "One column text", [("TITLE", 311700, 555600, 3054300, 755700),
                                                  ("BODY", 311700, 1389600, 3054300, 3179400)]),
    "MAIN_POINT": ("p9", "Main point", [("TITLE", 490250, 450150, 7505700, 4236000)]),
    "BIG_NUMBER": ("p10", "Big number", [("TITLE", 311700, 1106125, 8520600, 1963500),
                                         ("BODY", 311700, 3152225, 8520600, 1300800)]),
}
UNSUPPORTED_LAYOUTS = ("SECTION_TITLE_AND_DESCRIPTION",)
_OBJECT_ID = re.compile(r"^[a-zA-Z0-9_][a-zA-Z0-9_\-:]{4,49}$")


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _coerce_slide_row(r):
    out = _strip_ctx(r)
    out["position"] = strict_int(out, "position")
    out["notes"] = out.get("notes") or ""
    return out


def _coerce_element_row(r):
    out = _strip_ctx(r)
    out["position"] = strict_int(out, "position")
    for key in ("x", "y", "width", "height"):
        out[key] = strict_int(out, key)
    for key in ("text", "placeholder", "image_url", "title", "description"):
        out[key] = out.get(key) or ""
    return out


_store.register("presentations", primary_key="id",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("presentations.json", "presentations")])
_store.register("slides", primary_key="id",
                initial_loader=lambda: [_coerce_slide_row(r) for r in _load("slides.json", "slides")],
                row_coercer=_coerce_slide_row)
_store.register("elements", primary_key="id",
                initial_loader=lambda: [_coerce_element_row(r) for r in _load("elements.json", "elements")],
                row_coercer=_coerce_element_row)

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


def _u16(text):
    return len(text.encode("utf-16-le")) // 2


def _u16_to_index(text, offset):
    """The Python index at UTF-16 offset ``offset`` of ``text``; None inside a surrogate pair."""
    count = 0
    for i, ch in enumerate(text):
        if count == offset:
            return i
        count += 2 if ord(ch) > 0xFFFF else 1
        if count > offset:
            return None
    return len(text) if count == offset else None


def _new_presentation_id():
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
    return "1" + "".join(secrets.choice(alphabet) for _ in range(33))


def _new_revision():
    return base64.urlsafe_b64encode(secrets.token_bytes(15)).decode().rstrip("=")


def _new_object_id():
    return "g" + secrets.token_hex(6) + "_0_" + str(secrets.randbelow(90) + 10)


# --- rendering ------------------------------------------------------------------------------

def _dim(value):
    return {"magnitude": value, "unit": EMU}


def _text_view(text):
    """The Slides TextContent of a shape whose text is ``text`` (every paragraph newline-terminated)."""
    if not text:
        return None
    body = text if text.endswith("\n") else text + "\n"
    elements, start = [], 0
    for line in body.split("\n")[:-1]:
        content = line + "\n"
        end = start + _u16(content)
        marker = {"endIndex": end, "paragraphMarker": {"style": {}}}
        run = {"endIndex": end, "textRun": {"content": content, "style": {}}}
        if start:
            marker["startIndex"] = start
            run["startIndex"] = start
        elements.extend([marker, run])
        start = end
    return {"textElements": elements}


def _element_view(e, layout_id):
    view = {"objectId": e["id"], "size": {"width": _dim(e["width"]), "height": _dim(e["height"])},
            "transform": {"scaleX": 1, "scaleY": 1, "translateX": e["x"], "translateY": e["y"], "unit": EMU}}
    if e["title"]:
        view["title"] = e["title"]
    if e["description"]:
        view["description"] = e["description"]
    if e["kind"] == "image":
        view["image"] = {"contentUrl": e["image_url"], "sourceUrl": e["image_url"], "imageProperties": {}}
        return view
    shape = {"shapeType": "TEXT_BOX", "shapeProperties": {}}
    text = _text_view(e["text"])
    if text:
        shape["text"] = text
    if e["placeholder"]:
        kind, _, index = e["placeholder"].partition(":")
        shape["placeholder"] = {"type": kind, **({"index": int(index)} if index and index != "0" else {}),
                                "parentObjectId": f"{layout_id}_{kind.lower()}{index or ''}"}
    view["shape"] = shape
    return view


def _slide_view(slide, revision):
    layout_id = LAYOUTS[slide["layout"]][0]
    elements = sorted(_store.table("elements").find(lambda e: e["slide_id"] == slide["id"]),
                      key=lambda e: e["position"])
    notes_id = f"{slide['id']}:notes"
    view = {"objectId": slide["id"], "pageType": "SLIDE",
            "pageElements": [_element_view(e, layout_id) for e in elements],
            "slideProperties": {"layoutObjectId": layout_id, "masterObjectId": MASTER_ID,
                                "notesPage": _notes_view(slide, notes_id, revision)},
            "pageProperties": {"pageBackgroundFill": {"propertyState": "INHERIT"}}, "revisionId": revision}
    if not view["pageElements"]:
        del view["pageElements"]
    return view


def _notes_view(slide, notes_id, revision):
    shape = {"shapeType": "TEXT_BOX", "placeholder": {"type": "BODY", "index": 1, "parentObjectId": "n:body"}}
    text = _text_view(slide["notes"])
    if text:
        shape["text"] = text
    return {"objectId": notes_id, "pageType": "NOTES", "revisionId": revision,
            "pageElements": [{"objectId": f"{slide['id']}:notes:body", "size": {"width": _dim(6096000),
                                                                                "height": _dim(4572000)},
                              "transform": {"scaleX": 1, "scaleY": 1, "translateX": 381000, "translateY": 4400550,
                                            "unit": EMU}, "shape": shape}],
            "notesProperties": {"speakerNotesObjectId": f"{slide['id']}:notes:body"}}


def _layout_views(revision):
    out = []
    for name, (object_id, display, placeholders) in LAYOUTS.items():
        elements = []
        counts = {}
        for kind, x, y, w, h in placeholders:
            index = counts.get(kind, 0)
            counts[kind] = index + 1
            elements.append({"objectId": f"{object_id}_{kind.lower()}{index or ''}",
                             "size": {"width": _dim(w), "height": _dim(h)},
                             "transform": {"scaleX": 1, "scaleY": 1, "translateX": x, "translateY": y, "unit": EMU},
                             "shape": {"shapeType": "TEXT_BOX",
                                       "placeholder": {"type": kind, **({"index": index} if index else {}),
                                                       "parentObjectId": f"{MASTER_ID}_{kind.lower()}"}}})
        layout = {"objectId": object_id, "pageType": "LAYOUT", "revisionId": revision,
                  "layoutProperties": {"masterObjectId": MASTER_ID, "name": name, "displayName": display}}
        if elements:
            layout["pageElements"] = elements
        out.append(layout)
    return out


def _master_view(revision):
    return {"objectId": MASTER_ID, "pageType": "MASTER", "revisionId": revision,
            "masterProperties": {"displayName": "Simple Light"},
            "pageProperties": {"pageBackgroundFill": {"solidFill": {"color": {"rgbColor": {"red": 1, "green": 1,
                                                                                         "blue": 1}}}}}}


def _slides(presentation_id):
    return sorted(_store.table("slides").find(lambda s: s["presentation_id"] == presentation_id),
                  key=lambda s: s["position"])


def _presentation_view(p):
    revision = p["revision_id"]
    view = {"presentationId": p["id"], "pageSize": {"width": _dim(PAGE_WIDTH), "height": _dim(PAGE_HEIGHT)},
            "title": p["title"], "masters": [_master_view(revision)], "layouts": _layout_views(revision),
            "locale": p.get("locale") or "en", "revisionId": revision,
            "notesMaster": {"objectId": NOTES_MASTER_ID, "pageType": "NOTES_MASTER", "revisionId": revision}}
    slides = [_slide_view(s, revision) for s in _slides(p["id"])]
    if slides:
        view["slides"] = slides
    return view


def _owned(presentation_id, account_id):
    row = _store.table("presentations").get(presentation_id)
    if row is None or row.get("owner_account_id") != account_id:
        return None
    return row


# --- operations ------------------------------------------------------------------------------

def get_presentation(presentation_id, account_id):
    p = _owned(presentation_id, account_id)
    if p is None:
        return _missing()
    return _presentation_view(p)


def get_page(presentation_id, page_id, account_id):
    p = _owned(presentation_id, account_id)
    if p is None:
        return _missing()
    revision = p["revision_id"]
    for slide in _slides(presentation_id):
        if slide["id"] == page_id:
            return _slide_view(slide, revision)
        if f"{slide['id']}:notes" == page_id:
            return _notes_view(slide, page_id, revision)
    for layout in _layout_views(revision):
        if layout["objectId"] == page_id:
            return layout
    if page_id == MASTER_ID:
        return _master_view(revision)
    return _missing()


def create_presentation(account_id, title=None, presentation_id=None):
    if presentation_id is not None:
        if not re.fullmatch(r"[a-zA-Z0-9_-]{10,}", presentation_id):
            return _invalid(f"Invalid presentationId '{presentation_id}'.", field="presentation_id")
        if _store.table("presentations").get(presentation_id) is not None:
            return GoogleError(409, f"A presentation with id '{presentation_id}' already exists.",
                               status_name="ALREADY_EXISTS")
    pid = presentation_id or _new_presentation_id()
    row = {"id": pid, "owner_account_id": account_id, "title": title or "Untitled presentation",
           "revision_id": _new_revision(), "locale": "en"}
    _store.table("presentations").upsert(row)
    slide_id = _new_object_id()
    _store.table("slides").upsert({"id": slide_id, "presentation_id": pid, "position": 0, "layout": "TITLE",
                                   "notes": ""})
    _add_placeholders(pid, slide_id, "TITLE", {})
    return _presentation_view(_store.table("presentations").get(pid))


def _add_placeholders(presentation_id, slide_id, layout, mappings):
    counts = {}
    for position, (kind, x, y, w, h) in enumerate(LAYOUTS[layout][2]):
        index = counts.get(kind, 0)
        counts[kind] = index + 1
        object_id = mappings.get((kind, index)) or f"{slide_id}_{position}"
        _store.table("elements").upsert({"id": object_id, "presentation_id": presentation_id, "slide_id": slide_id,
                                         "position": position, "kind": "shape",
                                         "placeholder": f"{kind}:{index}" if index else kind,
                                         "x": x, "y": y, "width": w, "height": h, "text": "", "image_url": "",
                                         "title": "", "description": ""})


def _taken_ids(presentation_id, pending):
    ids = {s["id"] for s in _store.table("slides").find(lambda s: s["presentation_id"] == presentation_id)}
    ids |= {e["id"] for e in _store.table("elements").find(lambda e: e["presentation_id"] == presentation_id)}
    return ids | pending


def _check_object_id(object_id, where, taken):
    if not _OBJECT_ID.match(object_id):
        return _invalid(f"Invalid {where}: The object ID ({object_id}) should be 5 to 50 characters long, start "
                        "with a letter, digit or underscore, and contain only letters, digits, underscores, "
                        "hyphens and colons.", field=where)
    if object_id in taken:
        return _invalid(f"Invalid {where}: The object ID ({object_id}) should be unique among all pages and page "
                        "elements.", field=where)
    return None


def batch_update(presentation_id, account_id, requests, write_control=None):
    p = _owned(presentation_id, account_id)
    if p is None:
        return _missing()
    control = write_control or {}
    required = control.get("requiredRevisionId")
    if required and required != p["revision_id"]:
        return GoogleError(400, f"The required revision ID '{required}' does not match the latest revision of the "
                                "presentation. Get the presentation again and retry against its revisionId.",
                           status_name="FAILED_PRECONDITION")
    if not requests:
        return _invalid("Must specify at least one request.", field="requests")
    slides = [dict(s) for s in _slides(presentation_id)]
    elements = {e["id"]: dict(e) for e in _store.table("elements").find(
        lambda e: e["presentation_id"] == presentation_id)}
    pending = set()
    replies, changed = [], False
    for i, req in enumerate(requests):
        kinds = [k for k in ("createSlide", "insertText", "replaceAllText") if req.get(k) is not None]
        if not kinds:
            return _invalid(f"Invalid requests[{i}]: no request is set. Send createSlide, insertText or "
                            "replaceAllText.", field=f"requests[{i}]")
        if len(kinds) > 1:
            return _invalid(f"Invalid JSON payload received. Oneof field 'kind' is already set. Cannot set "
                            f"'{kinds[1]}'")
        kind, body, where = kinds[0], req[kinds[0]], f"requests[{i}].{kinds[0]}"
        if kind == "createSlide":
            reference = body.get("slideLayoutReference") or {}
            layout = reference.get("predefinedLayout") or "BLANK"
            if reference.get("layoutId"):
                layout = next((n for n, (oid, _d, _p) in LAYOUTS.items() if oid == reference["layoutId"]), None)
                if layout is None:
                    return _invalid(f"Invalid {where}: The layout ({reference['layoutId']}) does not exist.",
                                    field=f"{where}.slide_layout_reference.layout_id")
            if layout not in LAYOUTS:
                return _invalid(f"Invalid {where}: predefinedLayout {layout} is not available in this "
                                "presentation's master.", field=f"{where}.slide_layout_reference.predefined_layout")
            taken = _taken_ids(presentation_id, pending)
            slide_id = body.get("objectId") or _new_object_id()
            problem = _check_object_id(slide_id, f"{where}.objectId", taken) if body.get("objectId") else None
            if problem:
                return problem
            pending.add(slide_id)
            mappings = {}
            for k, m in enumerate(body.get("placeholderIdMappings") or []):
                ph = m.get("layoutPlaceholder") or {}
                key = (ph.get("type"), ph.get("index") or 0)
                if m.get("layoutPlaceholderObjectId"):
                    key = next(((kd, n) for kd, n in _placeholder_keys(layout)
                                if f"{LAYOUTS[layout][0]}_{kd.lower()}{n or ''}" == m["layoutPlaceholderObjectId"]),
                               (m["layoutPlaceholderObjectId"], 0))
                if key not in {(t, n) for t, n in _placeholder_keys(layout)}:
                    return _invalid(f"Invalid {where}.placeholderIdMappings[{k}]: The layout {layout} has no "
                                    f"{key[0]} placeholder with index {key[1]}.",
                                    field=f"{where}.placeholder_id_mappings[{k}]")
                problem = _check_object_id(m.get("objectId") or "", f"{where}.placeholderIdMappings[{k}].objectId",
                                           taken | pending)
                if problem:
                    return problem
                pending.add(m["objectId"])
                mappings[key] = m["objectId"]
            index = body.get("insertionIndex", len(slides))
            if not 0 <= index <= len(slides):
                return _invalid(f"Invalid {where}: insertionIndex {index} is out of range for a presentation with "
                                f"{len(slides)} slides.", field=f"{where}.insertion_index")
            slides.insert(index, {"id": slide_id, "presentation_id": presentation_id, "layout": layout,
                                  "notes": "", "position": index})
            counts = {}
            for position, (pk, x, y, w, h) in enumerate(LAYOUTS[layout][2]):
                n = counts.get(pk, 0)
                counts[pk] = n + 1
                oid = mappings.get((pk, n)) or f"{slide_id}_{position}"
                pending.add(oid)
                elements[oid] = {"id": oid, "presentation_id": presentation_id, "slide_id": slide_id,
                                 "position": position, "kind": "shape", "placeholder": f"{pk}:{n}" if n else pk,
                                 "x": x, "y": y, "width": w, "height": h, "text": "", "image_url": "", "title": "",
                                 "description": ""}
            replies.append({"createSlide": {"objectId": slide_id}})
            changed = True
        elif kind == "insertText":
            target = elements.get(body.get("objectId") or "")
            notes = None
            if target is None:
                notes = next((s for s in slides if f"{s['id']}:notes:body" == body.get("objectId")), None)
                if notes is None:
                    return _invalid(f"Invalid {where}: The object ({body.get('objectId')}) could not be found.",
                                    field=f"{where}.object_id")
            elif target["kind"] != "shape":
                return _invalid(f"Invalid {where}: The object ({target['id']}) does not allow text editing.",
                                field=f"{where}.object_id")
            if body.get("cellLocation"):
                return _invalid(f"Invalid {where}: cellLocation applies to table cells, and this presentation has "
                                "no tables.", field=f"{where}.cell_location")
            text = body.get("text") or ""
            if not text:
                return _invalid(f"Invalid {where}: The text to insert must not be empty.", field=f"{where}.text")
            stored = notes["notes"] if notes is not None else target["text"]
            length = _u16(stored)
            index = body.get("insertionIndex") or 0
            if not 0 <= index <= length:
                return _invalid(f"Invalid {where}: The insertion index must be within the bounds of an existing "
                                f"text (0 - {length}).", field=f"{where}.insertion_index")
            offset = _u16_to_index(stored, index)
            if offset is None:
                return _invalid(f"Invalid {where}: The insertion index cannot be within a surrogate pair.",
                                field=f"{where}.insertion_index")
            updated = stored[:offset] + text + stored[offset:]
            if notes is not None:
                notes["notes"] = updated
            else:
                target["text"] = updated
            replies.append({})
            changed = True
        else:
            criteria = body.get("containsText") or {}
            needle = criteria.get("text") or ""
            if not needle:
                return _invalid(f"Invalid {where}: containsText.text must not be empty.",
                                field=f"{where}.contains_text.text")
            pages = body.get("pageObjectIds") or []
            slide_ids = {s["id"] for s in slides}
            for page in pages:
                if page not in slide_ids:
                    return _invalid(f"Invalid {where}: The page ({page}) is not a slide of this presentation.",
                                    field=f"{where}.page_object_ids")
            scope = set(pages) or slide_ids
            pattern = re.compile(re.escape(needle), 0 if criteria.get("matchCase") else re.IGNORECASE)
            replacement = body.get("replaceText") or ""
            count = 0
            for e in elements.values():
                if e["slide_id"] in scope and e["kind"] == "shape" and e["text"]:
                    e["text"], n = pattern.subn(lambda _m: replacement, e["text"])
                    count += n
            replies.append({"replaceAllText": {"occurrencesChanged": count}} if count else {"replaceAllText": {}})
            changed = changed or count > 0
    if changed:
        for position, slide in enumerate(slides):
            _store.table("slides").upsert({**slide, "position": position})
        for e in elements.values():
            _store.table("elements").upsert(e)
        p = _store.table("presentations").patch(presentation_id, {"revision_id": _new_revision()})
    return {"presentationId": presentation_id, "replies": replies,
            "writeControl": {"requiredRevisionId": p["revision_id"]}}


def _placeholder_keys(layout):
    counts = {}
    for kind, *_rest in LAYOUTS[layout][2]:
        n = counts.get(kind, 0)
        counts[kind] = n + 1
        yield kind, n


_store.eager_load()
