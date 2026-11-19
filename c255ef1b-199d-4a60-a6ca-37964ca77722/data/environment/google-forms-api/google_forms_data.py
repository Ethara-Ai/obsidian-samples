"""Data access module for the Google Forms API mock service.

Serves exactly the five form operations the connector needs -- get a form,
create a form, batchUpdate to add or change a question, list a form's
responses, and get one response -- in the shape of the Google Forms API v1
(forms.googleapis.com). Every read and write is scoped to the forms the
presented token's connected account owns.

A form is one row (title, description, settings, revision) plus one row per
item in order; a question item carries its question kind (choice, text, scale
or date). Responses are rows whose answers are keyed by question id. Mock
simplifications (also stated in api_test_results.md): items are questions,
page breaks, text blocks or section headers (no grids, images or videos),
batchUpdate serves createItem and updateItem only, and quizzes are not graded.
"""

import base64
import json
import re
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent

sys.path.insert(0, str(DATA_DIR.parent))
import _mock_clock  # noqa: E402
from _mutable_store import get_store, opt_bool, read_seed_with_ctx, strict_int  # noqa: E402
from _connector_auth import ConnectorAuth  # noqa: E402

_API = "google-forms-api"
_store = get_store(_API)

STATUS_NAMES = {400: "INVALID_ARGUMENT", 401: "UNAUTHENTICATED", 403: "PERMISSION_DENIED", 404: "NOT_FOUND"}
CHOICE_TYPES = ("RADIO", "CHECKBOX", "DROP_DOWN")
QUESTION_KINDS = ("choiceQuestion", "textQuestion", "scaleQuestion", "dateQuestion")
ITEM_KINDS = ("questionItem", "pageBreakItem", "textItem")
ITEM_FIELDS = ("title", "description", "questionItem", "pageBreakItem", "textItem")


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _parsed(value, empty):
    if isinstance(value, str) and value.strip()[:1] in ("[", "{"):
        try:
            return json.loads(value)
        except ValueError:
            return empty
    return value if isinstance(value, type(empty)) else empty


def _coerce_form_row(r):
    out = _strip_ctx(r)
    out["is_quiz"] = opt_bool(out, "is_quiz")
    out["description"] = out.get("description") or ""
    out["linked_sheet_id"] = out.get("linked_sheet_id") or ""
    return out


def _coerce_item_row(r):
    out = _strip_ctx(r)
    out["position"] = strict_int(out, "position")
    out["description"] = out.get("description") or ""
    out["required"] = opt_bool(out, "required")
    out["options"] = [str(o) for o in _parsed(out.get("options"), [])]
    out["paragraph"] = opt_bool(out, "paragraph")
    out["shuffle"] = opt_bool(out, "shuffle")
    for key in ("low", "high"):
        out[key] = int(out[key]) if str(out.get(key, "")).strip() not in ("", "None") else None
    for key in ("low_label", "high_label", "question_id", "choice_type", "kind"):
        out[key] = out.get(key) or ""
    out["include_time"] = opt_bool(out, "include_time")
    out["include_year"] = opt_bool(out, "include_year", default=True)
    return out


def _coerce_response_row(r):
    out = _strip_ctx(r)
    out["answers"] = _parsed(out.get("answers"), {})
    out["respondent_email"] = out.get("respondent_email") or ""
    return out


_store.register("forms", primary_key="id",
                initial_loader=lambda: [_coerce_form_row(r) for r in _load("forms.json", "forms")],
                row_coercer=_coerce_form_row)
_store.register("items", primary_key="id",
                initial_loader=lambda: [_coerce_item_row(r) for r in _load("items.json", "items")],
                row_coercer=_coerce_item_row)
_store.register("responses", primary_key="id",
                initial_loader=lambda: [_coerce_response_row(r) for r in _load("responses.json", "responses")],
                row_coercer=_coerce_response_row)

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


def _new_id(n=44):
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
    return "1" + "".join(secrets.choice(alphabet) for _ in range(n - 1))


def _new_hex(n=8):
    return secrets.token_hex(n)[:n]


def _new_revision():
    return "0000" + secrets.token_hex(2)


# --- rendering ------------------------------------------------------------------------------

def _question(item):
    q = {"questionId": item["question_id"]}
    if item["required"]:
        q["required"] = True
    if item["kind"] == "choice":
        choice = {"type": item["choice_type"], "options": [{"value": o} for o in item["options"]]}
        if item["shuffle"]:
            choice["shuffle"] = True
        q["choiceQuestion"] = choice
    elif item["kind"] == "text":
        q["textQuestion"] = {"paragraph": True} if item["paragraph"] else {}
    elif item["kind"] == "scale":
        scale = {"low": item["low"], "high": item["high"]}
        if item["low_label"]:
            scale["lowLabel"] = item["low_label"]
        if item["high_label"]:
            scale["highLabel"] = item["high_label"]
        q["scaleQuestion"] = scale
    elif item["kind"] == "date":
        date = {"includeYear": item["include_year"]}
        if item["include_time"]:
            date["includeTime"] = True
        q["dateQuestion"] = date
    return q


