---
name: withings-api-connector
description: >
  Withings API (Mock) mock HTTP API. Base URL is provided via the
  `WITHINGS_API_URL` environment variable. 6 endpoint(s) across GET, POST.
  Every operation needs an OAuth bearer token that carries the operation's scope.
---

# Withings API (Mock)

Mock HTTP API. **All requests go to the base URL in `$WITHINGS_API_URL`.** Every operation needs a bearer token, and a token covers only the scopes it was issued with: a connected account is not permission for every action. Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `WITHINGS_API_URL` | Base URL for all requests (e.g. `http://withings-api:8135`) |
| `WITHINGS_CLIENT_ID` | OAuth client id of the connected account, when the task provides it |
| `WITHINGS_CLIENT_SECRET` | OAuth client secret of the connected account, when the task provides it |

## Authentication

1. Exchange the client credentials for an access token: `POST /oauth/token` with `grant_type=client_credentials`, `client_id`, `client_secret`, and optionally `scope` (space-separated). Form-encoded and JSON bodies are both accepted.
2. Send `Authorization: Bearer <access_token>` on every operation.
3. `GET /oauth/tokeninfo` reports the presented token's scopes and expiry.

A token requested without `scope` carries only the default scopes (`user.metrics user.activity user.info`). Ask for any other scope explicitly. A `401 invalid_token` means the token is missing, expired, or revoked; get a new one. A `403 insufficient_scope` names the `required_scope`; request a token that carries it. The token endpoint answers `invalid_scope` when the account never granted a scope to this client. `grant_type=refresh_token` exchanges a refresh token for a new access token.

## Scopes

| Scope | Operations |
|-------|------------|
| `user.activity` | POST `/v2/measure`, POST `/v2/sleep` |
| `user.info` | POST `/v2/user` |
| `user.metrics` | POST `/measure` |

## Endpoints

| Method | Path |
|--------|------|
| POST | `/oauth/token` |
| GET | `/oauth/tokeninfo` |
| POST | `/measure` |
| POST | `/v2/measure` |
| POST | `/v2/sleep` |
| POST | `/v2/user` |

## Usage

```bash
TOKEN=$(curl -s -X POST "$WITHINGS_API_URL/oauth/token" -d grant_type=client_credentials \
  -d client_id="$WITHINGS_CLIENT_ID" -d client_secret="$WITHINGS_CLIENT_SECRET" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s -X POST "$WITHINGS_API_URL/measure" -H "Authorization: Bearer $TOKEN" -d action=getmeas -d meastypes=1,6,8 -d category=1 -d startdate=1788238800 -d enddate=1790830799
```

## Paging

- `POST /measure` (`action=getmeas`) returns 100 per page by default; when `body.more` is 1, send `body.offset` back as the `offset` form field for the next page.
- `POST /v2/measure` (`action=getactivity`) returns 50 per page by default; when `body.more` is true, send `body.offset` back as the `offset` form field for the next page.
