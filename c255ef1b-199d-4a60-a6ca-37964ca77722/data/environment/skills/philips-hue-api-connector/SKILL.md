---
name: philips-hue-api-connector
description: >
  Philips Hue API (Mock) mock HTTP API. Base URL is provided via the
  `PHILIPS_HUE_API_URL` environment variable. 8 endpoint(s) across GET, POST, PUT.
  Every operation needs an OAuth bearer token that carries the operation's scope.
---

# Philips Hue API (Mock)

Mock HTTP API. **All requests go to the base URL in `$PHILIPS_HUE_API_URL`.** Every operation needs a bearer token, and a token covers only the scopes it was issued with: a connected account is not permission for every action. Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `PHILIPS_HUE_API_URL` | Base URL for all requests (e.g. `http://philips-hue-api:8131`) |
| `PHILIPS_HUE_CLIENT_ID` | OAuth client id of the connected account, when the task provides it |
| `PHILIPS_HUE_CLIENT_SECRET` | OAuth client secret of the connected account, when the task provides it |

## Authentication

1. Exchange the client credentials for an access token: `POST /oauth/token` with `grant_type=client_credentials`, `client_id`, `client_secret`, and optionally `scope` (space-separated). Form-encoded and JSON bodies are both accepted.
2. Send `Authorization: Bearer <access_token>` on every operation.
3. `GET /oauth/tokeninfo` reports the presented token's scopes and expiry.

A token requested without `scope` carries only the default scopes (`hue.read`). Ask for any other scope explicitly. A `401 invalid_token` means the token is missing, expired, or revoked; get a new one. A `403 insufficient_scope` names the `required_scope`; request a token that carries it. The token endpoint answers `invalid_scope` when the account never granted a scope to this client. `grant_type=refresh_token` exchanges a refresh token for a new access token.

## Scopes

| Scope | Operations |
|-------|------------|
| `hue.control` | PUT `/clip/v2/resource/light/{light_id}`, PUT `/clip/v2/resource/scene/{scene_id}` |
| `hue.read` | GET `/clip/v2/resource/light`, GET `/clip/v2/resource/light/{light_id}`, GET `/clip/v2/resource/room`, GET `/clip/v2/resource/scene` |

## Endpoints

| Method | Path |
|--------|------|
| POST | `/oauth/token` |
| GET | `/oauth/tokeninfo` |
| GET | `/clip/v2/resource/light` |
| GET | `/clip/v2/resource/light/{light_id}` |
| PUT | `/clip/v2/resource/light/{light_id}` |
| GET | `/clip/v2/resource/room` |
| GET | `/clip/v2/resource/scene` |
| PUT | `/clip/v2/resource/scene/{scene_id}` |

## Usage

```bash
TOKEN=$(curl -s -X POST "$PHILIPS_HUE_API_URL/oauth/token" -d grant_type=client_credentials \
  -d client_id="$PHILIPS_HUE_CLIENT_ID" -d client_secret="$PHILIPS_HUE_CLIENT_SECRET" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$PHILIPS_HUE_API_URL/clip/v2/resource/light" -H "Authorization: Bearer $TOKEN"
```
