---
name: google-forms-api-connector
description: >
  Google Forms API (Mock) mock HTTP API. Base URL is provided via the
  `GOOGLE_FORMS_API_URL` environment variable. 7 endpoint(s) across GET, POST.
  Every operation needs an OAuth bearer token that carries the operation's scope.
---

# Google Forms API (Mock)

Mock HTTP API. **All requests go to the base URL in `$GOOGLE_FORMS_API_URL`.** Every operation needs a bearer token, and a token covers only the scopes it was issued with: a connected account is not permission for every action. Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `GOOGLE_FORMS_API_URL` | Base URL for all requests (e.g. `http://google-forms-api:8117`) |
| `GOOGLE_FORMS_CLIENT_ID` | OAuth client id of the connected account, when the task provides it |
| `GOOGLE_FORMS_CLIENT_SECRET` | OAuth client secret of the connected account, when the task provides it |

## Authentication

1. Exchange the client credentials for an access token: `POST /oauth/token` with `grant_type=client_credentials`, `client_id`, `client_secret`, and optionally `scope` (space-separated). Form-encoded and JSON bodies are both accepted.
2. Send `Authorization: Bearer <access_token>` on every operation.
3. `GET /oauth/tokeninfo` reports the presented token's scopes and expiry.

A token requested without `scope` carries only the default scopes (`forms.body.readonly forms.responses.readonly`). Ask for any other scope explicitly. A `401 invalid_token` means the token is missing, expired, or revoked; get a new one. A `403 insufficient_scope` names the `required_scope`; request a token that carries it. The token endpoint answers `invalid_scope` when the account never granted a scope to this client. `grant_type=refresh_token` exchanges a refresh token for a new access token.

## Scopes

| Scope | Operations |
|-------|------------|
| `forms.body` | POST `/v1/forms`, POST `/v1/forms/{formId}:batchUpdate` |
| `forms.body.readonly` | GET `/v1/forms/{formId}` |
| `forms.responses.readonly` | GET `/v1/forms/{formId}/responses`, GET `/v1/forms/{formId}/responses/{responseId}` |

A token carrying `forms.body` also covers every `forms.body.readonly` operation, so it does not need `forms.body.readonly` as well. A token carrying only `forms.body.readonly` cannot do the `forms.body` operations.

## Endpoints

| Method | Path |
|--------|------|
| POST | `/oauth/token` |
| GET | `/oauth/tokeninfo` |
| GET | `/v1/forms/{formId}` |
| POST | `/v1/forms` |
| POST | `/v1/forms/{formId}:batchUpdate` |
| GET | `/v1/forms/{formId}/responses` |
| GET | `/v1/forms/{formId}/responses/{responseId}` |

## Usage

```bash
TOKEN=$(curl -s -X POST "$GOOGLE_FORMS_API_URL/oauth/token" -d grant_type=client_credentials \
  -d client_id="$GOOGLE_FORMS_CLIENT_ID" -d client_secret="$GOOGLE_FORMS_CLIENT_SECRET" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$GOOGLE_FORMS_API_URL/v1/forms/1Snliw-QCNZNy5tkr7Ly6rLJLKASQVtaEz0V3G5F4HuT" -H "Authorization: Bearer $TOKEN"
```

## Paging

- `GET /v1/forms/{formId}/responses` returns 5000 per page by default (`pageSize`, up to 5000); when an answer carries `nextPageToken`, send it back as `pageToken` for the next page.
