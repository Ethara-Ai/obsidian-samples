---
name: ring-api-connector
description: >
  Ring API (Mock) mock HTTP API. Base URL is provided via the
  `RING_API_URL` environment variable. 7 endpoint(s) across GET, POST, PUT.
  Every operation needs an OAuth bearer token that carries the operation's scope.
---

# Ring API (Mock)

Mock HTTP API. **All requests go to the base URL in `$RING_API_URL`.** Every operation needs a bearer token, and a token covers only the scopes it was issued with: a connected account is not permission for every action. Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `RING_API_URL` | Base URL for all requests (e.g. `http://ring-api:8132`) |
| `RING_CLIENT_ID` | OAuth client id of the connected account, when the task provides it |
| `RING_CLIENT_SECRET` | OAuth client secret of the connected account, when the task provides it |

## Authentication

1. Exchange the client credentials for an access token: `POST /oauth/token` with `grant_type=client_credentials`, `client_id`, `client_secret`, and optionally `scope` (space-separated). Form-encoded and JSON bodies are both accepted.
2. Send `Authorization: Bearer <access_token>` on every operation.
3. `GET /oauth/tokeninfo` reports the presented token's scopes and expiry.

A token requested without `scope` carries only the default scopes (`devices.read history.read`). Ask for any other scope explicitly. A `401 invalid_token` means the token is missing, expired, or revoked; get a new one. A `403 insufficient_scope` names the `required_scope`; request a token that carries it. The token endpoint answers `invalid_scope` when the account never granted a scope to this client. `grant_type=refresh_token` exchanges a refresh token for a new access token.

## Scopes

| Scope | Operations |
|-------|------------|
| `alarm.control` | PUT `/api/v1/mode/location/{location_id}` |
| `devices.read` | GET `/clients_api/ring_devices`, GET `/clients_api/doorbots/{device_id}/health` |
| `history.read` | GET `/clients_api/doorbots/{device_id}/history`, GET `/clients_api/dings/{ding_id}/recording` |

## Endpoints

| Method | Path |
|--------|------|
| POST | `/oauth/token` |
| GET | `/oauth/tokeninfo` |
| GET | `/clients_api/ring_devices` |
| GET | `/clients_api/doorbots/{device_id}/health` |
| GET | `/clients_api/doorbots/{device_id}/history` |
| GET | `/clients_api/dings/{ding_id}/recording` |
| PUT | `/api/v1/mode/location/{location_id}` |

## Usage

```bash
TOKEN=$(curl -s -X POST "$RING_API_URL/oauth/token" -d grant_type=client_credentials \
  -d client_id="$RING_CLIENT_ID" -d client_secret="$RING_CLIENT_SECRET" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$RING_API_URL/clients_api/ring_devices" -H "Authorization: Bearer $TOKEN"
```

## Paging

- `GET /clients_api/doorbots/{device_id}/history` returns 20 per page by default (`limit`, up to 100); for older events send the `id` of the last event shown as `older_than`.
