"""Data access module for the Google Docs API mock service.

Serves the three Google Docs operations the connector needs -- get a document,
create a document, and batchUpdate -- for the documents one connected account
owns. batchUpdate takes insertText, replaceAllText, deleteContentRange,
updateParagraphStyle, updateTextStyle, createParagraphBullets,
deleteParagraphBullets and insertTable. The seed shares its document ids and
titles with google-drive-api, so a document found through Drive opens here.

A document is stored as ordered body rows: a paragraph (text without its
newline, named style, alignment, indent, list, nesting level and heading ids,
and its character styles as runs) or a table (rows of cells, each a list of
paragraphs).
It is rendered as the Docs API structure: a section break at index 0, then each
element in turn, a table taking one index for its start, one per row and one
per cell, every index counted in UTF-16 code units the way the real API counts
them. Mock simplifications (also stated in api_test_results.md): one tab per
document, no headers, footers, footnotes, inline objects or suggestions, and
only the paragraph and text style fields named below.
"""

import base64
import copy
import re
import secrets
import sys
import uuid
from pathlib import Path

DATA_DIR = Path(__file__).parent

sys.path.insert(0, str(DATA_DIR.parent))
from _mutable_store import get_store, read_seed_with_ctx, strict_int  # noqa: E402
from _connector_auth import ConnectorAuth  # noqa: E402

_API = "google-docs-api"
_store = get_store(_API)

TAB_ID = "t.0"
TAB_TITLE = "Tab 1"
UNTITLED = "Untitled document"
VIEW_MODES = ("DEFAULT_FOR_CURRENT_ACCESS", "SUGGESTIONS_INLINE", "PREVIEW_SUGGESTIONS_ACCEPTED",
              "PREVIEW_WITHOUT_SUGGESTIONS")
NAMED_STYLE_TYPES = ("NORMAL_TEXT", "TITLE", "SUBTITLE", "HEADING_1", "HEADING_2", "HEADING_3",
                     "HEADING_4", "HEADING_5", "HEADING_6")
ALIGNMENTS = ("START", "CENTER", "END", "JUSTIFIED")
PARAGRAPH_STYLE_FIELDS = ("namedStyleType", "alignment")
TEXT_STYLE_FIELDS = ("bold", "italic", "underline", "strikethrough")
BULLET_PRESETS = ("BULLET_DISC_CIRCLE_SQUARE", "BULLET_DIAMONDX_ARROW3D_SQUARE", "BULLET_CHECKBOX",
                  "BULLET_ARROW_DIAMOND_DISC", "BULLET_STAR_CIRCLE_SQUARE", "BULLET_ARROW3D_CIRCLE_SQUARE",
                  "BULLET_LEFTTRIANGLE_DIAMOND_DISC", "BULLET_DIAMONDX_HOLLOWDIAMOND_SQUARE",
                  "BULLET_DIAMOND_CIRCLE_SQUARE", "NUMBERED_DECIMAL_ALPHA_ROMAN",
                  "NUMBERED_DECIMAL_ALPHA_ROMAN_PARENS", "NUMBERED_DECIMAL_NESTED",
                  "NUMBERED_UPPERALPHA_ALPHA_ROMAN", "NUMBERED_UPPERROMAN_UPPERALPHA_DECIMAL",
                  "NUMBERED_ZERODECIMAL_ALPHA_ROMAN")
MAX_TABLE_COLUMNS = 20
# Every field of Google's ParagraphStyle and TextStyle: a request may send any of them, and the
# fields mask decides which are applied (those outside the *_FIELDS above are refused).
PARAGRAPH_STYLE_NAMES = ("headingId", "namedStyleType", "alignment", "lineSpacing", "direction", "spacingMode",
                         "spaceAbove", "spaceBelow", "borderBetween", "borderTop", "borderBottom", "borderLeft",
                         "borderRight", "indentFirstLine", "indentStart", "indentEnd", "tabStops",
                         "keepLinesTogether", "keepWithNext", "avoidWidowAndOrphan", "shading", "pageBreakBefore")
TEXT_STYLE_NAMES = ("bold", "italic", "underline", "strikethrough", "smallCaps", "backgroundColor",
                    "foregroundColor", "fontSize", "weightedFontFamily", "baselineOffset", "link")
STATUS_NAMES = {400: "INVALID_ARGUMENT", 401: "UNAUTHENTICATED", 403: "PERMISSION_DENIED",
                404: "NOT_FOUND", 409: "ABORTED"}


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _coerce_document_row(r):
    out = _strip_ctx(r)
    out["lists"] = dict(out.get("lists") or {})
    return out


