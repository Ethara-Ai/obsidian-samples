"""Data access module for the Google Tasks API mock service.

Serves exactly the six task operations the connector needs -- list task lists,
list the tasks in a list, get a task, create a task, update a task (including
marking it complete), and delete a task -- in the shape of the Google Tasks API
v1 (tasks.googleapis.com/tasks/v1). Every read and write is scoped to the task
lists the presented token's connected account owns.

A task list is one row, and each task is a row carrying its list, parent,
ordering position, notes, due date, status and completion time. Deleting a task
marks it deleted, as Google does, so `showDeleted` can still list it. Mock
simplifications (also stated in api_test_results.md): no assigned tasks from
Docs or Chat, no `move`, `clear` or task list writes, and links are not served.
"""

import base64
import hashlib
import json
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent

sys.path.insert(0, str(DATA_DIR.parent))
import _mock_clock  # noqa: E402
from _mutable_store import get_store, opt_bool, read_seed_with_ctx  # noqa: E402
from _connector_auth import ConnectorAuth  # noqa: E402

_API = "google-tasks-api"
_store = get_store(_API)

BASE = "https://www.googleapis.com/tasks/v1"
STATUS_NAMES = {400: "INVALID_ARGUMENT", 401: "UNAUTHENTICATED", 403: "PERMISSION_DENIED", 404: "NOT_FOUND"}
STATUSES = ("needsAction", "completed")
TITLE_LIMIT, NOTES_LIMIT = 1024, 8192


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _coerce_task_row(r):
    out = _strip_ctx(r)
    for key in ("parent", "notes", "due", "completed"):
        out[key] = out.get(key) or ""
    out["deleted"] = opt_bool(out, "deleted")
    out["hidden"] = opt_bool(out, "hidden")
    return out


_store.register("tasklists", primary_key="id",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("tasklists.json", "tasklists")])
_store.register("tasks", primary_key="id",
                initial_loader=lambda: [_coerce_task_row(r) for r in _load("tasks.json", "tasks")],
                row_coercer=_coerce_task_row)

auth = ConnectorAuth(_API, store=_store, data_dir=DATA_DIR)


class GoogleError:
    """A Google API error envelope (google.rpc.Status) and the HTTP status it is served with."""

    def __init__(self, status, message, status_name=None, field=None, reason=None):
        self.status = status
        error = {"code": status, "message": message, "status": status_name or STATUS_NAMES.get(status, "UNKNOWN")}
        if reason:
            error["errors"] = [{"message": message, "domain": "global", "reason": reason}]
        if field is not None:
            violation = {"field": field, "description": message} if field else {"description": message}
            error["details"] = [{"@type": "type.googleapis.com/google.rpc.BadRequest",
                                 "fieldViolations": [violation]}]
        self.body = {"error": error}


def _invalid(message, field=None):
    return GoogleError(400, message, reason="invalid")


def _missing():
    return GoogleError(404, "Requested entity was not found.", reason="notFound")


def _now():
    return _mock_clock.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _new_id():
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
    return "".join(secrets.choice(alphabet) for _ in range(22))


def _etag(row):
    digest = hashlib.md5(json.dumps(row, sort_keys=True, default=str).encode()).hexdigest()
    return f'"{digest[:12]}"'


def _instant(text, name):
    """An RFC 3339 timestamp as an aware datetime, or a GoogleError naming the parameter."""
    try:
        moment = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return _invalid(f"Invalid value for {name}: {text!r} is not an RFC 3339 timestamp.", field=name)
    if moment.tzinfo is None:
        return _invalid(f"Invalid value for {name}: {text!r} needs a time zone offset.", field=name)
    return moment


def _due_value(text):
    """Google stores only the date of a due time and serves it at midnight UTC."""
    moment = _instant(text, "due")
    if isinstance(moment, GoogleError):
        return moment
    return moment.strftime("%Y-%m-%dT00:00:00.000Z")


# --- rendering ------------------------------------------------------------------------------

def _list_view(row):
    view = {"kind": "tasks#taskList", "id": row["id"], "title": row["title"], "updated": row["updated"],
            "selfLink": f"{BASE}/users/@me/lists/{row['id']}"}
    view["etag"] = _etag(view)
    return view


def _task_view(row):
    view = {"kind": "tasks#task", "id": row["id"], "title": row["title"], "updated": row["updated"],
            "selfLink": f"{BASE}/lists/{row['tasklist_id']}/tasks/{row['id']}", "position": row["position"],
            "status": row["status"],
            "webViewLink": f"https://tasks.google.com/task/{row['id']}?sa=6"}
    if row["parent"]:
        view["parent"] = row["parent"]
    if row["notes"]:
        view["notes"] = row["notes"]
    if row["due"]:
        view["due"] = row["due"]
    if row["completed"]:
        view["completed"] = row["completed"]
    if row["deleted"]:
        view["deleted"] = True
    if row["hidden"]:
        view["hidden"] = True
    view["links"] = []
    view["etag"] = _etag(view)
    return view


# --- lookup and paging ------------------------------------------------------------------------

