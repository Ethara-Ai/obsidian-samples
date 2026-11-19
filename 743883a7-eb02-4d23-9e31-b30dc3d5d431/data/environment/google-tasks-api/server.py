"""FastAPI server wrapping google_tasks_data as REST endpoints.

Mirrors the Google Tasks API v1 (tasks.googleapis.com/tasks/v1) for the six
operations the connector needs: list task lists, list the tasks in a list, get
a task, create a task, update a task (tasks.update replaces it, tasks.patch
changes the fields sent, either one can mark it complete), and delete a task.
Every operation needs a bearer token from POST /oauth/token, and each one
checks its own scope, so a connected account is not by itself permission to
edit. Errors use Google's own envelope, including request validation failures
and query parameters the method does not take.
"""

import json
from typing import List, Literal, Optional

from fastapi import Depends, FastAPI, Request, Response
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

import google_tasks_data
try:
    from tracking_middleware import install_tracker
    from admin_plane import install_admin_plane
except ModuleNotFoundError as _shared_plane_err:  # standalone run without the shared module on sys.path
    import logging as _logging
    _logging.error("SHARED PLANE MISSING - audit + admin disabled: %s", _shared_plane_err)
    def install_tracker(app):  # no-op fallback: audit endpoints disabled
        return None

    def install_admin_plane(app, store=None, one_shot_registry=None):
        return None

V = "/tasks/v1"
auth = google_tasks_data.auth
GoogleError = google_tasks_data.GoogleError

app = FastAPI(title="Google Tasks API (Mock)", version="v1")
install_tracker(app)
install_admin_plane(app, store=google_tasks_data._store)
auth.install(app)

SHARED_PLANES = ("/admin", "/audit")


class GoogleApiError(Exception):
    def __init__(self, error: GoogleError):
        super().__init__(error.body["error"]["message"])
        self.error = error


def _render(error: GoogleError) -> JSONResponse:
    return JSONResponse(status_code=error.status, content=error.body)


def _validation_error(exc: RequestValidationError) -> GoogleError:
    err = exc.errors()[0]
    loc = [str(p) for p in (err.get("loc") or [])]
    where, parts = (loc[0], loc[1:]) if loc else ("body", [])
    kind, value = err.get("type", ""), err.get("input")
    if kind == "json_invalid":
        return GoogleError(400, "Invalid JSON payload received. Unexpected token.", reason="parseError")
    if kind == "extra_forbidden" and parts:
        name, parent = parts[-1], ".".join(parts[:-1])
        return GoogleError(400, f'Invalid JSON payload received. Unknown name "{name}"'
                                + (f" at '{parent}'" if parent else "") + ": Cannot find field.", reason="invalid")
    name = ".".join(parts) or where
    return GoogleError(400, f"Invalid value for {name}: {json.dumps(value, default=str)}", reason="invalid")


@app.exception_handler(GoogleApiError)
async def _google_api_error(_request: Request, exc: GoogleApiError):
    return _render(exc.error)


@app.exception_handler(RequestValidationError)
async def _invalid_request(request: Request, exc: RequestValidationError):
    if request.url.path.startswith(SHARED_PLANES):
        return await request_validation_exception_handler(request, exc)
    return _render(_validation_error(exc))