def _coerce_paragraph_row(r):
    out = _strip_ctx(r)
    out["position"] = strict_int(out, "position")
    out["list_id"] = out.get("list_id") or ""
    out["heading_id"] = out.get("heading_id") or ""
    return out


_store.register("documents", primary_key="id",
                initial_loader=lambda: [_coerce_document_row(r) for r in _load("documents.json", "documents")],
                row_coercer=_coerce_document_row)
_store.register("paragraphs", primary_key="id",
                initial_loader=lambda: [_coerce_paragraph_row(r) for r in _load("paragraphs.json", "paragraphs")],
                row_coercer=_coerce_paragraph_row)

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


def _forbidden():
    return GoogleError(403, "The caller does not have permission")


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


def _new_doc_id():
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
    return "1" + "".join(secrets.choice(alphabet) for _ in range(33))


def _new_revision():
    return "AL" + base64.urlsafe_b64encode(secrets.token_bytes(48)).decode().rstrip("=")[:58]


def _new_heading_id():
    return "h." + uuid.uuid4().hex[:12]


def _new_list_id():
    return "kix." + "".join(secrets.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(12))


# --- the document model ----------------------------------------------------------------
# A paragraph is a dict with text (no newline), style, alignment, indent ([first line, start] in points
# or empty), list_id, nesting, heading_id and marks: one text style per character of text plus one for
# its newline. A table is {"table": rows},
# each row a list of cells, each cell a list of paragraphs.

def _marks(runs, length):
    """Per-character text styles from stored runs of ``[count, style]``; unstyled where runs say nothing."""
    marks = []
    for count, style in runs or []:
        marks += [dict(style)] * int(count)
    return (marks + [{}] * length)[:length]


def _runs(marks):
    runs = []
    for mark in marks:
        if runs and runs[-1][1] == mark:
            runs[-1][0] += 1
        else:
            runs.append([1, dict(mark)])
    return runs


def _paragraph(row):
    text = row.get("text") or ""
    return {"text": text, "style": row.get("style") or "NORMAL_TEXT", "alignment": row.get("alignment") or "",
            "indent": list(row.get("indent") or []), "list_id": row.get("list_id") or "",
            "nesting": int(row.get("nesting") or 0), "heading_id": row.get("heading_id") or "",
            "marks": _marks(row.get("runs"), len(text) + 1)}


def _element(row):
    if row.get("table"):
        return {"table": [[[_paragraph(p) for p in cell] for cell in cells] for cells in row["table"]]}
    return _paragraph(row)


def _row(element):
    """The stored row of an element; a paragraph without alignment, indent, nesting or character styles
    stores exactly the four columns the seed has."""
    if "table" in element:
        return {"text": "", "style": "", "list_id": "", "heading_id": "",
                "table": [[[_row(p) for p in cell] for cell in cells] for cells in element["table"]]}
    row = {"text": element["text"], "style": element["style"], "list_id": element["list_id"],
           "heading_id": element["heading_id"]}
    if element["alignment"]:
        row["alignment"] = element["alignment"]
    if element["indent"]:
        row["indent"] = list(element["indent"])
    if element["nesting"]:
        row["nesting"] = element["nesting"]
    if any(element["marks"]):
        row["runs"] = _runs(element["marks"])
    return row


def _blank_paragraph():
    return _paragraph({"text": "", "style": "NORMAL_TEXT"})


def _all_paragraphs(elements):
    for element in elements:
        if "table" in element:
            for cells in element["table"]:
                for cell in cells:
                    yield from cell
        else:
            yield element


def _containers(elements):
    """The body and every table cell: each list of paragraphs an edit may rewrite in place."""
    out = [elements]
    for element in elements:
        if "table" in element:
            out += [cell for cells in element["table"] for cell in cells]
    return out


def _layout(elements):
    """(paragraph slots, table slots, end of the body): each paragraph, the body's and the cells', as
    (start, end, its container, its position there), and each table as (start, end, position)."""
    paragraphs, tables, index = [], [], 1
    for k, element in enumerate(elements):
        if "table" not in element:
            end = index + _u16(element["text"]) + 1
            paragraphs.append((index, end, elements, k))
            index = end
            continue
        start = index
        index += 1
        for cells in element["table"]:
            index += 1
            for cell in cells:
                index += 1
                for c, p in enumerate(cell):
                    end = index + _u16(p["text"]) + 1
                    paragraphs.append((index, end, cell, c))
                    index = end
        tables.append((start, index, k))
    return paragraphs, tables, index


def _slot(paragraphs, index):
    return next((slot for slot in paragraphs if slot[0] <= index < slot[1]), None)


# --- rendering ------------------------------------------------------------------------

_DIM = lambda magnitude: {"magnitude": magnitude, "unit": "PT"}  # noqa: E731

