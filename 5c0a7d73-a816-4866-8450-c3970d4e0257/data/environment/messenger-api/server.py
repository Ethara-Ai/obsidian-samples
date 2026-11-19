"""FastAPI server wrapping messenger_data as REST endpoints.

Mirrors the Facebook Messenger inbox under the Graph API (graph.facebook.com/v21.0/me)
for the eight connector operations the client lists. Every operation needs a
bearer token from POST /oauth/token, and each one checks its own scope, so a
connected account is not by itself permission to send messages or list contacts.
"""

from typing import Optional

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

import messenger_data
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

V = "/" + messenger_data.GRAPH_VERSION + "/me"
auth = messenger_data.auth

app = FastAPI(title="Facebook Messenger (Mock)", version=messenger_data.GRAPH_VERSION)
install_tracker(app)
install_admin_plane(app, store=messenger_data._store)
auth.install(app)


@app.get("/health")
def health():
    return {"status": "ok"}


def _reply(result):
    if isinstance(result, messenger_data.GraphError):
        return JSONResponse(status_code=result.status, content=result.body)
    return result


def _account(request: Request) -> str:
    return request.state.oauth["account_id"]


# --- .threads -----------------------------------------------------------------------

@app.get(V + "/conversations", dependencies=[auth.require("messenger.read")])
def list_threads(
    request: Request,
    limit: int = Query(25, ge=1, le=100),
    after: Optional[str] = None,
):
    return _reply(messenger_data.list_threads(_account(request), limit=limit, after=after))


@app.get(V + "/conversations/{thread_id}", dependencies=[auth.require("messenger.read")])
def get_thread(thread_id: str, request: Request):
    return _reply(messenger_data.get_thread(thread_id, _account(request)))


# --- .messages ------------------------------------------------------------------------

@app.get(V + "/conversations/{thread_id}/messages", dependencies=[auth.require("messenger.read")])
def list_messages(
    thread_id: str,
    request: Request,
    limit: int = Query(25, ge=1, le=100),
    after: Optional[str] = None,
):
    return _reply(messenger_data.list_messages(thread_id, _account(request), limit=limit, after=after))


# --- .check / .sync / .search ----------------------------------------------------------

@app.get(V + "/unread", dependencies=[auth.require("messenger.read")])
def get_unread(request: Request):
    return _reply(messenger_data.get_unread(_account(request)))


@app.get(V + "/sync", dependencies=[auth.require("messenger.read")])
def sync(request: Request, cursor: Optional[str] = None):
    return _reply(messenger_data.sync(_account(request), cursor=cursor))


@app.get(V + "/search", dependencies=[auth.require("messenger.read")])
def search(request: Request, q: str):
    return _reply(messenger_data.search(_account(request), q))


# --- .contacts --------------------------------------------------------------------------

@app.get(V + "/contacts", dependencies=[auth.require("messenger.contacts")])
def list_contacts(
    request: Request,
    limit: int = Query(25, ge=1, le=100),
    after: Optional[str] = None,
):
    return _reply(messenger_data.list_contacts(_account(request), limit=limit, after=after))


# --- .send / .unsend --------------------------------------------------------------------

class Recipient(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Optional[str] = None
    thread_id: Optional[str] = None


class MessageContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str


class SendMessageBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipient: Recipient
    message: MessageContent


@app.post(V + "/messages", dependencies=[auth.require("messenger.send")])
def send_message(body: SendMessageBody, request: Request):
    return _reply(messenger_data.send_message(
        _account(request), body.message.text, recipient_id=body.recipient.id,
        thread_id=body.recipient.thread_id,
    ))


@app.delete(V + "/messages/{message_id}", dependencies=[auth.require("messenger.send")])
def unsend_message(message_id: str, request: Request):
    return _reply(messenger_data.unsend_message(message_id, _account(request)))
