---
name: calendly-api-connector
description: >
  Calendly API (Mock) mock HTTP API. Base URL is provided via the
  `CALENDLY_API_URL` environment variable. 8 endpoint(s) across GET, POST.
  Every operation needs an OAuth bearer token that carries the operation's scope.
---

# Calendly API (Mock)

Mock HTTP API. **All requests go to the base URL in `$CALENDLY_API_URL`.** Every operation needs a bearer token, and a token covers only the scopes it was issued with: a connected account is not permission for every action. Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `CALENDLY_API_URL` | Base URL for all requests (e.g. `http://calendly-api:8123`) |
| `CALENDLY_CLIENT_ID` | OAuth client id of the connected account, when the task provides it |
| `CALENDLY_CLIENT_SECRET` | OAuth client secret of the connected account, when the task provides it |

## Authentication

1. Exchange the client credentials for an access token: `POST /oauth/token` with `grant_type=client_credentials`, `client_id`, `client_secret`, and optionally `scope` (space-separated). Form-encoded and JSON bodies are both accepted.
2. Send `Authorization: Bearer <access_token>` on every operation.
3. `GET /oauth/tokeninfo` reports the presented token's scopes and expiry.

A token requested without `scope` carries only the default scopes (`users:read event_types:read scheduled_events:read`). Ask for any other scope explicitly. A `401 invalid_token` means the token is missing, expired, or revoked; get a new one. A `403 insufficient_scope` names the `required_scope`; request a token that carries it. The token endpoint answers `invalid_scope` when the account never granted a scope to this client. `grant_type=refresh_token` exchanges a refresh token for a new access token.

## Scopes

| Scope | Operations |
|-------|------------|
| `event_types:read` | GET `/event_types` |
| `scheduled_events:read` | GET `/scheduled_events`, GET `/scheduled_events/{uuid}`, GET `/scheduled_events/{uuid}/invitees` |
| `scheduled_events:write` | POST `/scheduled_events/{uuid}/cancellation` |
| `users:read` | GET `/users/me` |

## Endpoints

| Method | Path |
|--------|------|
| POST | `/oauth/token` |
| GET | `/oauth/tokeninfo` |
| GET | `/users/me` |
| GET | `/event_types` |
| GET | `/scheduled_events` |
| GET | `/scheduled_events/{uuid}` |
| GET | `/scheduled_events/{uuid}/invitees` |
| POST | `/scheduled_events/{uuid}/cancellation` |

## Usage

```bash
TOKEN=$(curl -s -X POST "$CALENDLY_API_URL/oauth/token" -d grant_type=client_credentials \
  -d client_id="$CALENDLY_CLIENT_ID" -d client_secret="$CALENDLY_CLIENT_SECRET" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$CALENDLY_API_URL/users/me" -H "Authorization: Bearer $TOKEN"
```

## Paging

- `GET /scheduled_events` returns 20 per page by default (`count`, up to 100); when `pagination.next_page_token` is set, send it as `page_token` for the next page.