DOCUMENT_STYLE = {
    "background": {"color": {}},
    "pageNumberStart": 1,
    "marginTop": _DIM(72), "marginBottom": _DIM(72), "marginRight": _DIM(72), "marginLeft": _DIM(72),
    "pageSize": {"height": _DIM(792), "width": _DIM(612)},
    "marginHeader": _DIM(36), "marginFooter": _DIM(36),
    "useCustomHeaderFooterMargins": True,
    "documentFormat": {"documentMode": "PAGES"},
}

_STYLE_SIZES = {"NORMAL_TEXT": 11, "TITLE": 26, "SUBTITLE": 15, "HEADING_1": 20, "HEADING_2": 16,
                "HEADING_3": 14, "HEADING_4": 12, "HEADING_5": 11, "HEADING_6": 11}

NAMED_STYLES = {"styles": [
    {"namedStyleType": name,
     "textStyle": {"fontSize": _DIM(size), "weightedFontFamily": {"fontFamily": "Arial", "weight": 400},
                   "foregroundColor": {"color": {"rgbColor": {}}}},
     "paragraphStyle": {"namedStyleType": name, "alignment": "START", "lineSpacing": 115,
                        "direction": "LEFT_TO_RIGHT", "spaceAbove": _DIM(20 if name.startswith("HEADING") else 0),
                        "spaceBelow": _DIM(6 if name.startswith("HEADING") else 0)}}
    for name, size in _STYLE_SIZES.items()
]}


def _level_indent(nesting):
    """[first line, start] indent of a list's nesting level, in points."""
    return [18 + 36 * nesting, 36 + 36 * nesting]


def _level(nesting, numbered):
    first, start = _level_indent(nesting)
    level = {"bulletAlignment": "START", "indentFirstLine": _DIM(first), "indentStart": _DIM(start),
             "textStyle": {"underline": False}, "startNumber": 1}
    if numbered:
        level.update({"glyphType": ("DECIMAL", "ALPHA", "ROMAN")[nesting % 3], "glyphFormat": f"%{nesting}."})
    else:
        level.update({"glyphSymbol": ("\u25cf", "\u25cb", "\u25a0")[nesting % 3], "glyphFormat": f"%{nesting}"})
    return level


def _list_properties(kind):
    """A seeded list ("bullet" or "number") has the one level its seed describes; a list
    createParagraphBullets made, named by its preset, has Google's nine."""
    if kind in ("bullet", "number"):
        return {"listProperties": {"nestingLevels": [_level(0, kind == "number")]}}
    return {"listProperties": {"nestingLevels": [_level(n, kind.startswith("NUMBERED")) for n in range(9)]}}


def _paragraph_view(p, index):
    """A paragraph structural element starting at ``index``, one text run per stretch of equal style."""
    text, runs, start, i = p["text"] + "\n", [], index, 0
    while i < len(text):
        j = i + 1
        while j < len(text) and p["marks"][j] == p["marks"][i]:
            j += 1
        end = start + _u16(text[i:j])
        runs.append({"startIndex": start, "endIndex": end,
                     "textRun": {"content": text[i:j], "textStyle": dict(sorted(p["marks"][i].items()))}})
        start, i = end, j
    style = {"namedStyleType": p["style"], "direction": "LEFT_TO_RIGHT"}
    if p["heading_id"]:
        style["headingId"] = p["heading_id"]
    if p["alignment"]:
        style["alignment"] = p["alignment"]
    if p["indent"]:
        style["indentFirstLine"], style["indentStart"] = _DIM(p["indent"][0]), _DIM(p["indent"][1])
    paragraph = {"elements": runs, "paragraphStyle": style}
    if p["list_id"]:
        paragraph["bullet"] = {"listId": p["list_id"], "textStyle": {"underline": False}}
        if p["nesting"]:
            paragraph["bullet"]["nestingLevel"] = p["nesting"]
    return {"startIndex": index, "endIndex": start, "paragraph": paragraph}, start


def _table_view(table, index):
    start, index, rows = index, index + 1, []
    for cells in table["table"]:
        row_start, index, out = index, index + 1, []
        for cell in cells:
            cell_start, index, content = index, index + 1, []
            for p in cell:
                node, index = _paragraph_view(p, index)
                content.append(node)
            out.append({"startIndex": cell_start, "endIndex": index, "content": content,
                        "tableCellStyle": {"rowSpan": 1, "columnSpan": 1}})
        rows.append({"startIndex": row_start, "endIndex": index, "tableCells": out,
                     "tableRowStyle": {"minRowHeight": {"unit": "PT"}}})
    columns = len(table["table"][0])
    return {"startIndex": start, "endIndex": index, "table": {
        "rows": len(rows), "columns": columns, "tableRows": rows,
        "tableStyle": {"tableColumnProperties": [{"widthType": "EVENLY_DISTRIBUTED"} for _ in range(columns)]}}}, index


