"""FastAPI server wrapping facebook_data as REST endpoints.

Mirrors the Facebook Graph API (graph.facebook.com/v21.0) for the eight connector
operations the client lists. Every operation needs a bearer token from
POST /oauth/token, and each one checks its own scope, so a connected account is
not by itself permission to post or to read the news feed.
"""

from typing import Optional

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

import facebook_data
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

V = "/" + facebook_data.GRAPH_VERSION
auth = facebook_data.auth

app = FastAPI(title="Facebook Graph API (Mock)", version=facebook_data.GRAPH_VERSION)
install_tracker(app)
install_admin_plane(app, store=facebook_data._store)
auth.install(app)


@app.get("/health")
def health():
    return {"status": "ok"}


def _reply(result):
    if isinstance(result, facebook_data.GraphError):
        return JSONResponse(status_code=result.status, content=result.body)
    return result


def _account(request: Request) -> str:
    return request.state.oauth["account_id"]


# --- .me ----------------------------------------------------------------------------

@app.get(V + "/me", dependencies=[auth.require("public_profile")])
def get_me(request: Request, fields: Optional[str] = None):
    return _reply(facebook_data.get_me(_account(request), fields=fields))


# --- .timeline / .post (create) -----------------------------------------------------------

@app.get(V + "/me/feed", dependencies=[auth.require("user_posts")])
def list_timeline(
    request: Request,
    limit: int = Query(25, ge=1, le=100),
    after: Optional[str] = None,
):
    return _reply(facebook_data.list_timeline(_account(request), limit=limit, after=after))


class CreatePostBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str
    link: Optional[str] = None
    privacy: Optional[str] = None


@app.post(V + "/me/feed", dependencies=[auth.require("publish_actions")])
def create_post(body: CreatePostBody, request: Request):
    return _reply(facebook_data.create_post(_account(request), body.message, link=body.link,
                                            privacy=body.privacy))


# --- .feed ----------------------------------------------------------------------------------

@app.get(V + "/me/home", dependencies=[auth.require("user_feed")])
def list_home(
    request: Request,
    limit: int = Query(25, ge=1, le=100),
    after: Optional[str] = None,
):
    return _reply(facebook_data.list_home(_account(request), limit=limit, after=after))


# --- .groups ---------------------------------------------------------------------------------

@app.get(V + "/me/groups", dependencies=[auth.require("groups_access_member_info")])
def list_groups(
    request: Request,
    limit: int = Query(25, ge=1, le=100),
    after: Optional[str] = None,
):
    return _reply(facebook_data.list_groups(_account(request), limit=limit, after=after))


@app.get(V + "/{group_id}/feed", dependencies=[auth.require("groups_access_member_info")])
def list_group_feed(
    group_id: str,
    request: Request,
    limit: int = Query(25, ge=1, le=100),
    after: Optional[str] = None,
):
    return _reply(facebook_data.list_group_feed(group_id, _account(request), limit=limit,
                                                after=after))


# --- .saved ------------------------------------------------------------------------------------

@app.get(V + "/me/saved", dependencies=[auth.require("user_saved")])
def list_saved(
    request: Request,
    limit: int = Query(25, ge=1, le=100),
    after: Optional[str] = None,
):
    return _reply(facebook_data.list_saved(_account(request), limit=limit, after=after))


# --- .marketplace -------------------------------------------------------------------------------

@app.get(V + "/marketplace_listings", dependencies=[auth.require("marketplace_listings")])
def search_listings(
    q: Optional[str] = None,
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    location: Optional[str] = None,
    condition: Optional[str] = None,
    limit: int = Query(25, ge=1, le=100),
    after: Optional[str] = None,
):
    return _reply(facebook_data.search_listings(
        q=q, category=category, min_price=min_price, max_price=max_price, location=location,
        condition=condition, limit=limit, after=after,
    ))


@app.get(V + "/marketplace_listings/{listing_id}", dependencies=[auth.require("marketplace_listings")])
def get_listing(listing_id: str):
    return _reply(facebook_data.get_listing(listing_id))


# --- .post (retrieve by link / by id) --------------------------------------------------------------

@app.get(V + "/posts", dependencies=[auth.require("user_posts")])
def get_post_by_link(request: Request, link: str):
    return _reply(facebook_data.get_post_by_link(link, _account(request)))


@app.get(V + "/{owner_id}_{post_suffix}", dependencies=[auth.require("user_posts")])
def get_post(owner_id: str, post_suffix: str, request: Request, fields: Optional[str] = None):
    return _reply(facebook_data.get_post(f"{owner_id}_{post_suffix}", _account(request),
                                         fields=fields))


# --- .profile --------------------------------------------------------------------------------------

@app.get(V + "/{user_id}", dependencies=[auth.require("public_profile")])
def get_profile(user_id: str, request: Request, fields: Optional[str] = None):
    return _reply(facebook_data.get_profile(user_id, _account(request), fields=fields))
