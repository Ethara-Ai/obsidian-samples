---
name: box-api-connector
description: >
  Box API (Mock) mock HTTP API. Base URL is provided via the
  `BOX_API_URL` environment variable. 8 endpoint(s) across GET, POST, PUT.
  Every operation needs an OAuth bearer token that carries the operation's scope.
---

# Box API (Mock)

Mock HTTP API. **All requests go to the base URL in `$BOX_API_URL`.** Every operation needs a bearer token, and a token covers only the scopes it was issued with: a connected account is not permission for every action. Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `BOX_API_URL` | Base URL for all requests (e.g. `http://box-api:8124`) |
| `BOX_CLIENT_ID` | OAuth client id of the connected account, when the task provides it |
| `BOX_CLIENT_SECRET` | OAuth client secret of the connected account, when the task provides it |

## Authentication

1. Exchange the client credentials for an access token: `POST /oauth/token` with `grant_type=client_credentials`, `client_id`, `client_secret`, and optionally `scope` (space-separated). Form-encoded and JSON bodies are both accepted.
2. Send `Authorization: Bearer <access_token>` on every operation.
3. `GET /oauth/tokeninfo` reports the presented token's scopes and expiry.

A token requested without `scope` carries only the default scopes (`root_readonly`). Ask for any other scope explicitly. A `401 invalid_token` means the token is missing, expired, or revoked; get a new one. A `403 insufficient_scope` names the `required_scope`; request a token that carries it. The token endpoint answers `invalid_scope` when the account never granted a scope to this client. `grant_type=refresh_token` exchanges a refresh token for a new access token.

## Scopes

| Scope | Operations |
|-------|------------|
| `root_readonly` | GET `/2.0/folders/{folder_id}/items`, GET `/2.0/files/{file_id}`, GET `/2.0/search` |
| `root_readwrite` | POST `/2.0/folders`, POST `/api/2.0/files/content`, PUT `/2.0/files/{file_id}` |

## Endpoints

| Method | Path |
|--------|------|
| POST | `/oauth/token` |
| GET | `/oauth/tokeninfo` |
| GET | `/2.0/folders/{folder_id}/items` |
| GET | `/2.0/files/{file_id}` |
| GET | `/2.0/search` |
| POST | `/2.0/folders` |
| POST | `/api/2.0/files/content` |
| PUT | `/2.0/files/{file_id}` |

## Usage

```bash
TOKEN=$(curl -s -X POST "$BOX_API_URL/oauth/token" -d grant_type=client_credentials \
  -d client_id="$BOX_CLIENT_ID" -d client_secret="$BOX_CLIENT_SECRET" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$BOX_API_URL/2.0/folders/0/items" -H "Authorization: Bearer $TOKEN"
```

## Paging

- `GET /2.0/folders/{folder_id}/items` returns 100 per page by default (`limit`, up to 1000); for the next page send `offset` raised by `limit`, while `offset` + `limit` is below `total_count`.