def _body(elements):
    content = [{"endIndex": 1, "sectionBreak": {"sectionStyle": {
        "columnSeparatorStyle": "NONE", "contentDirection": "LEFT_TO_RIGHT", "sectionType": "CONTINUOUS"}}}]
    index = 1
    for element in elements:
        node, index = (_table_view if "table" in element else _paragraph_view)(element, index)
        content.append(node)
    return {"content": content}


def _document_view(doc, elements, include_tabs=False, view_mode="DEFAULT_FOR_CURRENT_ACCESS"):
    applied = "SUGGESTIONS_INLINE" if view_mode == "DEFAULT_FOR_CURRENT_ACCESS" else view_mode
    used = {p["list_id"] for p in _all_paragraphs(elements) if p["list_id"]}
    lists = {lid: _list_properties(kind) for lid, kind in doc["lists"].items() if lid in used}
    content = {"body": _body(elements), "documentStyle": DOCUMENT_STYLE, "namedStyles": NAMED_STYLES}
    if lists:
        content["lists"] = lists
    if include_tabs:
        return {"title": doc["title"], "revisionId": doc["revision_id"], "suggestionsViewMode": applied,
                "documentId": doc["id"],
                "tabs": [{"tabProperties": {"tabId": TAB_ID, "title": TAB_TITLE, "index": 0},
                          "documentTab": content}]}
    return {"title": doc["title"], **content, "revisionId": doc["revision_id"],
            "suggestionsViewMode": applied, "documentId": doc["id"]}


def _elements(doc_id):
    rows = _store.table("paragraphs").find(lambda p: p["document_id"] == doc_id)
    return [_element(r) for r in sorted(rows, key=lambda p: p["position"])]


def _owned(doc_id, account_id):
    doc = _store.table("documents").get(doc_id)
    if doc is None:
        return _missing()
    if doc.get("owner_account_id") != account_id:
        return _forbidden()
    return doc


# --- fields (partial response) ----------------------------------------------------------

class _MaskError(ValueError):
    pass


def _parse_mask(text):
    text = re.sub(r"\s+", "", text or "")
    pos = 0

    def parse_list():
        nonlocal pos
        tree = {}
        while True:
            names = parse_path()
            sub = True
            if pos < len(text) and text[pos] == "(":
                pos += 1
                sub = parse_list()
                if pos >= len(text) or text[pos] != ")":
                    raise _MaskError(text)
                pos += 1
            node = tree
            for name in names[:-1]:
                child = node.get(name)
                if child is True:
                    break
                node = node.setdefault(name, {})
            else:
                leaf = names[-1]
                if sub is True or node.get(leaf) is True:
                    node[leaf] = True
                else:
                    existing = node.get(leaf) or {}
                    existing.update(sub)
                    node[leaf] = existing
            if pos < len(text) and text[pos] == ",":
                pos += 1
                continue
            return tree

    def parse_path():
        nonlocal pos
        names = []
        while True:
            match = re.match(r"[A-Za-z0-9_*]+", text[pos:])
            if not match:
                raise _MaskError(text)
            names.append(match.group(0))
            pos += len(match.group(0))
            if pos < len(text) and text[pos] in "./":
                pos += 1
                continue
            return names

    if not text:
        raise _MaskError(text)
    tree = parse_list()
    if pos != len(text):
        raise _MaskError(text)
    return tree


def _mask_paths(tree, prefix=""):
    for name, sub in tree.items():
        path = f"{prefix}.{name}" if prefix else name
        yield name, path
        if sub is not True:
            yield from _mask_paths(sub, path)


def _keys(obj, out):
    if isinstance(obj, dict):
        for key, value in obj.items():
            out.add(key)
            _keys(value, out)
    elif isinstance(obj, list):
        for item in obj:
            _keys(item, out)
    return out


_KNOWN = set()


def _known_fields():
    if not _KNOWN:
        sample = [_paragraph({"text": "Title", "style": "TITLE", "alignment": "CENTER"}),
                  _paragraph({"text": "Heading", "style": "HEADING_1", "heading_id": "h.sample"}),
                  _paragraph({"text": "Item", "style": "NORMAL_TEXT", "list_id": "kix.sample", "nesting": 1,
                              "runs": [[1, {name: True for name in TEXT_STYLE_FIELDS}]]}),
                  {"table": [[[_blank_paragraph()]]]}, _blank_paragraph()]
        doc = {"id": "sample", "title": "Sample", "revision_id": "rev", "lists": {"kix.sample": "bullet"}}
        for tabs in (False, True):
            _keys(_document_view(doc, sample, include_tabs=tabs), _KNOWN)
        _KNOWN.update({"replies", "writeControl", "requiredRevisionId", "targetRevisionId", "replaceAllText",
                       "occurrencesChanged", "documentId", "glyphType", "glyphSymbol"})
    return _KNOWN


