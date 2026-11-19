---
name: instagram-api-connector
description: >
  Instagram Graph API (Mock) mock HTTP API. Base URL is provided via the
  `INSTAGRAM_API_URL` environment variable. 12 endpoint(s) across GET, POST.
  Every operation needs an OAuth bearer token that carries the operation's scope.
---

# Instagram Graph API (Mock)

Mock HTTP API. **All requests go to the base URL in `$INSTAGRAM_API_URL`.** Every operation needs a bearer token, and a token covers only the scopes it was issued with: a connected account is not permission for every action. Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `INSTAGRAM_API_URL` | Base URL for all requests (e.g. `http://instagram-api:8102`) |
| `INSTAGRAM_CLIENT_ID` | OAuth client id of the connected account, when the task provides it |
| `INSTAGRAM_CLIENT_SECRET` | OAuth client secret of the connected account, when the task provides it |

## Authentication

1. Exchange the client credentials for an access token: `POST /oauth/token` with `grant_type=client_credentials`, `client_id`, `client_secret`, and optionally `scope` (space-separated). Form-encoded and JSON bodies are both accepted.
2. Send `Authorization: Bearer <access_token>` on every operation.
3. `GET /oauth/tokeninfo` reports the presented token's scopes and expiry.

A token requested without `scope` carries only the default scopes (`instagram_basic`). Ask for any other scope explicitly. A `401 invalid_token` means the token is missing, expired, or revoked; get a new one. A `403 insufficient_scope` names the `required_scope`; request a token that carries it. The token endpoint answers `invalid_scope` when the account never granted a scope to this client. `grant_type=refresh_token` exchanges a refresh token for a new access token.

## Scopes

| Scope | Operations |
|-------|------------|
| `instagram_basic` | GET `/v21.0/me/accounts`, GET `/v21.0/{ig_user_id}`, GET `/v21.0/{ig_user_id}/media` |
| `instagram_content_publish` | POST `/v21.0/{ig_user_id}/media`, POST `/v21.0/{ig_user_id}/media_publish` |
| `instagram_manage_comments` | GET `/v21.0/{media_id}/comments` |
| `instagram_manage_insights` | GET `/v21.0/{ig_user_id}/insights` |
| `instagram_relationships` | GET `/v21.0/{ig_user_id}/followers`, GET `/v21.0/{ig_user_id}/following` |
| `instagram_saved_media` | GET `/v21.0/{ig_user_id}/saved_media` |

## Endpoints

| Method | Path |
|--------|------|
| POST | `/oauth/token` |
| GET | `/oauth/tokeninfo` |
| GET | `/v21.0/me/accounts` |
| GET | `/v21.0/{ig_user_id}` |
| GET | `/v21.0/{ig_user_id}/media` |
| POST | `/v21.0/{ig_user_id}/media` |
| POST | `/v21.0/{ig_user_id}/media_publish` |
| GET | `/v21.0/{ig_user_id}/insights` |
| GET | `/v21.0/{ig_user_id}/saved_media` |
| GET | `/v21.0/{media_id}/comments` |
| GET | `/v21.0/{ig_user_id}/followers` |
| GET | `/v21.0/{ig_user_id}/following` |

## Usage

```bash
TOKEN=$(curl -s -X POST "$INSTAGRAM_API_URL/oauth/token" -d grant_type=client_credentials \
  -d client_id="$INSTAGRAM_CLIENT_ID" -d client_secret="$INSTAGRAM_CLIENT_SECRET" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$INSTAGRAM_API_URL/v21.0/me/accounts" -H "Authorization: Bearer $TOKEN"
```

## Paging

- `GET /v21.0/{ig_user_id}/media` returns 25 per page by default (`limit`, up to 100); when an answer carries `paging.next`, send `paging.cursors.after` as `after` for the next page.
