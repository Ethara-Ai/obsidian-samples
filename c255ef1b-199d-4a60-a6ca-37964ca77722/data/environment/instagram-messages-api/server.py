"""FastAPI server wrapping instagram_messages_data as REST endpoints.

Mirrors Instagram messaging in the Graph API (v21.0) for the three operations
the connector needs: list conversations, list the messages of a conversation,
and send a message, on the /me routes of the Instagram API with Instagram
Login. Every operation needs a bearer token from POST /oauth/token,
and each one checks its own scope, so reading the inbox is not by itself
permission to reply. Errors use the Graph error envelope, request validation
failures included.
"""

import json
import re
from typing import Literal, Optional

from fastapi import FastAPI, Query, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

import instagram_messages_data
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

V = "/" + instagram_messages_data.GRAPH_VERSION
auth = instagram_messages_data.auth
GraphError = instagram_messages_data.GraphError

app = FastAPI(title="Instagram Messaging API (Mock)", version=instagram_messages_data.GRAPH_VERSION)
install_tracker(app)
install_admin_plane(app, store=instagram_messages_data._store)
auth.install(app)

SHARED_PLANES = ("/admin", "/audit")
TYPE_NAMES = (("int", "an integer"), ("bool", "a boolean"), ("string", "a string"), ("float", "a number"),
              ("dict", "an object"), ("model", "an object"))


def _render(error: GraphError) -> JSONResponse:
    return JSONResponse(status_code=error.status, content=error.body)


def _param(parts) -> str:
    """Graph names a nested parameter message[text]."""
    names = [str(p) for p in parts]
    return names[0] + "".join(f"[{n}]" for n in names[1:]) if names else ""


def _validation_error(exc: RequestValidationError) -> GraphError:
    err = exc.errors()[0]
    loc = list(err.get("loc") or [])
    parts = loc[1:]
    kind, ctx = err.get("type", ""), err.get("ctx") or {}
    name = _param(parts)
    if kind == "json_invalid":
        return instagram_messages_data.invalid("Invalid JSON payload")
    if kind == "missing":
        return instagram_messages_data.invalid(f"The parameter {name} is required")
    if kind == "extra_forbidden":
        return instagram_messages_data.invalid(f"Param {name} is not a valid parameter")
    if kind == "literal_error":
        allowed = ", ".join(re.findall(r"'([^']*)'", str(ctx.get("expected", ""))))
        return instagram_messages_data.invalid(f"Param {name} must be one of {{{allowed}}}")
    if kind.startswith(("greater_than", "less_than")):
        return instagram_messages_data.invalid(f"Param {name} must be a number between 1 and 100")
    expected = next((text for prefix, text in TYPE_NAMES if kind.startswith(prefix)), "valid")
    return instagram_messages_data.invalid(f"Param {name} must be {expected}, got "
                                           f"{json.dumps(err.get('input'), default=str)}")


@app.exception_handler(RequestValidationError)
async def _invalid_request(request: Request, exc: RequestValidationError):
    if request.url.path.startswith(SHARED_PLANES):
        return await request_validation_exception_handler(request, exc)
    return _render(_validation_error(exc))


@app.exception_handler(StarletteHTTPException)
async def _http_error(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith(SHARED_PLANES) or exc.status_code not in (404, 405):
        return await http_exception_handler(request, exc)
    return _render(GraphError(400, f"Unknown path components: {request.url.path}", code=2500,
                              err_type="OAuthException"))


@app.get("/health")
def health():
    return {"status": "ok"}


def _reply(result):
    if isinstance(result, GraphError):
        return _render(result)
    return result


def _account(request: Request) -> str:
    return request.state.oauth["account_id"]


# --- conversations ----------------------------------------------------------------------------

@app.get(V + "/me/conversations", dependencies=[auth.require("instagram_messages.read")])
def list_conversations(
    request: Request,
    platform: Literal["instagram", "messenger"] = "instagram",
    user_id: Optional[str] = None,
    limit: int = Query(25, ge=1, le=100),
    after: Optional[str] = None,
    fields: Optional[str] = None,
):
    return _reply(instagram_messages_data.list_conversations("me", _account(request), platform=platform,
                                                             user_id=user_id, limit=limit, after=after,
                                                             fields=fields))


@app.get(V + "/{conversation_id}/messages", dependencies=[auth.require("instagram_messages.read")])
def list_messages(
    conversation_id: str,
    request: Request,
    limit: int = Query(25, ge=1, le=100),
    after: Optional[str] = None,
    fields: Optional[str] = None,
):
    return _reply(instagram_messages_data.list_messages(conversation_id, _account(request), limit=limit,
                                                        after=after, fields=fields))


# --- send -----------------------------------------------------------------------------------------

class Recipient(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str


class MessageContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str


class SendMessageBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipient: Recipient
    message: MessageContent


@app.post(V + "/me/messages", dependencies=[auth.require("instagram_messages.send")])
def send_message(body: SendMessageBody, request: Request):
    return _reply(instagram_messages_data.send_message("me", _account(request), body.recipient.id,
                                                       body.message.text))
