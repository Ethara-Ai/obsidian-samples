---
name: google-sheets-api-connector
description: >
  Google Sheets API (Mock) mock HTTP API. Base URL is provided via the
  `GOOGLE_SHEETS_API_URL` environment variable. 7 endpoint(s) across GET, POST, PUT.
  Every operation needs an OAuth bearer token that carries the operation's scope.
---

# Google Sheets API (Mock)

Mock HTTP API. **All requests go to the base URL in `$GOOGLE_SHEETS_API_URL`.** Every operation needs a bearer token, and a token covers only the scopes it was issued with: a connected account is not permission for every action. Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `GOOGLE_SHEETS_API_URL` | Base URL for all requests (e.g. `http://google-sheets-api:8111`) |
| `GOOGLE_SHEETS_CLIENT_ID` | OAuth client id of the connected account, when the task provides it |
| `GOOGLE_SHEETS_CLIENT_SECRET` | OAuth client secret of the connected account, when the task provides it |

## Authentication

1. Exchange the client credentials for an access token: `POST /oauth/token` with `grant_type=client_credentials`, `client_id`, `client_secret`, and optionally `scope` (space-separated). Form-encoded and JSON bodies are both accepted.
2. Send `Authorization: Bearer <access_token>` on every operation.
3. `GET /oauth/tokeninfo` reports the presented token's scopes and expiry.

A token requested without `scope` carries only the default scopes (`spreadsheets.readonly`). Ask for any other scope explicitly. A `401 invalid_token` means the token is missing, expired, or revoked; get a new one. A `403 insufficient_scope` names the `required_scope`; request a token that carries it. The token endpoint answers `invalid_scope` when the account never granted a scope to this client. `grant_type=refresh_token` exchanges a refresh token for a new access token.

## Scopes

| Scope | Operations |
|-------|------------|
| `spreadsheets` | PUT `/v4/spreadsheets/{spreadsheetId}/values/{range}`, POST `/v4/spreadsheets/{spreadsheetId}/values/{range}:append`, POST `/v4/spreadsheets` |
| `spreadsheets.readonly` | GET `/v4/spreadsheets/{spreadsheetId}`, GET `/v4/spreadsheets/{spreadsheetId}/values/{range}` |

A token carrying `spreadsheets` also covers every `spreadsheets.readonly` operation, so it does not need `spreadsheets.readonly` as well. A token carrying only `spreadsheets.readonly` cannot do the `spreadsheets` operations.

## Endpoints

| Method | Path |
|--------|------|
| POST | `/oauth/token` |
| GET | `/oauth/tokeninfo` |
| GET | `/v4/spreadsheets/{spreadsheetId}` |
| GET | `/v4/spreadsheets/{spreadsheetId}/values/{range}` |
| PUT | `/v4/spreadsheets/{spreadsheetId}/values/{range}` |
| POST | `/v4/spreadsheets/{spreadsheetId}/values/{range}:append` |
| POST | `/v4/spreadsheets` |

## Usage

```bash
TOKEN=$(curl -s -X POST "$GOOGLE_SHEETS_API_URL/oauth/token" -d grant_type=client_credentials \
  -d client_id="$GOOGLE_SHEETS_CLIENT_ID" -d client_secret="$GOOGLE_SHEETS_CLIENT_SECRET" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$GOOGLE_SHEETS_API_URL/v4/spreadsheets/17MhG1mZB-ymy5rKz_r69BAEGny1KAOziv" -H "Authorization: Bearer $TOKEN"
```