@app.exception_handler(StarletteHTTPException)
async def _http_error(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith(SHARED_PLANES) or exc.status_code not in (404, 405):
        return await http_exception_handler(request, exc)
    return _render(GoogleError(404, "Requested entity was not found.", reason="notFound"))


def known_query(request: Request):
    """Refuse a query parameter the method does not declare instead of ignoring it."""
    route = request.scope.get("route")
    allowed = {p.alias for p in route.dependant.query_params} if route is not None else set()
    for name in request.query_params.keys():
        if name not in allowed:
            raise GoogleApiError(GoogleError(
                400, f'Invalid JSON payload received. Unknown name "{name}": Cannot bind query parameter. '
                     f"Field '{name}' could not be found in request message.", reason="invalid"))


STRICT = Depends(known_query)


@app.get("/health")
def health():
    return {"status": "ok"}


def _reply(result):
    if isinstance(result, GoogleError):
        return _render(result)
    if result is None:
        return Response(status_code=204)
    return result


def _account(request: Request) -> str:
    return request.state.oauth["account_id"]


# --- tasklists.list ----------------------------------------------------------------------------

@app.get(V + "/users/@me/lists", dependencies=[auth.require("tasks.readonly", implied_by=("tasks",)), STRICT])
def list_tasklists(request: Request, maxResults: int = 1000, pageToken: Optional[str] = None):
    return _reply(google_tasks_data.list_tasklists(_account(request), max_results=maxResults, page_token=pageToken))


# --- tasks.list / tasks.get ------------------------------------------------------------------------

@app.get(V + "/lists/{tasklist}/tasks", dependencies=[auth.require("tasks.readonly", implied_by=("tasks",)), STRICT])
def list_tasks(
    tasklist: str,
    request: Request,
    maxResults: int = 20,
    pageToken: Optional[str] = None,
    showCompleted: bool = True,
    showDeleted: bool = False,
    showHidden: bool = False,
    completedMin: Optional[str] = None,
    completedMax: Optional[str] = None,
    dueMin: Optional[str] = None,
    dueMax: Optional[str] = None,
    updatedMin: Optional[str] = None,
):
    return _reply(google_tasks_data.list_tasks(
        tasklist, _account(request), max_results=maxResults, page_token=pageToken, show_completed=showCompleted,
        show_deleted=showDeleted, show_hidden=showHidden, completed_min=completedMin, completed_max=completedMax,
        due_min=dueMin, due_max=dueMax, updated_min=updatedMin))


@app.get(V + "/lists/{tasklist}/tasks/{task}", dependencies=[auth.require("tasks.readonly", implied_by=("tasks",)), STRICT])
def get_task(tasklist: str, task: str, request: Request):
    return _reply(google_tasks_data.get_task(tasklist, task, _account(request)))


# --- tasks.insert / tasks.update / tasks.patch / tasks.delete ----------------------------------

class TaskLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Optional[str] = None
    description: Optional[str] = None
    link: Optional[str] = None


class TaskBody(BaseModel):
    """A Task resource. Output-only fields are accepted so a task read back can be sent again."""

    model_config = ConfigDict(extra="forbid")

    kind: Optional[Literal["tasks#task"]] = None
    id: Optional[str] = None
    etag: Optional[str] = None
    title: Optional[str] = None
    updated: Optional[str] = None
    selfLink: Optional[str] = None
    parent: Optional[str] = None
    position: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    due: Optional[str] = None
    completed: Optional[str] = None
    deleted: Optional[bool] = None
    hidden: Optional[bool] = None
    links: Optional[List[TaskLink]] = None
    webViewLink: Optional[str] = None


WRITABLE = ("title", "notes", "status", "due", "completed", "deleted")


def _fields(body: Optional[TaskBody]) -> dict:
    sent = body.model_dump(exclude_unset=True) if body else {}
    return {k: sent[k] for k in ("id", *WRITABLE) if k in sent}


@app.post(V + "/lists/{tasklist}/tasks", dependencies=[auth.require("tasks"), STRICT])
def create_task(tasklist: str, request: Request, body: Optional[TaskBody] = None, parent: Optional[str] = None,
                previous: Optional[str] = None):
    fields = _fields(body)
    fields.pop("id", None)
    return _reply(google_tasks_data.create_task(tasklist, _account(request), fields, parent=parent,
                                                previous=previous))


@app.put(V + "/lists/{tasklist}/tasks/{task}", dependencies=[auth.require("tasks"), STRICT])
def update_task(tasklist: str, task: str, request: Request, body: Optional[TaskBody] = None):
    return _reply(google_tasks_data.update_task(tasklist, task, _account(request), _fields(body), replace=True))


@app.patch(V + "/lists/{tasklist}/tasks/{task}", dependencies=[auth.require("tasks"), STRICT])
def patch_task(tasklist: str, task: str, request: Request, body: Optional[TaskBody] = None):
    return _reply(google_tasks_data.update_task(tasklist, task, _account(request), _fields(body)))


@app.delete(V + "/lists/{tasklist}/tasks/{task}", status_code=204, dependencies=[auth.require("tasks"), STRICT])
def delete_task(tasklist: str, task: str, request: Request):
    return _reply(google_tasks_data.delete_task(tasklist, task, _account(request)))