def _item_view(item):
    view = {"itemId": item["id"].split(":", 1)[1]}
    if item["title"]:
        view["title"] = item["title"]
    if item["description"]:
        view["description"] = item["description"]
    if item["kind"] == "page_break":
        view["pageBreakItem"] = {}
    elif item["kind"] == "text_block":
        view["textItem"] = {}
    else:
        view["questionItem"] = {"question": _question(item)}
    return view


def _items(form_id):
    return sorted(_store.table("items").find(lambda i: i["form_id"] == form_id), key=lambda i: i["position"])


def _form_view(form):
    view = {"formId": form["id"],
            "info": {"title": form["title"], "documentTitle": form["document_title"]},
            "settings": {"quizSettings": {"isQuiz": True}} if form["is_quiz"] else {},
            "revisionId": form["revision_id"],
            "responderUri": f"https://docs.google.com/forms/d/e/{form['responder_key']}/viewform"}
    if form["description"]:
        view["info"]["description"] = form["description"]
    items = [_item_view(i) for i in _items(form["id"])]
    if items:
        view["items"] = items
    if form["linked_sheet_id"]:
        view["linkedSheetId"] = form["linked_sheet_id"]
    return view


def _answer_view(question_id, value):
    values = value if isinstance(value, list) else [value]
    return {"questionId": question_id, "textAnswers": {"answers": [{"value": str(v)} for v in values]}}


def _response_view(row):
    view = {"formId": row["form_id"], "responseId": row["id"], "createTime": row["create_time"],
            "lastSubmittedTime": row["last_submitted_time"]}
    if row["respondent_email"]:
        view["respondentEmail"] = row["respondent_email"]
    if row["answers"]:
        view["answers"] = {qid: _answer_view(qid, v) for qid, v in row["answers"].items()}
    return view


# --- lookup -----------------------------------------------------------------------------------

def _owned(form_id, account_id):
    row = _store.table("forms").get(form_id)
    if row is None or row.get("owner_account_id") != account_id:
        return None
    return row


# --- operations ------------------------------------------------------------------------------

def get_form(form_id, account_id):
    form = _owned(form_id, account_id)
    if form is None:
        return _missing()
    return _form_view(form)


def create_form(account_id, info):
    title = (info or {}).get("title") or ""
    if not title.strip():
        return _invalid("info.title is required.", field="info.title")
    form = {"id": _new_id(), "owner_account_id": account_id, "title": title,
            "document_title": (info or {}).get("documentTitle") or title, "description": "", "is_quiz": False,
            "revision_id": _new_revision(), "responder_key": "1FAIpQLS" + _new_id(48)[8:],
            "created_time": _now(), "updated_time": _now(), "linked_sheet_id": ""}
    _store.table("forms").upsert(form)
    return _form_view(_store.table("forms").get(form["id"]))


