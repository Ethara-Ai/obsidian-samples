---
name: opentable-api-connector
description: >
  OpenTable API (Mock) mock HTTP API. Base URL is provided via the
  `OPENTABLE_API_URL` environment variable. 8 endpoint(s) across DELETE, GET, POST.
  Every operation needs an OAuth bearer token that carries the operation's scope.
---

# OpenTable API (Mock)

Mock HTTP API. **All requests go to the base URL in `$OPENTABLE_API_URL`.** Every operation needs a bearer token, and a token covers only the scopes it was issued with: a connected account is not permission for every action. Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `OPENTABLE_API_URL` | Base URL for all requests (e.g. `http://opentable-api:8114`) |
| `OPENTABLE_CLIENT_ID` | OAuth client id of the connected account, when the task provides it |
| `OPENTABLE_CLIENT_SECRET` | OAuth client secret of the connected account, when the task provides it |

## Authentication

1. Exchange the client credentials for an access token: `POST /oauth/token` with `grant_type=client_credentials`, `client_id`, `client_secret`, and optionally `scope` (space-separated). Form-encoded and JSON bodies are both accepted.
2. Send `Authorization: Bearer <access_token>` on every operation.
3. `GET /oauth/tokeninfo` reports the presented token's scopes and expiry.

A token requested without `scope` carries only the default scopes (`directory.read availability.read reservations.read`). Ask for any other scope explicitly. A `401 invalid_token` means the token is missing, expired, or revoked; get a new one. A `403 insufficient_scope` names the `required_scope`; request a token that carries it. The token endpoint answers `invalid_scope` when the account never granted a scope to this client. `grant_type=refresh_token` exchanges a refresh token for a new access token.

## Scopes

| Scope | Operations |
|-------|------------|
| `availability.read` | GET `/v2/availability/{rid}` |
| `directory.read` | GET `/v2/directory/restaurants` |
| `reservations.read` | GET `/v2/booking/{rid}/reservations/{confirmation_number}` |
| `reservations.write` | POST `/v2/booking/{rid}/slot_locks`, POST `/v2/booking/{rid}/reservations`, DELETE `/v2/booking/{rid}/reservations/{confirmation_number}` |

## Endpoints

| Method | Path |
|--------|------|
| POST | `/oauth/token` |
| GET | `/oauth/tokeninfo` |
| GET | `/v2/directory/restaurants` |
| GET | `/v2/availability/{rid}` |
| POST | `/v2/booking/{rid}/slot_locks` |
| POST | `/v2/booking/{rid}/reservations` |
| GET | `/v2/booking/{rid}/reservations/{confirmation_number}` |
| DELETE | `/v2/booking/{rid}/reservations/{confirmation_number}` |

## Usage

```bash
TOKEN=$(curl -s -X POST "$OPENTABLE_API_URL/oauth/token" -d grant_type=client_credentials \
  -d client_id="$OPENTABLE_CLIENT_ID" -d client_secret="$OPENTABLE_CLIENT_SECRET" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$OPENTABLE_API_URL/v2/directory/restaurants?city=Chicago&cuisine=Italian" -H "Authorization: Bearer $TOKEN"
```

## Paging

- `GET /v2/directory/restaurants` returns 20 per page by default (`limit`, up to 100); for the next page send `offset` raised by `limit`, while `offset` + `limit` is below `total_count`.