def parse_fields(mask):
    """The parsed ``fields`` selection, or a GoogleError for a malformed or unknown path."""
    if mask is None:
        return None
    try:
        tree = _parse_mask(mask)
    except _MaskError:
        return _field_error(f"Error expanding 'fields' parameter. Invalid field selection '{mask}'.")
    known = _known_fields()
    for name, path in _mask_paths(tree):
        if name != "*" and name not in known:
            return _field_error(f"Error expanding 'fields' parameter. Cannot find matching fields for path "
                                f"'{path}'.")
    return tree


def _field_error(description):
    error = GoogleError(400, "Request contains an invalid argument.")
    error.body["error"]["details"] = [{"@type": "type.googleapis.com/google.rpc.BadRequest",
                                       "fieldViolations": [{"field": "fields", "description": description}]}]
    return error


def apply_fields(obj, tree):
    if tree is None or tree is True:
        return obj
    if isinstance(obj, list):
        return [apply_fields(item, tree) for item in obj]
    if not isinstance(obj, dict):
        return obj
    out = {}
    wildcard = tree.get("*")
    for key, value in obj.items():
        sub = tree.get(key, wildcard)
        if sub is not None:
            out[key] = apply_fields(value, sub)
    return out


# --- operations -----------------------------------------------------------------------

def get_document(doc_id, account_id, include_tabs=False, view_mode="DEFAULT_FOR_CURRENT_ACCESS"):
    doc = _owned(doc_id, account_id)
    if isinstance(doc, GoogleError):
        return doc
    return _document_view(doc, _elements(doc_id), include_tabs=include_tabs, view_mode=view_mode)


def create_document(account_id, title=None):
    doc = {"id": _new_doc_id(), "owner_account_id": account_id, "title": title or UNTITLED,
           "revision_id": _new_revision(), "lists": {}}
    _store.table("documents").upsert(doc)
    _store.table("paragraphs").upsert({"id": f"{doc['id']}:0", "document_id": doc["id"], "position": 0,
                                       "style": "NORMAL_TEXT", "text": "", "list_id": "", "heading_id": ""})
    return _document_view(doc, _elements(doc["id"]))


def _split(paragraph, text, marks):
    """``paragraph`` carrying ``text`` (``marks`` has one more style, for its newline); every newline in
    it starts a paragraph of the same style."""
    out, at = [], 0
    for n, part in enumerate(text.split("\n")):
        piece = {**paragraph, "text": part, "marks": marks[at:at + len(part) + 1]}
        if n:
            piece["heading_id"] = _new_heading_id() if paragraph["style"].startswith("HEADING") else ""
        out.append(piece)
        at += len(part) + 1
    return out


def _check_location(where, segment_id, tab_id):
    if segment_id:
        return _invalid(f"Invalid {where}: Segment ID '{segment_id}' was not found. This document has no "
                        "headers, footers or footnotes; leave segmentId empty to address the body.")
    if tab_id and tab_id != TAB_ID:
        return _invalid(f"Invalid {where}: The tab with ID '{tab_id}' was not found.")
    return None


def _one_location(req, where):
    if (req.get("location") is None) == (req.get("endOfSegmentLocation") is None):
        return _invalid(f"Invalid {where}: Exactly one of location or endOfSegmentLocation must be set.")
    return None


def _insertion(elements, req, where):
    """(paragraph slot, offset in its text) where insertText or insertTable inserts, or a GoogleError."""
    location, end_of_segment = req.get("location"), req.get("endOfSegmentLocation")
    paragraphs, _tables, end = _layout(elements)
    given = end_of_segment if location is None else location
    problem = _check_location(where, given.get("segmentId"), given.get("tabId"))
    if problem:
        return problem
    if location is None:
        index = end - 1
    else:
        index = location.get("index") or 0
        if index < 1:
            return _invalid(f"Invalid {where}: The insertion index must be inside the bounds of an existing "
                            "paragraph. You can still create new paragraphs by inserting newlines.")
        if index >= end:
            return _invalid(f"Invalid {where}: Index {index} must be less than the end index of the referenced "
                            f"segment, {end}.")
    slot = _slot(paragraphs, index)
    if slot is None:
        return _invalid(f"Invalid {where}: The insertion index must be inside the bounds of an existing "
                        "paragraph. You can still create new paragraphs by inserting newlines.")
    offset = _u16_to_index(slot[2][slot[3]]["text"], index - slot[0])
    if offset is None:
        return _invalid(f"Invalid {where}: The insertion index cannot be within a surrogate pair.")
    return slot, offset


