---
name: tailscale-api-connector
description: >
  Tailscale API (Mock) mock HTTP API. Base URL is provided via the
  `TAILSCALE_API_URL` environment variable. 9 endpoint(s) across DELETE, GET, POST.
  Every operation needs an OAuth bearer token that carries the operation's scope.
---

# Tailscale API (Mock)

Mock HTTP API. **All requests go to the base URL in `$TAILSCALE_API_URL`.** Every operation needs a bearer token, and a token covers only the scopes it was issued with: a connected account is not permission for every action. Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `TAILSCALE_API_URL` | Base URL for all requests (e.g. `http://tailscale-api:8127`) |
| `TAILSCALE_CLIENT_ID` | OAuth client id of the connected account, when the task provides it |
| `TAILSCALE_CLIENT_SECRET` | OAuth client secret of the connected account, when the task provides it |

## Authentication

1. Exchange the client credentials for an access token: `POST /oauth/token` with `grant_type=client_credentials`, `client_id`, `client_secret`, and optionally `scope` (space-separated). Form-encoded and JSON bodies are both accepted.
2. Send `Authorization: Bearer <access_token>` on every operation.
3. `GET /oauth/tokeninfo` reports the presented token's scopes and expiry.

A token requested without `scope` carries only the default scopes (`devices:core:read policy_file:read auth_keys:read`). Ask for any other scope explicitly. A `401 invalid_token` means the token is missing, expired, or revoked; get a new one. A `403 insufficient_scope` names the `required_scope`; request a token that carries it. The token endpoint answers `invalid_scope` when the account never granted a scope to this client. `grant_type=refresh_token` exchanges a refresh token for a new access token.

## Scopes

| Scope | Operations |
|-------|------------|
| `auth_keys` | POST `/api/v2/tailnet/{tailnet}/keys` |
| `auth_keys:read` | GET `/api/v2/tailnet/{tailnet}/keys/{key_id}` |
| `devices:core` | POST `/api/v2/device/{device_id}/authorized`, DELETE `/api/v2/device/{device_id}` |
| `devices:core:read` | GET `/api/v2/tailnet/{tailnet}/devices`, GET `/api/v2/device/{device_id}` |
| `policy_file:read` | GET `/api/v2/tailnet/{tailnet}/acl` |

## Endpoints

| Method | Path |
|--------|------|
| POST | `/oauth/token` |
| GET | `/oauth/tokeninfo` |
| GET | `/api/v2/tailnet/{tailnet}/devices` |
| GET | `/api/v2/device/{device_id}` |
| POST | `/api/v2/device/{device_id}/authorized` |
| DELETE | `/api/v2/device/{device_id}` |
| GET | `/api/v2/tailnet/{tailnet}/acl` |
| POST | `/api/v2/tailnet/{tailnet}/keys` |
| GET | `/api/v2/tailnet/{tailnet}/keys/{key_id}` |

## Usage

```bash
TOKEN=$(curl -s -X POST "$TAILSCALE_API_URL/oauth/token" -d grant_type=client_credentials \
  -d client_id="$TAILSCALE_CLIENT_ID" -d client_secret="$TAILSCALE_CLIENT_SECRET" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$TAILSCALE_API_URL/api/v2/tailnet/-/devices" -H "Authorization: Bearer $TOKEN"
```
