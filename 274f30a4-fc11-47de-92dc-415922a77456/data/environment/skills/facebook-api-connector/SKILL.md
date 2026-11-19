---
name: facebook-api-connector
description: >
  Facebook Graph API (Mock) mock HTTP API. Base URL is provided via the
  `FACEBOOK_API_URL` environment variable. 14 endpoint(s) across GET, POST.
  Every operation needs an OAuth bearer token that carries the operation's scope.
---

# Facebook Graph API (Mock)

Mock HTTP API. **All requests go to the base URL in `$FACEBOOK_API_URL`.** Every operation needs a bearer token, and a token covers only the scopes it was issued with: a connected account is not permission for every action. Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `FACEBOOK_API_URL` | Base URL for all requests (e.g. `http://facebook-api:8103`) |
| `FACEBOOK_CLIENT_ID` | OAuth client id of the connected account, when the task provides it |
| `FACEBOOK_CLIENT_SECRET` | OAuth client secret of the connected account, when the task provides it |

## Authentication

1. Exchange the client credentials for an access token: `POST /oauth/token` with `grant_type=client_credentials`, `client_id`, `client_secret`, and optionally `scope` (space-separated). Form-encoded and JSON bodies are both accepted.
2. Send `Authorization: Bearer <access_token>` on every operation.
3. `GET /oauth/tokeninfo` reports the presented token's scopes and expiry.

A token requested without `scope` carries only the default scopes (`public_profile`). Ask for any other scope explicitly. A `401 invalid_token` means the token is missing, expired, or revoked; get a new one. A `403 insufficient_scope` names the `required_scope`; request a token that carries it. The token endpoint answers `invalid_scope` when the account never granted a scope to this client. `grant_type=refresh_token` exchanges a refresh token for a new access token.

## Scopes

| Scope | Operations |
|-------|------------|
| `groups_access_member_info` | GET `/v21.0/me/groups`, GET `/v21.0/{group_id}/feed` |
| `marketplace_listings` | GET `/v21.0/marketplace_listings`, GET `/v21.0/marketplace_listings/{listing_id}` |
| `public_profile` | GET `/v21.0/me`, GET `/v21.0/{user_id}` |
| `publish_actions` | POST `/v21.0/me/feed` |
| `user_feed` | GET `/v21.0/me/home` |
| `user_posts` | GET `/v21.0/me/feed`, GET `/v21.0/posts`, GET `/v21.0/{owner_id}_{post_suffix}` |
| `user_saved` | GET `/v21.0/me/saved` |

## Endpoints

| Method | Path |
|--------|------|
| POST | `/oauth/token` |
| GET | `/oauth/tokeninfo` |
| GET | `/v21.0/me` |
| GET | `/v21.0/me/feed` |
| POST | `/v21.0/me/feed` |
| GET | `/v21.0/me/home` |
| GET | `/v21.0/me/groups` |
| GET | `/v21.0/{group_id}/feed` |
| GET | `/v21.0/me/saved` |
| GET | `/v21.0/marketplace_listings` |
| GET | `/v21.0/marketplace_listings/{listing_id}` |
| GET | `/v21.0/posts` |
| GET | `/v21.0/{owner_id}_{post_suffix}` |
| GET | `/v21.0/{user_id}` |

## Usage

```bash
TOKEN=$(curl -s -X POST "$FACEBOOK_API_URL/oauth/token" -d grant_type=client_credentials \
  -d client_id="$FACEBOOK_CLIENT_ID" -d client_secret="$FACEBOOK_CLIENT_SECRET" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$FACEBOOK_API_URL/v21.0/me" -H "Authorization: Bearer $TOKEN"
```

## Paging

- `GET /v21.0/me/feed` returns 25 per page by default (`limit`, up to 100); when an answer carries `paging.next`, send `paging.cursors.after` as `after` for the next page.
