---
name: instagram-messages-api-connector
description: >
  Instagram Messaging API (Mock) mock HTTP API. Base URL is provided via the
  `INSTAGRAM_MESSAGES_API_URL` environment variable. 5 endpoint(s) across GET, POST.
  Every operation needs an OAuth bearer token that carries the operation's scope.
---

# Instagram Messaging API (Mock)

Mock HTTP API. **All requests go to the base URL in `$INSTAGRAM_MESSAGES_API_URL`.** Every operation needs a bearer token, and a token covers only the scopes it was issued with: a connected account is not permission for every action. Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `INSTAGRAM_MESSAGES_API_URL` | Base URL for all requests (e.g. `http://instagram-messages-api:8112`) |
| `INSTAGRAM_MESSAGES_CLIENT_ID` | OAuth client id of the connected account, when the task provides it |
| `INSTAGRAM_MESSAGES_CLIENT_SECRET` | OAuth client secret of the connected account, when the task provides it |

## Authentication

1. Exchange the client credentials for an access token: `POST /oauth/token` with `grant_type=client_credentials`, `client_id`, `client_secret`, and optionally `scope` (space-separated). Form-encoded and JSON bodies are both accepted.
2. Send `Authorization: Bearer <access_token>` on every operation.
3. `GET /oauth/tokeninfo` reports the presented token's scopes and expiry.

A token requested without `scope` carries only the default scopes (`instagram_messages.read`). Ask for any other scope explicitly. A `401 invalid_token` means the token is missing, expired, or revoked; get a new one. A `403 insufficient_scope` names the `required_scope`; request a token that carries it. The token endpoint answers `invalid_scope` when the account never granted a scope to this client. `grant_type=refresh_token` exchanges a refresh token for a new access token.

## Scopes

| Scope | Operations |
|-------|------------|
| `instagram_messages.read` | GET `/v21.0/me/conversations`, GET `/v21.0/{conversation_id}/messages` |
| `instagram_messages.send` | POST `/v21.0/me/messages` |

## Endpoints

| Method | Path |
|--------|------|
| POST | `/oauth/token` |
| GET | `/oauth/tokeninfo` |
| GET | `/v21.0/me/conversations` |
| GET | `/v21.0/{conversation_id}/messages` |
| POST | `/v21.0/me/messages` |

## Usage

```bash
TOKEN=$(curl -s -X POST "$INSTAGRAM_MESSAGES_API_URL/oauth/token" -d grant_type=client_credentials \
  -d client_id="$INSTAGRAM_MESSAGES_CLIENT_ID" -d client_secret="$INSTAGRAM_MESSAGES_CLIENT_SECRET" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$INSTAGRAM_MESSAGES_API_URL/v21.0/me/conversations?platform=instagram&limit=10" -H "Authorization: Bearer $TOKEN"
```

## Paging

- `GET /v21.0/me/conversations` returns 25 per page by default (`limit`, up to 100); when an answer carries `paging.next`, send `paging.cursors.after` as `after` for the next page.