def _item_columns(item, where):
    """Stored columns for an Item body (camelCase), or a GoogleError naming what is wrong with it."""
    kinds = [k for k in ITEM_KINDS if item.get(k) is not None]
    if len(kinds) != 1:
        return _invalid(f"Invalid {where}: exactly one of questionItem, pageBreakItem or textItem must be set.",
                        field=where)
    out = {"title": item.get("title") or "", "description": item.get("description") or "",
           "required": False, "options": [], "paragraph": False, "shuffle": False, "low": None, "high": None,
           "low_label": "", "high_label": "", "include_time": False, "include_year": True, "choice_type": "",
           "question_id": ""}
    if kinds[0] == "pageBreakItem":
        return {**out, "kind": "page_break"}
    if kinds[0] == "textItem":
        return {**out, "kind": "text_block"}
    question = (item["questionItem"] or {}).get("question") or {}
    qkinds = [k for k in QUESTION_KINDS if question.get(k) is not None]
    if len(qkinds) != 1:
        return _invalid(f"Invalid {where}.questionItem.question: exactly one of choiceQuestion, textQuestion, "
                        "scaleQuestion or dateQuestion must be set.", field=f"{where}.question_item.question")
    out["required"] = bool(question.get("required"))
    out["question_id"] = question.get("questionId") or ""
    if qkinds[0] == "choiceQuestion":
        choice = question["choiceQuestion"]
        if choice.get("type") not in CHOICE_TYPES:
            return _invalid(f"Invalid {where}: choiceQuestion.type must be RADIO, CHECKBOX or DROP_DOWN.",
                            field=f"{where}.question_item.question.choice_question.type")
        options = [o.get("value") or "" for o in choice.get("options") or []]
        if not options or any(not o.strip() for o in options):
            return _invalid(f"Invalid {where}: a choice question needs at least one option, and every option a "
                            "value.", field=f"{where}.question_item.question.choice_question.options")
        if len(set(options)) != len(options):
            return _invalid(f"Invalid {where}: option values must be unique.",
                            field=f"{where}.question_item.question.choice_question.options")
        out.update(kind="choice", choice_type=choice["type"], options=options, shuffle=bool(choice.get("shuffle")))
    elif qkinds[0] == "textQuestion":
        out.update(kind="text", paragraph=bool(question["textQuestion"].get("paragraph")))
    elif qkinds[0] == "scaleQuestion":
        scale = question["scaleQuestion"]
        low, high = scale.get("low"), scale.get("high")
        if low not in (0, 1) or high is None or not 2 <= high <= 10 or high <= low:
            return _invalid(f"Invalid {where}: scaleQuestion.low must be 0 or 1 and scaleQuestion.high 2 to 10.",
                            field=f"{where}.question_item.question.scale_question")
        out.update(kind="scale", low=low, high=high, low_label=scale.get("lowLabel") or "",
                   high_label=scale.get("highLabel") or "")
    else:
        date = question["dateQuestion"]
        out.update(kind="date", include_time=bool(date.get("includeTime")),
                   include_year=date.get("includeYear", True) is not False)
    return out


def _create_item(form, items, req, i):
    where = f"requests[{i}].createItem"
    location = req.get("location") or {}
    if "index" not in location:
        return _invalid(f"Invalid {where}: location.index is required.", field=f"{where}.location.index")
    index = location["index"]
    if not 0 <= index <= len(items):
        return _invalid(f"Invalid {where}: location.index {index} is out of range for a form with {len(items)} "
                        "items.", field=f"{where}.location.index")
    item = req.get("item") or {}
    if item.get("itemId"):
        return _invalid(f"Invalid {where}: item.itemId is assigned by the server.", field=f"{where}.item.item_id")
    cols = _item_columns(item, f"{where}.item")
    if isinstance(cols, GoogleError):
        return cols
    item_id = _new_hex(8)
    if cols["kind"] in ("choice", "text", "scale", "date"):
        cols["question_id"] = cols["question_id"] or _new_hex(8)
        if any(other["question_id"] == cols["question_id"] for other in items):
            return _invalid(f"Invalid {where}: question id {cols['question_id']} is already in use.",
                            field=f"{where}.item.question_item.question.question_id")
    items.insert(index, {"id": f"{form['id']}:{item_id}", "form_id": form["id"], **cols})
    reply = {"itemId": item_id}
    if cols["question_id"]:
        reply["questionId"] = [cols["question_id"]]
    return {"createItem": reply}


def _update_item(items, req, i):
    where = f"requests[{i}].updateItem"
    location = req.get("location") or {}
    if "index" not in location:
        return _invalid(f"Invalid {where}: location.index is required.", field=f"{where}.location.index")
    index = location["index"]
    if not 0 <= index < len(items):
        return _invalid(f"Invalid {where}: location.index {index} is out of range for a form with {len(items)} "
                        "items.", field=f"{where}.location.index")
    mask = [m.strip() for m in (req.get("updateMask") or "").split(",") if m.strip()]
    if not mask:
        return _invalid(f"Invalid {where}: updateMask is required.", field=f"{where}.update_mask")
    current = items[index]
    item = req.get("item") or {}
    if item.get("itemId") and item["itemId"] != current["id"].split(":", 1)[1]:
        return _invalid(f"Invalid {where}: item.itemId does not match the item at location.index {index}.",
                        field=f"{where}.item.item_id")
    merged = dict(current)
    for path in mask:
        if path == "*":
            path = "title,description,questionItem"
        for part in path.split(","):
            top = part.split(".")[0]
            if top not in ITEM_FIELDS:
                return _invalid(f"Invalid {where}: updateMask path {part!r} is not an Item field.",
                                field=f"{where}.update_mask")
            if top in ("title", "description"):
                merged[top] = item.get(top) or ""
            elif top == "questionItem":
                if current["kind"] not in ("choice", "text", "scale", "date"):
                    return _invalid(f"Invalid {where}: the item at location.index {index} is not a question.",
                                    field=f"{where}.item.question_item")
                question = ((item.get("questionItem") or {}).get("question") or {})
                if question.get("questionId") and question["questionId"] != current["question_id"]:
                    return _invalid(f"Invalid {where}: a question's questionId cannot change.",
                                    field=f"{where}.item.question_item.question.question_id")
                cols = _item_columns({"questionItem": item.get("questionItem")}, f"{where}.item")
                if isinstance(cols, GoogleError):
                    return cols
                cols.pop("title")
                cols.pop("description")
                merged.update(cols, question_id=current["question_id"])
            else:
                return _invalid(f"Invalid {where}: {top} cannot be updated by this service.",
                                field=f"{where}.update_mask")
    items[index] = merged
    return {}


