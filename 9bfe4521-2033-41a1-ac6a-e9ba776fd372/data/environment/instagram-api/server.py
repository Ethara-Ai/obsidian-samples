"""FastAPI server wrapping instagram_data as REST endpoints.

Mirrors the Instagram Graph API (graph.facebook.com/v21.0) for the ten connector
operations the client ranks. Every operation needs a bearer token from
POST /oauth/token, and each one checks its own scope, so a connected account is
not by itself permission to publish.
"""

from typing import Optional

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

import instagram_data
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

V = "/" + instagram_data.GRAPH_VERSION
auth = instagram_data.auth

app = FastAPI(title="Instagram Graph API (Mock)", version=instagram_data.GRAPH_VERSION)
install_tracker(app)
install_admin_plane(app, store=instagram_data._store)
auth.install(app)


@app.get("/health")
def health():
    return {"status": "ok"}


def _reply(result, status_code=200):
    if isinstance(result, instagram_data.GraphError):
        return JSONResponse(status_code=result.status, content=result.body)
    if status_code != 200:
        return JSONResponse(status_code=status_code, content=result)
    return result


def _account(request: Request) -> str:
    return request.state.oauth["account_id"]


# --- .accounts / .profile ---------------------------------------------------------

@app.get(V + "/me/accounts", dependencies=[auth.require("instagram_basic")])
def list_accounts(request: Request, fields: Optional[str] = None):
    return _reply(instagram_data.list_accounts(_account(request), fields=fields))


@app.get(V + "/{ig_user_id}", dependencies=[auth.require("instagram_basic")])
def get_profile(ig_user_id: str, request: Request, fields: Optional[str] = None):
    return _reply(instagram_data.get_profile(ig_user_id, _account(request), fields=fields))


# --- .posts -------------------------------------------------------------------------

@app.get(V + "/{ig_user_id}/media", dependencies=[auth.require("instagram_basic")])
def list_media(
    ig_user_id: str,
    request: Request,
    fields: Optional[str] = None,
    limit: int = Query(25, ge=1, le=100),
    after: Optional[str] = None,
):
    return _reply(instagram_data.list_media(ig_user_id, _account(request), limit=limit,
                                            after=after, fields=fields))


# --- .post-feed / .post-story --------------------------------------------------------

class MediaContainerBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    media_type: Optional[str] = None
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    caption: Optional[str] = None


@app.post(V + "/{ig_user_id}/media", status_code=201,
          dependencies=[auth.require("instagram_content_publish")])
def create_media_container(ig_user_id: str, body: MediaContainerBody, request: Request):
    return _reply(instagram_data.create_container(
        ig_user_id, _account(request), media_type=body.media_type, image_url=body.image_url,
        video_url=body.video_url, caption=body.caption,
    ), status_code=201)


class MediaPublishBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    creation_id: str


@app.post(V + "/{ig_user_id}/media_publish", status_code=201,
          dependencies=[auth.require("instagram_content_publish")])
def publish_media(ig_user_id: str, body: MediaPublishBody, request: Request):
    return _reply(instagram_data.publish_container(ig_user_id, _account(request), body.creation_id),
                  status_code=201)


# --- .account-insights ------------------------------------------------------------------

@app.get(V + "/{ig_user_id}/insights", dependencies=[auth.require("instagram_manage_insights")])
def get_insights(
    ig_user_id: str,
    request: Request,
    metric: str = "",
    period: str = "day",
    since: Optional[str] = None,
    until: Optional[str] = None,
):
    return _reply(instagram_data.get_insights(ig_user_id, _account(request), metric, period=period,
                                              since=since, until=until))


# --- .saved-posts ------------------------------------------------------------------------

@app.get(V + "/{ig_user_id}/saved_media", dependencies=[auth.require("instagram_saved_media")])
def list_saved_media(
    ig_user_id: str,
    request: Request,
    limit: int = Query(25, ge=1, le=100),
    after: Optional[str] = None,
):
    return _reply(instagram_data.list_saved(ig_user_id, _account(request), limit=limit, after=after))


# --- .fetch-post-comments ----------------------------------------------------------------

@app.get(V + "/{media_id}/comments", dependencies=[auth.require("instagram_manage_comments")])
def list_comments(
    media_id: str,
    request: Request,
    limit: int = Query(25, ge=1, le=100),
    after: Optional[str] = None,
):
    return _reply(instagram_data.list_comments(media_id, _account(request), limit=limit, after=after))


# --- .followers / .following --------------------------------------------------------------

@app.get(V + "/{ig_user_id}/followers", dependencies=[auth.require("instagram_relationships")])
def list_followers(
    ig_user_id: str,
    request: Request,
    limit: int = Query(25, ge=1, le=100),
    after: Optional[str] = None,
):
    return _reply(instagram_data.list_relationships("followers", ig_user_id, _account(request),
                                                    limit=limit, after=after))


@app.get(V + "/{ig_user_id}/following", dependencies=[auth.require("instagram_relationships")])
def list_following(
    ig_user_id: str,
    request: Request,
    limit: int = Query(25, ge=1, le=100),
    after: Optional[str] = None,
):
    return _reply(instagram_data.list_relationships("following", ig_user_id, _account(request),
                                                    limit=limit, after=after))