def _insert_text(elements, req, where, lists):
    text = req.get("text") or ""
    problem = _one_location(req, where)
    if problem:
        return problem
    if not text:
        return _invalid(f"Invalid {where}: The text to insert must not be empty.")
    found = _insertion(elements, req, where)
    if isinstance(found, GoogleError):
        return found
    (_start, _end, container, k), offset = found
    p = container[k]
    inherited = p["marks"][offset - 1] if offset else p["marks"][0]
    container[k:k + 1] = _split(p, p["text"][:offset] + text + p["text"][offset:],
                                p["marks"][:offset] + [inherited] * len(text) + p["marks"][offset:])
    return {}


def _replace_all_text(elements, req, where, lists):
    criteria = req.get("containsText") or {}
    needle = criteria.get("text") or ""
    if not needle:
        return _invalid(f"Invalid {where}: containsText.text must not be empty.")
    for tab_id in (req.get("tabsCriteria") or {}).get("tabIds") or []:
        if tab_id != TAB_ID:
            return _invalid(f"Invalid {where}: The tab with ID '{tab_id}' was not found.")
    pattern = re.compile(re.escape(needle), 0 if criteria.get("matchCase") else re.IGNORECASE)
    replacement = req.get("replaceText") or ""
    changed = 0
    for container in _containers(elements):
        rebuilt = []
        for p in container:
            matches = [] if "table" in p else list(pattern.finditer(p["text"]))
            if not matches:
                rebuilt.append(p)
                continue
            text, marks, last = "", [], 0
            for match in matches:
                text += p["text"][last:match.start()] + replacement
                marks += p["marks"][last:match.start()] + [p["marks"][match.start()]] * len(replacement)
                last = match.end()
            changed += len(matches)
            rebuilt.extend(_split(p, text + p["text"][last:], marks + p["marks"][last:]))
        container[:] = rebuilt
    return {"replaceAllText": {"occurrencesChanged": changed} if changed else {}}


def _range(elements, rng, where):
    """(start, end) of a request's range, or a GoogleError for one outside the body or inside a character."""
    if not rng:
        return _invalid(f"Invalid {where}: range must be set.")
    problem = _check_location(where, rng.get("segmentId"), rng.get("tabId"))
    if problem:
        return problem
    start, end = rng.get("startIndex"), rng.get("endIndex")
    if start is None or end is None:
        return _invalid(f"Invalid {where}: The range must set both startIndex and endIndex.")
    paragraphs, _tables, body_end = _layout(elements)
    if start < 1:
        return _invalid(f"Invalid {where}: The range's startIndex must be at least 1; index 0 is the section "
                        "break.")
    if end <= start:
        return _invalid(f"Invalid {where}: The range should not be empty: endIndex must be greater than "
                        "startIndex.")
    if end > body_end:
        return _invalid(f"Invalid {where}: Index {end - 1} must be less than the end index of the referenced "
                        f"segment, {body_end}.")
    for index in (start, end):
        slot = _slot(paragraphs, index)
        if slot and _u16_to_index(slot[2][slot[3]]["text"] + "\n", index - slot[0]) is None:
            return _invalid(f"Invalid {where}: The range cannot start or end inside a surrogate pair.")
    return start, end


def _touched(elements, start, end):
    """The (container, position) of every paragraph, the body's and the cells', the range overlaps."""
    return [(container, k) for s, e, container, k in _layout(elements)[0] if s < end and start < e]


def _offset(slot, index):
    return _u16_to_index(slot[2][slot[3]]["text"] + "\n", index - slot[0])


def _join(container, k1, a, k2, b, where, what):
    """Delete from character ``a`` of ``container[k1]`` (None: from the start of element k1, a table) to
    character ``b`` of ``container[k2]``, ``b`` past its text taking its newline too. The paragraph left
    keeps the properties of the paragraph whose newline remains."""
    if b > len(container[k2]["text"]):
        if k2 + 1 >= len(container):
            return _invalid(f"Invalid {where}: The range cannot include the newline character at the end of the "
                            f"{what}.")
        if "table" in container[k2 + 1]:
            return _invalid(f"Invalid {where}: The range cannot include the newline character before a table "
                            "without deleting the table.")
        k2, b = k2 + 1, 0
    last = container[k2]
    text, marks = last["text"][b:], last["marks"][b:]
    if a is not None:
        text, marks = container[k1]["text"][:a] + text, container[k1]["marks"][:a] + marks
    container[k1:k2 + 1] = [{**last, "text": text, "marks": marks}]
    return {}