def batch_update(form_id, account_id, requests, include_form=False, write_control=None):
    form = _owned(form_id, account_id)
    if form is None:
        return _missing()
    control = write_control or {}
    required, target = control.get("requiredRevisionId"), control.get("targetRevisionId")
    if required and target:
        return _invalid("Invalid JSON payload received. Oneof field 'control' is already set. "
                        "Cannot set 'targetRevisionId'")
    for name, value in (("required", required), ("target", target)):
        if value and value != form["revision_id"]:
            return GoogleError(400, f"The {name} revision ID '{value}' is not the latest revision of the form. "
                                    "Get the form again and retry against its revisionId.",
                               status_name="FAILED_PRECONDITION")
    if not requests:
        return _invalid("Must specify at least one request.", field="requests")
    items = [dict(i) for i in _items(form_id)]
    before = [dict(i) for i in items]
    replies = []
    for i, req in enumerate(requests):
        kinds = [k for k in ("createItem", "updateItem") if req.get(k) is not None]
        if not kinds:
            return _invalid(f"Invalid requests[{i}]: no request is set. Send createItem or updateItem.",
                            field=f"requests[{i}]")
        if len(kinds) > 1:
            return _invalid(f"Invalid JSON payload received. Oneof field 'kind' is already set. "
                            f"Cannot set '{kinds[1]}'")
        reply = (_create_item(form, items, req["createItem"], i) if kinds[0] == "createItem"
                 else _update_item(items, req["updateItem"], i))
        if isinstance(reply, GoogleError):
            return reply
        replies.append(reply)
    if items != before:
        table = _store.table("items")
        table.delete_where(lambda r: r["form_id"] == form_id)
        for position, item in enumerate(items):
            table.upsert({**item, "position": position})
        form = _store.table("forms").patch(form_id, {"revision_id": _new_revision(), "updated_time": _now()})
    out = {"replies": replies, "writeControl": {"requiredRevisionId": form["revision_id"]}}
    if include_form:
        out["form"] = _form_view(form)
    return out


_FILTER = re.compile(r"^\s*timestamp\s*(>=|>)\s*(\S+)\s*$")


def _instant(text):
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else None


def _token(offset):
    return base64.urlsafe_b64encode(f"fr:{offset}".encode()).decode().rstrip("=")


def _offset(token):
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode()
        prefix, _, value = raw.partition(":")
        if prefix != "fr" or not value.isdigit():
            raise ValueError(raw)
        return int(value)
    except (ValueError, UnicodeDecodeError):
        return None


def list_responses(form_id, account_id, filter=None, page_size=5000, page_token=None):
    if _owned(form_id, account_id) is None:
        return _missing()
    rows = sorted(_store.table("responses").find(lambda r: r["form_id"] == form_id),
                  key=lambda r: (r["last_submitted_time"], r["id"]))
    if filter is not None:
        match = _FILTER.match(filter)
        moment = _instant(match.group(2)) if match else None
        if moment is None:
            return _invalid(f"Invalid filter: {filter!r}. Supported filters are 'timestamp > N' and "
                            "'timestamp >= N', where N is an RFC 3339 UTC timestamp such as "
                            "2026-09-01T00:00:00Z.", field="filter")
        strict = match.group(1) == ">"
        rows = [r for r in rows if (_instant(r["last_submitted_time"]) > moment if strict
                                    else _instant(r["last_submitted_time"]) >= moment)]
    if not 0 <= page_size <= 5000:
        return _invalid("pageSize must be between 0 and 5000.", field="page_size")
    size = page_size or 5000
    start = 0
    if page_token:
        start = _offset(page_token)
        if start is None:
            return _invalid("Page token is invalid.", field="page_token")
    window = rows[start:start + size]
    out = {}
    if window:
        out["responses"] = [_response_view(r) for r in window]
    if start + size < len(rows):
        out["nextPageToken"] = _token(start + size)
    return out


def get_response(form_id, response_id, account_id):
    if _owned(form_id, account_id) is None:
        return _missing()
    row = _store.table("responses").get(response_id)
    if row is None or row["form_id"] != form_id:
        return _missing()
    return _response_view(row)


_store.eager_load()
