---
name: notion-api-connector
description: >
  Notion API (Mock) mock HTTP API. Base URL is provided via the
  `NOTION_API_URL` environment variable. 9 endpoint(s) across GET, PATCH, POST.
  Every operation needs an OAuth bearer token that carries the operation's scope.
---

# Notion API (Mock)

Mock HTTP API. **All requests go to the base URL in `$NOTION_API_URL`.** Every operation needs a bearer token, and a token covers only the scopes it was issued with: a connected account is not permission for every action. Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `NOTION_API_URL` | Base URL for all requests (e.g. `http://notion-api:8122`) |
| `NOTION_CLIENT_ID` | OAuth client id of the connected account, when the task provides it |
| `NOTION_CLIENT_SECRET` | OAuth client secret of the connected account, when the task provides it |

## Authentication

1. Exchange the client credentials for an access token: `POST /oauth/token` with `grant_type=client_credentials`, `client_id`, `client_secret`, and optionally `scope` (space-separated). Form-encoded and JSON bodies are both accepted.
2. Send `Authorization: Bearer <access_token>` on every operation.
3. `GET /oauth/tokeninfo` reports the presented token's scopes and expiry.

A token requested without `scope` carries only the default scopes (`read_content`). Ask for any other scope explicitly. A `401 invalid_token` means the token is missing, expired, or revoked; get a new one. A `403 insufficient_scope` names the `required_scope`; request a token that carries it. The token endpoint answers `invalid_scope` when the account never granted a scope to this client. `grant_type=refresh_token` exchanges a refresh token for a new access token.

## Scopes

| Scope | Operations |
|-------|------------|
| `insert_content` | POST `/v1/pages`, PATCH `/v1/blocks/{block_id}/children` |
| `read_content` | POST `/v1/search`, GET `/v1/pages/{page_id}`, POST `/v1/databases/{database_id}/query`, GET `/v1/blocks/{block_id}/children` |
| `update_content` | PATCH `/v1/pages/{page_id}` |

## Endpoints

| Method | Path |
|--------|------|
| POST | `/oauth/token` |
| GET | `/oauth/tokeninfo` |
| POST | `/v1/search` |
| GET | `/v1/pages/{page_id}` |
| POST | `/v1/pages` |
| PATCH | `/v1/pages/{page_id}` |
| POST | `/v1/databases/{database_id}/query` |
| GET | `/v1/blocks/{block_id}/children` |
| PATCH | `/v1/blocks/{block_id}/children` |

## Usage

```bash
TOKEN=$(curl -s -X POST "$NOTION_API_URL/oauth/token" -d grant_type=client_credentials \
  -d client_id="$NOTION_CLIENT_ID" -d client_secret="$NOTION_CLIENT_SECRET" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s -X POST "$NOTION_API_URL/v1/search" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"query": "Projects", "filter": {"property": "object", "value": "database"}}'
```

## Paging

- `POST /v1/search` returns 100 per page by default (`page_size` in the body, up to 100); when `has_more` is true, send `next_cursor` as `start_cursor` in the next request's body.
- `GET /v1/blocks/{block_id}/children` returns 100 per page by default (`page_size`, up to 100); when `has_more` is true, send `next_cursor` as the `start_cursor` query parameter.
