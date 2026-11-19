"""FastAPI server wrapping spotify_data as REST endpoints.

Mirrors the Spotify Web API (api.spotify.com/v1) for the ten connector
operations the client ranks. Every operation needs a bearer token from
POST /oauth/token. Search works for any live token (Spotify issues no scope
unless asked); every other operation checks its own scope, so a connected
account is not by itself permission to change playlists or control playback.
"""

from typing import List, Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

import spotify_data
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

V = "/v1"
auth = spotify_data.auth

app = FastAPI(title="Spotify Web API (Mock)", version="v1")
install_tracker(app)
install_admin_plane(app, store=spotify_data._store)
auth.install(app)


@app.get("/health")
def health():
    return {"status": "ok"}


def _reply(result, status_code=200):
    if isinstance(result, spotify_data.SpotifyError):
        return JSONResponse(status_code=result.status, content=result.body)
    if status_code != 200:
        return JSONResponse(status_code=status_code, content=result)
    return result


def _empty(result, status_code):
    """An operation that answers with no body on success."""
    if isinstance(result, spotify_data.SpotifyError):
        return _reply(result)
    return Response(status_code=status_code)


def _account(request: Request) -> str:
    return request.state.oauth["account_id"]


# --- .search ------------------------------------------------------------------------------

@app.get(V + "/search", dependencies=[auth.require(None)])
def search(
    q: Optional[str] = None,
    type: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
):
    return _reply(spotify_data.search(q, type, limit=limit, offset=offset))


# --- .library / .playlist-tracks ---------------------------------------------------------------

@app.get(V + "/me/tracks", dependencies=[auth.require("user-library-read")])
def list_saved_tracks(request: Request, limit: Optional[int] = None, offset: Optional[int] = None):
    return _reply(spotify_data.list_saved_tracks(_account(request), limit=limit, offset=offset))


@app.get(V + "/me/playlists", dependencies=[auth.require("playlist-read-private")])
def list_my_playlists(request: Request, limit: Optional[int] = None, offset: Optional[int] = None):
    return _reply(spotify_data.list_my_playlists(_account(request), limit=limit, offset=offset))


@app.get(V + "/playlists/{playlist_id}/tracks", dependencies=[auth.require("playlist-read-private")])
def list_playlist_tracks(playlist_id: str, request: Request, limit: Optional[int] = None,
                         offset: Optional[int] = None):
    return _reply(spotify_data.list_playlist_tracks(playlist_id, _account(request), limit=limit,
                                                    offset=offset))


# --- .create-collection / .update-collection / .add-to-collection ------------------------------

class CreatePlaylistBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: Optional[str] = None
    public: Optional[bool] = None
    collaborative: Optional[bool] = None


@app.post(V + "/me/playlists", status_code=201, dependencies=[auth.require("playlist-modify-private")])
def create_playlist(body: CreatePlaylistBody, request: Request):
    return _reply(spotify_data.create_playlist(
        _account(request), body.name, description=body.description, public=body.public,
        collaborative=body.collaborative,
    ), status_code=201)


class UpdatePlaylistBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    description: Optional[str] = None
    public: Optional[bool] = None
    collaborative: Optional[bool] = None


@app.put(V + "/playlists/{playlist_id}", dependencies=[auth.require("playlist-modify-private")])
def update_playlist(playlist_id: str, body: UpdatePlaylistBody, request: Request):
    changes = {key: getattr(body, key) for key in body.model_fields_set}
    return _empty(spotify_data.update_playlist(playlist_id, _account(request), changes), 200)


class AddItemsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uris: List[str]
    position: Optional[int] = None


@app.post(V + "/playlists/{playlist_id}/tracks", status_code=201,
          dependencies=[auth.require("playlist-modify-private")])
def add_playlist_items(playlist_id: str, body: AddItemsBody, request: Request):
    return _reply(spotify_data.add_playlist_items(playlist_id, _account(request), body.uris,
                                                  position=body.position), status_code=201)


# --- .devices / .play / .now-playing / .transfer -------------------------------------------------

@app.get(V + "/me/player/devices", dependencies=[auth.require("user-read-playback-state")])
def list_devices(request: Request):
    return _reply(spotify_data.list_devices(_account(request)))


class PlayOffset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: Optional[int] = None
    uri: Optional[str] = None


class PlayBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context_uri: Optional[str] = None
    uris: Optional[List[str]] = None
    offset: Optional[PlayOffset] = None
    position_ms: Optional[int] = None


@app.put(V + "/me/player/play", dependencies=[auth.require("user-modify-playback-state")])
def start_playback(request: Request, body: Optional[PlayBody] = None, device_id: Optional[str] = None):
    body = body or PlayBody()
    offset = {k: getattr(body.offset, k) for k in body.offset.model_fields_set
              if getattr(body.offset, k) is not None} if body.offset else None
    return _empty(spotify_data.start_playback(
        _account(request), device_id=device_id, context_uri=body.context_uri, uris=body.uris,
        offset=offset, position_ms=body.position_ms,
    ), 204)


@app.get(V + "/me/player/currently-playing", dependencies=[auth.require("user-read-currently-playing")])
def currently_playing(request: Request, additional_types: Optional[str] = None):
    result = spotify_data.currently_playing(_account(request), additional_types=additional_types)
    if result is None:
        return Response(status_code=204)
    return _reply(result)


class TransferBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_ids: List[str]
    play: Optional[bool] = None


@app.put(V + "/me/player", dependencies=[auth.require("user-modify-playback-state")])
def transfer_playback(body: TransferBody, request: Request):
    return _empty(spotify_data.transfer_playback(_account(request), body.device_ids, play=body.play), 204)
