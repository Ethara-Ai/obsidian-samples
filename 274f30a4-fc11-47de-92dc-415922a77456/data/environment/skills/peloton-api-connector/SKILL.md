---
name: peloton-api-connector
description: >
  Peloton API (Mock) mock HTTP API. Base URL is provided via the
  `PELOTON_API_URL` environment variable. 7 endpoint(s) across GET, POST.
  Every operation needs an OAuth bearer token that carries the operation's scope.
---

# Peloton API (Mock)

Mock HTTP API. **All requests go to the base URL in `$PELOTON_API_URL`.** Every operation needs a bearer token, and a token covers only the scopes it was issued with: a connected account is not permission for every action. Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `PELOTON_API_URL` | Base URL for all requests (e.g. `http://peloton-api:8134`) |
| `PELOTON_CLIENT_ID` | OAuth client id of the connected account, when the task provides it |
| `PELOTON_CLIENT_SECRET` | OAuth client secret of the connected account, when the task provides it |

## Authentication

1. Exchange the client credentials for an access token: `POST /oauth/token` with `grant_type=client_credentials`, `client_id`, `client_secret`, and optionally `scope` (space-separated). Form-encoded and JSON bodies are both accepted.
2. Send `Authorization: Bearer <access_token>` on every operation.
3. `GET /oauth/tokeninfo` reports the presented token's scopes and expiry.

A token requested without `scope` carries only the default scopes (`profile.read workouts.read classes.read`). Ask for any other scope explicitly. A `401 invalid_token` means the token is missing, expired, or revoked; get a new one. A `403 insufficient_scope` names the `required_scope`; request a token that carries it. The token endpoint answers `invalid_scope` when the account never granted a scope to this client. `grant_type=refresh_token` exchanges a refresh token for a new access token.

## Scopes

| Scope | Operations |
|-------|------------|
| `classes.read` | GET `/api/v2/ride/archived` |
| `profile.read` | GET `/api/me` |
| `workouts.read` | GET `/api/user/{user_id}/workouts`, GET `/api/workout/{workout_id}`, GET `/api/workout/{workout_id}/performance_graph` |

## Endpoints

| Method | Path |
|--------|------|
| POST | `/oauth/token` |
| GET | `/oauth/tokeninfo` |
| GET | `/api/me` |
| GET | `/api/user/{user_id}/workouts` |
| GET | `/api/workout/{workout_id}` |
| GET | `/api/workout/{workout_id}/performance_graph` |
| GET | `/api/v2/ride/archived` |

## Usage

```bash
TOKEN=$(curl -s -X POST "$PELOTON_API_URL/oauth/token" -d grant_type=client_credentials \
  -d client_id="$PELOTON_CLIENT_ID" -d client_secret="$PELOTON_CLIENT_SECRET" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$PELOTON_API_URL/api/me" -H "Authorization: Bearer $TOKEN"
```

## Paging

- `GET /api/user/{user_id}/workouts` returns 20 per page by default (`limit`, up to 100); while `show_next` is true, ask for `page` + 1 (pages count from 0).