def _lists(account_id):
    return sorted(_store.table("tasklists").find(lambda r: r.get("owner_account_id") == account_id),
                  key=lambda r: r["position"])


def resolve_list(tasklist, account_id):
    if tasklist == "@default":
        lists = _lists(account_id)
        return lists[0] if lists else None
    row = _store.table("tasklists").get(tasklist)
    if row is None or row.get("owner_account_id") != account_id:
        return None
    return row


def _token(offset):
    return base64.urlsafe_b64encode(f"gt:{offset}".encode()).decode().rstrip("=")


def _offset(token):
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode()
        prefix, _, value = raw.partition(":")
        if prefix != "gt" or not value.isdigit():
            raise ValueError(raw)
        return int(value)
    except (ValueError, UnicodeDecodeError):
        return None


def _page(views, kind, max_results, page_token, limit):
    if not 1 <= max_results <= limit:
        return _invalid(f"Invalid value for maxResults: it must be between 1 and {limit}.", field="maxResults")
    start = 0
    if page_token:
        start = _offset(page_token)
        if start is None:
            return _invalid("Invalid value for pageToken.", field="pageToken")
    window = views[start:start + max_results]
    out = {"kind": kind}
    out["etag"] = _etag({"kind": kind, "items": window})
    if start + max_results < len(views):
        out["nextPageToken"] = _token(start + max_results)
    if window:
        out["items"] = window
    return out


# --- operations ------------------------------------------------------------------------------

def list_tasklists(account_id, max_results=1000, page_token=None):
    return _page([_list_view(r) for r in _lists(account_id)], "tasks#taskLists", max_results, page_token, 1000)


def _tasks(tasklist_id):
    return _store.table("tasks").find(lambda t: t["tasklist_id"] == tasklist_id)


def _ordered(rows):
    """Tasks in the order the Tasks UI shows them: each top-level task followed by its subtasks."""
    tops = sorted((t for t in rows if not t["parent"]), key=lambda t: t["position"])
    children = {}
    for t in rows:
        if t["parent"]:
            children.setdefault(t["parent"], []).append(t)
    out = []
    for top in tops:
        out.append(top)
        out.extend(sorted(children.get(top["id"], []), key=lambda t: t["position"]))
    known = {t["id"] for t in out}
    out.extend(sorted((t for t in rows if t["id"] not in known), key=lambda t: t["position"]))
    return out


def list_tasks(tasklist, account_id, max_results=20, page_token=None, show_completed=True, show_deleted=False,
               show_hidden=False, completed_min=None, completed_max=None, due_min=None, due_max=None,
               updated_min=None):
    lst = resolve_list(tasklist, account_id)
    if lst is None:
        return _missing()
    bounds = {}
    for name, value in (("completedMin", completed_min), ("completedMax", completed_max), ("dueMin", due_min),
                        ("dueMax", due_max), ("updatedMin", updated_min)):
        if value is not None:
            moment = _instant(value, name)
            if isinstance(moment, GoogleError):
                return moment
            bounds[name] = moment
    rows = []
    for t in _ordered(_tasks(lst["id"])):
        if t["deleted"] and not show_deleted:
            continue
        if t["hidden"] and not show_hidden:
            continue
        if t["status"] == "completed" and not show_completed:
            continue
        if ("completedMin" in bounds or "completedMax" in bounds) and not t["completed"]:
            continue
        if "completedMin" in bounds and _instant(t["completed"], "completed") < bounds["completedMin"]:
            continue
        if "completedMax" in bounds and _instant(t["completed"], "completed") >= bounds["completedMax"]:
            continue
        if ("dueMin" in bounds or "dueMax" in bounds) and not t["due"]:
            continue
        if "dueMin" in bounds and _instant(t["due"], "due") < bounds["dueMin"]:
            continue
        if "dueMax" in bounds and _instant(t["due"], "due") >= bounds["dueMax"]:
            continue
        if "updatedMin" in bounds and _instant(t["updated"], "updated") < bounds["updatedMin"]:
            continue
        rows.append(_task_view(t))
    return _page(rows, "tasks#tasks", max_results, page_token, 100)


def get_task(tasklist, task_id, account_id):
    lst = resolve_list(tasklist, account_id)
    if lst is None:
        return _missing()
    row = _store.table("tasks").get(task_id)
    if row is None or row["tasklist_id"] != lst["id"]:
        return _missing()
    return _task_view(row)


def _check_fields(fields):
    if "title" in fields and len(fields["title"] or "") > TITLE_LIMIT:
        return _invalid(f"Invalid value for title: it can be at most {TITLE_LIMIT} characters.", field="title")
    if "notes" in fields and len(fields["notes"] or "") > NOTES_LIMIT:
        return _invalid(f"Invalid value for notes: it can be at most {NOTES_LIMIT} characters.", field="notes")
    if fields.get("status") not in (None, *STATUSES):
        return _invalid(f"Invalid value for status: {fields['status']!r}; use needsAction or completed.",
                        field="status")
    return None


