---
name: tessie-api-connector
description: >
  Tessie API (Mock) mock HTTP API. Base URL is provided via the
  `TESSIE_API_URL` environment variable. 13 endpoint(s) across GET, POST.
  Every operation needs an OAuth bearer token that carries the operation's scope.
---

# Tessie API (Mock)

Mock HTTP API. **All requests go to the base URL in `$TESSIE_API_URL`.** Every operation needs a bearer token, and a token covers only the scopes it was issued with: a connected account is not permission for every action. Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `TESSIE_API_URL` | Base URL for all requests (e.g. `http://tessie-api:8133`) |
| `TESSIE_CLIENT_ID` | OAuth client id of the connected account, when the task provides it |
| `TESSIE_CLIENT_SECRET` | OAuth client secret of the connected account, when the task provides it |

## Authentication

1. Exchange the client credentials for an access token: `POST /oauth/token` with `grant_type=client_credentials`, `client_id`, `client_secret`, and optionally `scope` (space-separated). Form-encoded and JSON bodies are both accepted.
2. Send `Authorization: Bearer <access_token>` on every operation.
3. `GET /oauth/tokeninfo` reports the presented token's scopes and expiry.

A token requested without `scope` carries only the default scopes (`vehicle_device_data vehicle_location`). Ask for any other scope explicitly. A `401 invalid_token` means the token is missing, expired, or revoked; get a new one. A `403 insufficient_scope` names the `required_scope`; request a token that carries it. The token endpoint answers `invalid_scope` when the account never granted a scope to this client. `grant_type=refresh_token` exchanges a refresh token for a new access token.

## Scopes

| Scope | Operations |
|-------|------------|
| `vehicle_charging_cmds` | POST `/{vin}/command/start_charging`, POST `/{vin}/command/stop_charging` |
| `vehicle_cmds` | POST `/{vin}/command/lock`, POST `/{vin}/command/unlock`, POST `/{vin}/command/start_climate`, POST `/{vin}/command/stop_climate` |
| `vehicle_device_data` | GET `/vehicles`, GET `/{vin}/state`, GET `/{vin}/battery` |
| `vehicle_location` | GET `/{vin}/location`, GET `/{vin}/drives` |

## Endpoints

| Method | Path |
|--------|------|
| POST | `/oauth/token` |
| GET | `/oauth/tokeninfo` |
| GET | `/vehicles` |
| GET | `/{vin}/state` |
| GET | `/{vin}/battery` |
| GET | `/{vin}/location` |
| GET | `/{vin}/drives` |
| POST | `/{vin}/command/lock` |
| POST | `/{vin}/command/unlock` |
| POST | `/{vin}/command/start_climate` |
| POST | `/{vin}/command/stop_climate` |
| POST | `/{vin}/command/start_charging` |
| POST | `/{vin}/command/stop_charging` |

## Usage

```bash
TOKEN=$(curl -s -X POST "$TESSIE_API_URL/oauth/token" -d grant_type=client_credentials \
  -d client_id="$TESSIE_CLIENT_ID" -d client_secret="$TESSIE_CLIENT_SECRET" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$TESSIE_API_URL/vehicles" -H "Authorization: Bearer $TOKEN"
```