def _delete_content_range(elements, req, where, lists):
    found = _range(elements, req.get("range"), where)
    if isinstance(found, GoogleError):
        return found
    start, end = found
    paragraphs, tables, body_end = _layout(elements)
    if end == body_end:
        return _invalid(f"Invalid {where}: The range cannot include the newline character at the end of the "
                        "segment.")
    first, last = _slot(paragraphs, start), _slot(paragraphs, end - 1)
    if first and last and first[2] is last[2] and first[2] is not elements:
        return _join(first[2], first[3], _offset(first, start), last[3], _offset(last, end), where, "table cell")
    head = next((t for t in tables if t[0] <= start < t[1]), None)
    tail = next((t for t in tables if t[0] <= end - 1 < t[1]), None)
    if (head and start != head[0]) or (tail and end != tail[1]):
        return _invalid(f"Invalid {where}: The range cannot cover part of a table: delete text inside one cell, "
                        "or the whole table.")
    k1, a = (head[2], None) if head else (first[3], _offset(first, start))
    k2, b = (tail[2] + 1, 0) if tail else (last[3], _offset(last, end))
    return _join(elements, k1, a, k2, b, where, "segment")


def _style_fields(req, style_key, supported, known, where):
    """The style fields a request's ``fields`` mask selects, ``*`` first when it selects all of them, or
    a GoogleError. Only Google's own field names are accepted, and of those only ``supported`` applied."""
    style = req.get(style_key) or {}
    names = [name.strip().split(".", 1)[0] for name in (req.get("fields") or "").split(",") if name.strip()]
    if not names:
        return _invalid(f"Invalid {where}: fields must name at least one field to update; '*' names them all.")
    if "*" in names:
        unsupported = [name for name in style if name not in supported]
        if unsupported:
            return _invalid(f"Invalid {where}: {style_key}.{unsupported[0]} is not supported by this service; "
                            f"it updates {', '.join(supported)}.")
        return ["*", *supported]
    for name in names:
        if name not in known:
            return _invalid(f"Invalid {where}: '{name}' in fields is not a field of {style_key}.")
        if name not in supported:
            return _invalid(f"Invalid {where}: {style_key}.{name} is not supported by this service; it updates "
                            f"{', '.join(supported)}.")
    return names


def _update_paragraph_style(elements, req, where, lists):
    found = _range(elements, req.get("range"), where)
    if isinstance(found, GoogleError):
        return found
    fields = _style_fields(req, "paragraphStyle", PARAGRAPH_STYLE_FIELDS, PARAGRAPH_STYLE_NAMES, where)
    if isinstance(fields, GoogleError):
        return fields
    style = req.get("paragraphStyle") or {}
    for container, k in _touched(elements, *found):
        p = container[k]
        if "namedStyleType" in fields:
            p["style"] = style.get("namedStyleType") or "NORMAL_TEXT"
            p["heading_id"] = (p["heading_id"] or _new_heading_id()) if p["style"].startswith("HEADING") else ""
        if "alignment" in fields:
            p["alignment"] = "" if style.get("alignment") in (None, "START") else style["alignment"]
        if "*" in fields:
            p["indent"] = []
    return {}


def _update_text_style(elements, req, where, lists):
    found = _range(elements, req.get("range"), where)
    if isinstance(found, GoogleError):
        return found
    fields = _style_fields(req, "textStyle", TEXT_STYLE_FIELDS, TEXT_STYLE_NAMES, where)
    if isinstance(fields, GoogleError):
        return fields
    style, chosen = req.get("textStyle") or {}, [name for name in fields if name != "*"]
    start, end = found
    for s, e, container, k in _layout(elements)[0]:
        if e <= start or s >= end:
            continue
        p, index, marks = container[k], s, []
        for j, ch in enumerate(p["text"] + "\n"):
            mark = p["marks"][j]
            if start <= index < end:
                mark = {name: value for name, value in mark.items() if name not in chosen}
                mark.update({name: True for name in chosen if style.get(name)})
            marks.append(mark)
            index += 2 if ord(ch) > 0xFFFF else 1
        p["marks"] = marks
    return {}