def _apply(row, fields):
    """``row`` with the writable ``fields`` applied, keeping status and completion time consistent."""
    out = dict(row)
    for key in ("title", "notes"):
        if key in fields:
            out[key] = fields[key] or ""
    if "due" in fields:
        if fields["due"]:
            due = _due_value(fields["due"])
            if isinstance(due, GoogleError):
                return due
            out["due"] = due
        else:
            out["due"] = ""
    if "completed" in fields and fields["completed"]:
        moment = _instant(fields["completed"], "completed")
        if isinstance(moment, GoogleError):
            return moment
    status = fields.get("status", out["status"])
    if status == "completed":
        if out["status"] != "completed" or fields.get("completed"):
            out["completed"] = fields.get("completed") or _now()
    else:
        out["completed"] = ""
        out["hidden"] = False
    out["status"] = status
    if "deleted" in fields and fields["deleted"] is not None:
        out["deleted"] = bool(fields["deleted"])
    out["updated"] = _now()
    return out


def _next_position(tasklist_id, parent, previous):
    siblings = sorted((t for t in _tasks(tasklist_id) if t["parent"] == (parent or "") and not t["deleted"]),
                      key=lambda t: t["position"])
    if previous:
        index = next((i for i, t in enumerate(siblings) if t["id"] == previous), None)
        if index is None:
            return None, siblings
        before = int(siblings[index]["position"])
        after = int(siblings[index + 1]["position"]) if index + 1 < len(siblings) else before + 2 ** 20
        return f"{(before + after) // 2:020d}", siblings
    first = int(siblings[0]["position"]) if siblings else 2 ** 40
    return f"{max(first // 2, 0):020d}", siblings


def create_task(tasklist, account_id, fields, parent=None, previous=None):
    lst = resolve_list(tasklist, account_id)
    if lst is None:
        return _missing()
    problem = _check_fields(fields)
    if problem:
        return problem
    if not (fields.get("title") or "").strip():
        return _invalid("Missing title: a task needs a title.", field="title")
    if parent:
        parent_row = _store.table("tasks").get(parent)
        if parent_row is None or parent_row["tasklist_id"] != lst["id"] or parent_row["deleted"]:
            return _invalid(f"Invalid value for parent: task {parent!r} is not in this task list.", field="parent")
        if parent_row["parent"]:
            return _invalid("Invalid value for parent: subtasks cannot have subtasks.", field="parent")
    position, _siblings = _next_position(lst["id"], parent, previous)
    if position is None:
        return _invalid(f"Invalid value for previous: task {previous!r} is not a sibling in this task list.",
                        field="previous")
    row = {"id": _new_id(), "tasklist_id": lst["id"], "title": "", "notes": "", "due": "", "completed": "",
           "status": "needsAction", "parent": parent or "", "position": position, "deleted": False,
           "hidden": False, "updated": _now()}
    row = _apply(row, fields)
    if isinstance(row, GoogleError):
        return row
    _store.table("tasks").upsert(row)
    _store.table("tasklists").patch(lst["id"], {"updated": row["updated"]})
    return _task_view(_store.table("tasks").get(row["id"]))


def update_task(tasklist, task_id, account_id, fields, replace=False):
    lst = resolve_list(tasklist, account_id)
    if lst is None:
        return _missing()
    row = _store.table("tasks").get(task_id)
    if row is None or row["tasklist_id"] != lst["id"]:
        return _missing()
    if fields.get("id") and fields["id"] != task_id:
        return _invalid("Invalid value for id: it does not match the task in the request path.", field="id")
    problem = _check_fields(fields)
    if problem:
        return problem
    if replace:
        if not (fields.get("title") or "").strip():
            return _invalid("Missing title: tasks.update replaces the whole task, so send its title.",
                            field="title")
        fields = {"title": fields.get("title"), "notes": fields.get("notes"), "due": fields.get("due"),
                  "status": fields.get("status") or "needsAction", "completed": fields.get("completed"),
                  **({"deleted": fields["deleted"]} if "deleted" in fields else {})}
    elif "title" in fields and not (fields["title"] or "").strip():
        return _invalid("Invalid value for title: a task title cannot be empty.", field="title")
    changed = _apply(row, fields)
    if isinstance(changed, GoogleError):
        return changed
    _store.table("tasks").upsert(changed)
    _store.table("tasklists").patch(lst["id"], {"updated": changed["updated"]})
    return _task_view(_store.table("tasks").get(task_id))


def delete_task(tasklist, task_id, account_id):
    lst = resolve_list(tasklist, account_id)
    if lst is None:
        return _missing()
    row = _store.table("tasks").get(task_id)
    if row is None or row["tasklist_id"] != lst["id"] or row["deleted"]:
        return _missing()
    now = _now()
    _store.table("tasks").patch(task_id, {"deleted": True, "updated": now})
    for child in _store.table("tasks").find(lambda t: t["parent"] == task_id and not t["deleted"]):
        _store.table("tasks").patch(child["id"], {"deleted": True, "updated": now})
    _store.table("tasklists").patch(lst["id"], {"updated": now})
    return None


_store.eager_load()
