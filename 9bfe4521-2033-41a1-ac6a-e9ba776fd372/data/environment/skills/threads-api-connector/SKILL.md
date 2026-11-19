---
name: threads-api-connector
description: >
  Threads API (Mock) mock HTTP API. Base URL is provided via the
  `THREADS_API_URL` environment variable. 8 endpoint(s) across GET, POST.
  Every operation needs an OAuth bearer token that carries the operation's scope.
---

# Threads API (Mock)

Mock HTTP API. **All requests go to the base URL in `$THREADS_API_URL`.** Every operation needs a bearer token, and a token covers only the scopes it was issued with: a connected account is not permission for every action. Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `THREADS_API_URL` | Base URL for all requests (e.g. `http://threads-api:8113`) |
| `THREADS_CLIENT_ID` | OAuth client id of the connected account, when the task provides it |
| `THREADS_CLIENT_SECRET` | OAuth client secret of the connected account, when the task provides it |

## Authentication

1. Exchange the client credentials for an access token: `POST /oauth/token` with `grant_type=client_credentials`, `client_id`, `client_secret`, and optionally `scope` (space-separated). Form-encoded and JSON bodies are both accepted.
2. Send `Authorization: Bearer <access_token>` on every operation.
3. `GET /oauth/tokeninfo` reports the presented token's scopes and expiry.

A token requested without `scope` carries only the default scopes (`threads_basic`). Ask for any other scope explicitly. A `401 invalid_token` means the token is missing, expired, or revoked; get a new one. A `403 insufficient_scope` names the `required_scope`; request a token that carries it. The token endpoint answers `invalid_scope` when the account never granted a scope to this client. `grant_type=refresh_token` exchanges a refresh token for a new access token.

## Scopes

| Scope | Operations |
|-------|------------|
| `threads_basic` | GET `/v1.0/me`, GET `/v1.0/{threads_media_id}`, GET `/v1.0/{threads_user_id}/threads` |
| `threads_content_publish` | POST `/v1.0/{threads_user_id}/threads`, POST `/v1.0/{threads_user_id}/threads_publish` |
| `threads_read_replies` | GET `/v1.0/{threads_media_id}/replies` |

## Endpoints

| Method | Path |
|--------|------|
| POST | `/oauth/token` |
| GET | `/oauth/tokeninfo` |
| GET | `/v1.0/me` |
| GET | `/v1.0/{threads_media_id}` |
| GET | `/v1.0/{threads_user_id}/threads` |
| POST | `/v1.0/{threads_user_id}/threads` |
| POST | `/v1.0/{threads_user_id}/threads_publish` |
| GET | `/v1.0/{threads_media_id}/replies` |

## Usage

```bash
TOKEN=$(curl -s -X POST "$THREADS_API_URL/oauth/token" -d grant_type=client_credentials \
  -d client_id="$THREADS_CLIENT_ID" -d client_secret="$THREADS_CLIENT_SECRET" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$THREADS_API_URL/v1.0/me?fields=id,username,name,threads_biography" -H "Authorization: Bearer $TOKEN"
```

## Paging

- `GET /v1.0/{threads_user_id}/threads` returns 25 per page by default (`limit`, up to 100); when an answer carries `paging.next`, send `paging.cursors.after` as `after` for the next page.
