---
name: google-slides-api-connector
description: >
  Google Slides API (Mock) mock HTTP API. Base URL is provided via the
  `GOOGLE_SLIDES_API_URL` environment variable. 6 endpoint(s) across GET, POST.
  Every operation needs an OAuth bearer token that carries the operation's scope.
---

# Google Slides API (Mock)

Mock HTTP API. **All requests go to the base URL in `$GOOGLE_SLIDES_API_URL`.** Every operation needs a bearer token, and a token covers only the scopes it was issued with: a connected account is not permission for every action. Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `GOOGLE_SLIDES_API_URL` | Base URL for all requests (e.g. `http://google-slides-api:8118`) |
| `GOOGLE_SLIDES_CLIENT_ID` | OAuth client id of the connected account, when the task provides it |
| `GOOGLE_SLIDES_CLIENT_SECRET` | OAuth client secret of the connected account, when the task provides it |

## Authentication

1. Exchange the client credentials for an access token: `POST /oauth/token` with `grant_type=client_credentials`, `client_id`, `client_secret`, and optionally `scope` (space-separated). Form-encoded and JSON bodies are both accepted.
2. Send `Authorization: Bearer <access_token>` on every operation.
3. `GET /oauth/tokeninfo` reports the presented token's scopes and expiry.

A token requested without `scope` carries only the default scopes (`presentations.readonly`). Ask for any other scope explicitly. A `401 invalid_token` means the token is missing, expired, or revoked; get a new one. A `403 insufficient_scope` names the `required_scope`; request a token that carries it. The token endpoint answers `invalid_scope` when the account never granted a scope to this client. `grant_type=refresh_token` exchanges a refresh token for a new access token.

## Scopes

| Scope | Operations |
|-------|------------|
| `presentations` | POST `/v1/presentations`, POST `/v1/presentations/{presentationId}:batchUpdate` |
| `presentations.readonly` | GET `/v1/presentations/{presentationId}`, GET `/v1/presentations/{presentationId}/pages/{pageObjectId}` |

A token carrying `presentations` also covers every `presentations.readonly` operation, so it does not need `presentations.readonly` as well. A token carrying only `presentations.readonly` cannot do the `presentations` operations.

## Endpoints

| Method | Path |
|--------|------|
| POST | `/oauth/token` |
| GET | `/oauth/tokeninfo` |
| GET | `/v1/presentations/{presentationId}` |
| GET | `/v1/presentations/{presentationId}/pages/{pageObjectId}` |
| POST | `/v1/presentations` |
| POST | `/v1/presentations/{presentationId}:batchUpdate` |

## Usage

```bash
TOKEN=$(curl -s -X POST "$GOOGLE_SLIDES_API_URL/oauth/token" -d grant_type=client_credentials \
  -d client_id="$GOOGLE_SLIDES_CLIENT_ID" -d client_secret="$GOOGLE_SLIDES_CLIENT_SECRET" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$GOOGLE_SLIDES_API_URL/v1/presentations/1LHzfmVr0d7fHB8OFkeAIdDyECSVI331nM" -H "Authorization: Bearer $TOKEN"
```
