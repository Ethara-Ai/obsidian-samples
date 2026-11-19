---
name: home-assistant-api-connector
description: >
  Home Assistant API (Mock) mock HTTP API. Base URL is provided via the
  `HOME_ASSISTANT_API_URL` environment variable. 7 endpoint(s) across GET, POST.
  Every operation needs an OAuth bearer token that carries the operation's scope.
---

# Home Assistant API (Mock)

Mock HTTP API. **All requests go to the base URL in `$HOME_ASSISTANT_API_URL`.** Every operation needs a bearer token, and a token covers only the scopes it was issued with: a connected account is not permission for every action. Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `HOME_ASSISTANT_API_URL` | Base URL for all requests (e.g. `http://home-assistant-api:8130`) |
| `HOME_ASSISTANT_CLIENT_ID` | OAuth client id of the connected account, when the task provides it |
| `HOME_ASSISTANT_CLIENT_SECRET` | OAuth client secret of the connected account, when the task provides it |

## Authentication

1. Exchange the client credentials for an access token: `POST /oauth/token` with `grant_type=client_credentials`, `client_id`, `client_secret`, and optionally `scope` (space-separated). Form-encoded and JSON bodies are both accepted.
2. Send `Authorization: Bearer <access_token>` on every operation.
3. `GET /oauth/tokeninfo` reports the presented token's scopes and expiry.

A token requested without `scope` carries only the default scopes (`homeassistant:read`). Ask for any other scope explicitly. A `401 invalid_token` means the token is missing, expired, or revoked; get a new one. A `403 insufficient_scope` names the `required_scope`; request a token that carries it. The token endpoint answers `invalid_scope` when the account never granted a scope to this client. `grant_type=refresh_token` exchanges a refresh token for a new access token.

## Scopes

| Scope | Operations |
|-------|------------|
| `homeassistant:control` | POST `/api/services/{domain}/{service}` |
| `homeassistant:read` | GET `/api/config`, GET `/api/states`, GET `/api/states/{entity_id}`, GET `/api/history/period/{timestamp}` |

## Endpoints

| Method | Path |
|--------|------|
| POST | `/oauth/token` |
| GET | `/oauth/tokeninfo` |
| GET | `/api/config` |
| GET | `/api/states` |
| GET | `/api/states/{entity_id}` |
| POST | `/api/services/{domain}/{service}` |
| GET | `/api/history/period/{timestamp}` |

## Usage

```bash
TOKEN=$(curl -s -X POST "$HOME_ASSISTANT_API_URL/oauth/token" -d grant_type=client_credentials \
  -d client_id="$HOME_ASSISTANT_CLIENT_ID" -d client_secret="$HOME_ASSISTANT_CLIENT_SECRET" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$HOME_ASSISTANT_API_URL/api/config" -H "Authorization: Bearer $TOKEN"
```

## Service calls

`POST /api/services/{domain}/{service}` takes the target in `entity_id` (one id or a list) plus the service's own fields, and answers `200` with only the devices whose state changed. As in Home Assistant, a device it cannot change is skipped without an error, so an empty list `[]` can mean either:

- the device is already in that state (a light that is already on, for `light/turn_on`), or
- there is no such device: an unknown `entity_id`, one of another account, or one of another domain (`switch.porch` sent to `light/turn_on`).

To tell them apart, read `GET /api/states/<entity_id>`: it answers `404` (`Entity not found.`) for an unknown device, and otherwise the device's current `state`. A call with no `entity_id` is a `400`.

```bash
curl -s -X POST "$HOME_ASSISTANT_API_URL/api/services/light/turn_on" -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"entity_id": "light.kitchen_pendant_1", "brightness_pct": 40}'
curl -s "$HOME_ASSISTANT_API_URL/api/states/light.kitchen_pendant_1" -H "Authorization: Bearer $TOKEN"
```
