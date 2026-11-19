"""FastAPI server wrapping threads_data as REST endpoints.

Mirrors the Threads API (graph.threads.net/v1.0) for the five operations the
connector needs: read the profile, list the account's threads, get one thread,
publish a text thread (create a container, then publish it), and list the
replies to a thread. ``GET /v1.0/me`` returns the profile and its Threads user
id; the user routes take ``me`` or that id, and so does the single-object route
for the profile. Every operation needs a bearer token from POST /oauth/token, and each one
checks its own scope, so reading the profile is not by itself permission to
post. Errors use the Threads Graph error envelope, request validation failures
included.
"""

import json
import re
from typing import Optional

from fastapi import FastAPI, Query, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

import threads_data
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

V = "/" + threads_data.API_VERSION
auth = threads_data.auth
GraphError = threads_data.GraphError

app = FastAPI(title="Threads API (Mock)", version=threads_data.API_VERSION)
install_tracker(app)
install_admin_plane(app, store=threads_data._store)
auth.install(app)

SHARED_PLANES = ("/admin", "/audit")
TYPE_NAMES = (("int", "an integer"), ("bool", "a boolean"), ("string", "a string"), ("float", "a number"),
              ("dict", "an object"), ("model", "an object"))


def _render(error: GraphError) -> JSONResponse:
    return JSONResponse(status_code=error.status, content=error.body)


def _param(parts) -> str:
    names = [str(p) for p in parts]
    return names[0] + "".join(f"[{n}]" for n in names[1:]) if names else ""


def _validation_error(exc: RequestValidationError) -> GraphError:
    err = exc.errors()[0]
    loc = list(err.get("loc") or [])
    kind, ctx = err.get("type", ""), err.get("ctx") or {}
    name = _param(loc[1:])
    if kind == "json_invalid":
        return threads_data.invalid("Invalid JSON payload")
    if kind == "missing":
        return threads_data.invalid(f"The parameter {name} is required")
    if kind == "extra_forbidden":
        return threads_data.invalid(f"Param {name} is not a valid parameter")
    if kind == "literal_error":
        allowed = ", ".join(re.findall(r"'([^']*)'", str(ctx.get("expected", ""))))
        return threads_data.invalid(f"Param {name} must be one of {{{allowed}}}")
    if kind.startswith(("greater_than", "less_than")):
        return threads_data.invalid(f"Param {name} must be a number between 1 and 100")
    expected = next((text for prefix, text in TYPE_NAMES if kind.startswith(prefix)), "valid")
    return threads_data.invalid(f"Param {name} must be {expected}, got {json.dumps(err.get('input'), default=str)}")


@app.exception_handler(RequestValidationError)
async def _invalid_request(request: Request, exc: RequestValidationError):
    if request.url.path.startswith(SHARED_PLANES):
        return await request_validation_exception_handler(request, exc)
    return _render(_validation_error(exc))


@app.exception_handler(StarletteHTTPException)
async def _http_error(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith(SHARED_PLANES) or exc.status_code not in (404, 405):
        return await http_exception_handler(request, exc)
    return _render(GraphError(400, f"Unknown path components: {request.url.path}", code=2500))


@app.get("/health")
def health():
    return {"status": "ok"}


def _reply(result):
    if isinstance(result, GraphError):
        return _render(result)
    return result


def _account(request: Request) -> str:
    return request.state.oauth["account_id"]


# --- profile and single thread ------------------------------------------------------------------

@app.get(V + "/me", dependencies=[auth.require("threads_basic")])
def get_profile(request: Request, fields: Optional[str] = None):
    return _reply(threads_data.get_node("me", _account(request), fields=fields))


@app.get(V + "/{threads_media_id}", dependencies=[auth.require("threads_basic")])
def get_thread(threads_media_id: str, request: Request, fields: Optional[str] = None):
    return _reply(threads_data.get_node(threads_media_id, _account(request), fields=fields))


# --- the account's threads ---------------------------------------------------------------------------

@app.get(V + "/{threads_user_id}/threads", dependencies=[auth.require("threads_basic")])
def list_threads(
    threads_user_id: str,
    request: Request,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = Query(25, ge=1, le=100),
    after: Optional[str] = None,
    fields: Optional[str] = None,
):
    return _reply(threads_data.list_threads(threads_user_id, _account(request), since=since, until=until,
                                            limit=limit, after=after, fields=fields))


# --- publishing --------------------------------------------------------------------------------------

class ContainerBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    media_type: str
    text: Optional[str] = None


@app.post(V + "/{threads_user_id}/threads", dependencies=[auth.require("threads_content_publish")])
def create_container(threads_user_id: str, body: ContainerBody, request: Request):
    return _reply(threads_data.create_container(threads_user_id, _account(request), body.media_type, body.text))


class PublishBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    creation_id: str


@app.post(V + "/{threads_user_id}/threads_publish", dependencies=[auth.require("threads_content_publish")])
def publish_container(threads_user_id: str, body: PublishBody, request: Request):
    return _reply(threads_data.publish_container(threads_user_id, _account(request), body.creation_id))


# --- replies -----------------------------------------------------------------------------------------

@app.get(V + "/{threads_media_id}/replies", dependencies=[auth.require("threads_read_replies")])
def list_replies(
    threads_media_id: str,
    request: Request,
    reverse: bool = True,
    limit: int = Query(25, ge=1, le=100),
    after: Optional[str] = None,
    fields: Optional[str] = None,
):
    return _reply(threads_data.list_replies(threads_media_id, _account(request), reverse=reverse, limit=limit,
                                            after=after, fields=fields))
