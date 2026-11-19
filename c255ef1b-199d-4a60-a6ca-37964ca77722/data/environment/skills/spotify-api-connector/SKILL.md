---
name: spotify-api-connector
description: >
  Spotify Web API (Mock) mock HTTP API. Base URL is provided via the
  `SPOTIFY_API_URL` environment variable. 13 endpoint(s) across GET, POST, PUT.
  Every operation needs an OAuth bearer token that carries the operation's scope.
---

# Spotify Web API (Mock)

Mock HTTP API. **All requests go to the base URL in `$SPOTIFY_API_URL`.** Every operation needs a bearer token, and a token covers only the scopes it was issued with: a connected account is not permission for every action. Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `SPOTIFY_API_URL` | Base URL for all requests (e.g. `http://spotify-api:8108`) |
| `SPOTIFY_CLIENT_ID` | OAuth client id of the connected account, when the task provides it |
| `SPOTIFY_CLIENT_SECRET` | OAuth client secret of the connected account, when the task provides it |

## Authentication

1. Exchange the client credentials for an access token: `POST /oauth/token` with `grant_type=client_credentials`, `client_id`, `client_secret`, and optionally `scope` (space-separated). Form-encoded and JSON bodies are both accepted.
2. Send `Authorization: Bearer <access_token>` on every operation.
3. `GET /oauth/tokeninfo` reports the presented token's scopes and expiry.

A token requested without `scope` carries only the default scopes (none). Ask for any other scope explicitly. A `401 invalid_token` means the token is missing, expired, or revoked; get a new one. A `403 insufficient_scope` names the `required_scope`; request a token that carries it. The token endpoint answers `invalid_scope` when the account never granted a scope to this client. `grant_type=refresh_token` exchanges a refresh token for a new access token.

## Scopes

| Scope | Operations |
|-------|------------|
| (any live token) | GET `/v1/search` |
| `playlist-modify-private` | POST `/v1/me/playlists`, PUT `/v1/playlists/{playlist_id}`, POST `/v1/playlists/{playlist_id}/tracks` |
| `playlist-read-private` | GET `/v1/me/playlists`, GET `/v1/playlists/{playlist_id}/tracks` |
| `user-library-read` | GET `/v1/me/tracks` |
| `user-modify-playback-state` | PUT `/v1/me/player/play`, PUT `/v1/me/player` |
| `user-read-currently-playing` | GET `/v1/me/player/currently-playing` |
| `user-read-playback-state` | GET `/v1/me/player/devices` |

## Endpoints

| Method | Path |
|--------|------|
| POST | `/oauth/token` |
| GET | `/oauth/tokeninfo` |
| GET | `/v1/search` |
| GET | `/v1/me/tracks` |
| GET | `/v1/me/playlists` |
| GET | `/v1/playlists/{playlist_id}/tracks` |
| POST | `/v1/me/playlists` |
| PUT | `/v1/playlists/{playlist_id}` |
| POST | `/v1/playlists/{playlist_id}/tracks` |
| GET | `/v1/me/player/devices` |
| PUT | `/v1/me/player/play` |
| GET | `/v1/me/player/currently-playing` |
| PUT | `/v1/me/player` |

## Usage

```bash
TOKEN=$(curl -s -X POST "$SPOTIFY_API_URL/oauth/token" -d grant_type=client_credentials \
  -d client_id="$SPOTIFY_CLIENT_ID" -d client_secret="$SPOTIFY_CLIENT_SECRET" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$SPOTIFY_API_URL/v1/search?q=jazz&type=track,playlist,show&limit=5" -H "Authorization: Bearer $TOKEN"
```

## Paging

- `GET /v1/me/tracks` returns 20 per page by default (`limit`, up to 50); when `next` is not null, request that URL (it moves `offset` on by `limit`) for the next page.