def _create_paragraph_bullets(elements, req, where, lists):
    found = _range(elements, req.get("range"), where)
    if isinstance(found, GoogleError):
        return found
    preset = req.get("bulletPreset")
    if not preset:
        return _invalid(f"Invalid {where}: bulletPreset must be set.")
    touched = _touched(elements, *found)
    if not touched:
        return {}
    container, k = touched[0]
    above = container[k - 1] if k else None
    if above and "table" not in above and above["list_id"] and lists.get(above["list_id"]) == preset:
        list_id = above["list_id"]
    else:
        list_id = _new_list_id()
        lists[list_id] = preset
    for container, k in touched:
        p = container[k]
        tabs = len(p["text"]) - len(p["text"].lstrip("\t"))
        p.update(text=p["text"][tabs:], marks=p["marks"][tabs:], nesting=min(tabs, 8), list_id=list_id,
                 indent=[])
    return {}


def _delete_paragraph_bullets(elements, req, where, lists):
    found = _range(elements, req.get("range"), where)
    if isinstance(found, GoogleError):
        return found
    for container, k in _touched(elements, *found):
        p = container[k]
        if p["list_id"]:
            p.update(list_id="", nesting=0, indent=_level_indent(p["nesting"]))
    return {}


def _insert_table(elements, req, where, lists):
    problem = _one_location(req, where)
    if problem:
        return problem
    rows, columns = req.get("rows") or 0, req.get("columns") or 0
    if rows < 1 or columns < 1:
        return _invalid(f"Invalid {where}: rows and columns must each be at least 1.")
    if columns > MAX_TABLE_COLUMNS:
        return _invalid(f"Invalid {where}: A table can have at most {MAX_TABLE_COLUMNS} columns.")
    found = _insertion(elements, req, where)
    if isinstance(found, GoogleError):
        return found
    (_start, _end, container, k), offset = found
    if container is not elements:
        return _invalid(f"Invalid {where}: This service inserts a table into the body only, not inside a table "
                        "cell.")
    p = elements[k]
    inherited = p["marks"][offset - 1] if offset else p["marks"][0]
    before, after = _split(p, p["text"][:offset] + "\n" + p["text"][offset:],
                           p["marks"][:offset] + [inherited] + p["marks"][offset:])
    elements[k:k + 1] = [before, {"table": [[[_blank_paragraph()] for _ in range(columns)] for _ in range(rows)]},
                         after]
    return {}


REQUESTS = {"insertText": _insert_text, "replaceAllText": _replace_all_text,
            "deleteContentRange": _delete_content_range, "updateParagraphStyle": _update_paragraph_style,
            "updateTextStyle": _update_text_style, "createParagraphBullets": _create_paragraph_bullets,
            "deleteParagraphBullets": _delete_paragraph_bullets, "insertTable": _insert_table}


def batch_update(doc_id, account_id, requests, write_control=None):
    doc = _owned(doc_id, account_id)
    if isinstance(doc, GoogleError):
        return doc
    control = write_control or {}
    required, target = control.get("requiredRevisionId"), control.get("targetRevisionId")
    if required and target:
        return _invalid("Invalid JSON payload received. Oneof field 'control' is already set. "
                        "Cannot set 'targetRevisionId'")
    if required and required != doc["revision_id"]:
        return GoogleError(400, f"The required revision ID '{required}' does not match the latest revision of "
                                "the document. Read the document again and retry against its revisionId.",
                           status_name="FAILED_PRECONDITION")
    if target and target != doc["revision_id"]:
        return GoogleError(400, f"The target revision ID '{target}' is not the latest revision of the document; "
                                "this service applies requests to the latest revision only.",
                           status_name="FAILED_PRECONDITION")
    if not requests:
        return _invalid("Must specify at least one request.")
    before = _elements(doc_id)
    elements, lists = copy.deepcopy(before), dict(doc["lists"])
    replies = []
    for i, req in enumerate(requests):
        kinds = [k for k in REQUESTS if req.get(k) is not None]
        if not kinds:
            return _invalid(f"Invalid requests[{i}]: no request is set. Send one of {', '.join(REQUESTS)}.")
        if len(kinds) > 1:
            return _invalid(f"Invalid JSON payload received. Oneof field 'request' is already set. "
                            f"Cannot set '{kinds[1]}'")
        reply = REQUESTS[kinds[0]](elements, req[kinds[0]], f"requests[{i}].{kinds[0]}", lists)
        if isinstance(reply, GoogleError):
            return reply
        replies.append(reply)
    if elements != before or lists != doc["lists"]:
        table = _store.table("paragraphs")
        table.delete_where(lambda p: p["document_id"] == doc_id)
        for position, element in enumerate(elements):
            table.upsert({"id": f"{doc_id}:{position}", "document_id": doc_id, "position": position,
                          **_row(element)})
        doc = _store.table("documents").patch(doc_id, {"revision_id": _new_revision(), "lists": lists})
    return {"replies": replies, "writeControl": {"requiredRevisionId": doc["revision_id"]}, "documentId": doc_id}


_store.eager_load()
