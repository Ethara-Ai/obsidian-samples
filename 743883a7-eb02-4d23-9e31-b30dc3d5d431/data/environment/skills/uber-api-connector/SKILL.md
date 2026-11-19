---
name: uber-api-connector
description: >
  Uber Rides API (Mock) mock HTTP API. Base URL is provided via the
  `UBER_API_URL` environment variable. 9 endpoint(s) across DELETE, GET, POST.
  Every operation needs an OAuth bearer token that carries the operation's scope.
---

# Uber Rides API (Mock)

Mock HTTP API. **All requests go to the base URL in `$UBER_API_URL`.** Every operation needs a bearer token, and a token covers only the scopes it was issued with: a connected account is not permission for every action. Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `UBER_API_URL` | Base URL for all requests (e.g. `http://uber-api:8115`) |
| `UBER_CLIENT_ID` | OAuth client id of the connected account, when the task provides it |
| `UBER_CLIENT_SECRET` | OAuth client secret of the connected account, when the task provides it |

## Authentication

1. Exchange the client credentials for an access token: `POST /oauth/token` with `grant_type=client_credentials`, `client_id`, `client_secret`, and optionally `scope` (space-separated). Form-encoded and JSON bodies are both accepted.
2. Send `Authorization: Bearer <access_token>` on every operation.
3. `GET /oauth/tokeninfo` reports the presented token's scopes and expiry.

A token requested without `scope` carries only the default scopes (`ride_request.estimate all_trips history`). Ask for any other scope explicitly. A `401 invalid_token` means the token is missing, expired, or revoked; get a new one. A `403 insufficient_scope` names the `required_scope`; request a token that carries it. The token endpoint answers `invalid_scope` when the account never granted a scope to this client. `grant_type=refresh_token` exchanges a refresh token for a new access token.

## Scopes

| Scope | Operations |
|-------|------------|
| `all_trips` | GET `/v1.2/requests/{request_id}` |
| `history` | GET `/v1.2/history` |
| `request` | POST `/v1.2/requests`, DELETE `/v1.2/requests/{request_id}` |
| `ride_request.estimate` | GET `/v1.2/products`, GET `/v1.2/estimates/price`, GET `/v1.2/estimates/time` |

## Endpoints

| Method | Path |
|--------|------|
| POST | `/oauth/token` |
| GET | `/oauth/tokeninfo` |
| GET | `/v1.2/products` |
| GET | `/v1.2/estimates/price` |
| GET | `/v1.2/estimates/time` |
| POST | `/v1.2/requests` |
| GET | `/v1.2/requests/{request_id}` |
| DELETE | `/v1.2/requests/{request_id}` |
| GET | `/v1.2/history` |

## Usage

```bash
TOKEN=$(curl -s -X POST "$UBER_API_URL/oauth/token" -d grant_type=client_credentials \
  -d client_id="$UBER_CLIENT_ID" -d client_secret="$UBER_CLIENT_SECRET" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$UBER_API_URL/v1.2/products?latitude=41.9147&longitude=-87.6826" -H "Authorization: Bearer $TOKEN"
```

## Paging

- `GET /v1.2/history` returns 5 per page by default (`limit`, up to 50); for the next page send `offset` raised by `limit`, while `offset` + `limit` is below `count`.
