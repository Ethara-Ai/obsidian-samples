---
name: health-api-connector
description: >
  Health Records API (Mock) mock HTTP API. Base URL is provided via the
  `HEALTH_API_URL` environment variable. 6 endpoint(s) across GET, POST.
  Every operation needs an OAuth bearer token that carries the operation's scope.
---

# Health Records API (Mock)

Mock HTTP API. **All requests go to the base URL in `$HEALTH_API_URL`.** Every operation needs a bearer token, and a token covers only the scopes it was issued with: a connected account is not permission for every action. Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `HEALTH_API_URL` | Base URL for all requests (e.g. `http://health-api:8104`) |
| `HEALTH_CLIENT_ID` | OAuth client id of the connected account, when the task provides it |
| `HEALTH_CLIENT_SECRET` | OAuth client secret of the connected account, when the task provides it |

## Authentication

1. Exchange the client credentials for an access token: `POST /oauth/token` with `grant_type=client_credentials`, `client_id`, `client_secret`, and optionally `scope` (space-separated). Form-encoded and JSON bodies are both accepted.
2. Send `Authorization: Bearer <access_token>` on every operation.
3. `GET /oauth/tokeninfo` reports the presented token's scopes and expiry.

A token requested without `scope` carries only the default scopes (`health.measurements.read`). Ask for any other scope explicitly. A `401 invalid_token` means the token is missing, expired, or revoked; get a new one. A `403 insufficient_scope` names the `required_scope`; request a token that carries it. The token endpoint answers `invalid_scope` when the account never granted a scope to this client. `grant_type=refresh_token` exchanges a refresh token for a new access token.

## Scopes

| Scope | Operations |
|-------|------------|
| `health.measurements.read` | GET `/v1/measurements` |
| `health.nutrition.read` | GET `/v1/nutrition` |
| `health.sleep.read` | GET `/v1/sleep` |
| `health.workouts.read` | GET `/v1/workouts` |

## Endpoints

| Method | Path |
|--------|------|
| POST | `/oauth/token` |
| GET | `/oauth/tokeninfo` |
| GET | `/v1/measurements` |
| GET | `/v1/nutrition` |
| GET | `/v1/sleep` |
| GET | `/v1/workouts` |

## Usage

```bash
TOKEN=$(curl -s -X POST "$HEALTH_API_URL/oauth/token" -d grant_type=client_credentials \
  -d client_id="$HEALTH_CLIENT_ID" -d client_secret="$HEALTH_CLIENT_SECRET" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$HEALTH_API_URL/v1/measurements?type=steps" -H "Authorization: Bearer $TOKEN"
```
