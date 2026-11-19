---
name: outlook-contacts-api-connector
description: >
  Outlook Contacts API (Mock) mock HTTP API. Base URL is provided via the
  `OUTLOOK_CONTACTS_API_URL` environment variable. 7 endpoint(s) across DELETE, GET, PATCH, POST.
  Every operation needs an OAuth bearer token that carries the operation's scope.
---

# Outlook Contacts API (Mock)

Mock HTTP API. **All requests go to the base URL in `$OUTLOOK_CONTACTS_API_URL`.** Every operation needs a bearer token, and a token covers only the scopes it was issued with: a connected account is not permission for every action. Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `OUTLOOK_CONTACTS_API_URL` | Base URL for all requests (e.g. `http://outlook-contacts-api:8121`) |
| `OUTLOOK_CONTACTS_CLIENT_ID` | OAuth client id of the connected account, when the task provides it |
| `OUTLOOK_CONTACTS_CLIENT_SECRET` | OAuth client secret of the connected account, when the task provides it |

## Authentication

1. Exchange the client credentials for an access token: `POST /oauth/token` with `grant_type=client_credentials`, `client_id`, `client_secret`, and optionally `scope` (space-separated). Form-encoded and JSON bodies are both accepted.
2. Send `Authorization: Bearer <access_token>` on every operation.
3. `GET /oauth/tokeninfo` reports the presented token's scopes and expiry.

A token requested without `scope` carries only the default scopes (`Contacts.Read`). Ask for any other scope explicitly. A `401 invalid_token` means the token is missing, expired, or revoked; get a new one. A `403 insufficient_scope` names the `required_scope`; request a token that carries it. The token endpoint answers `invalid_scope` when the account never granted a scope to this client. `grant_type=refresh_token` exchanges a refresh token for a new access token.

## Scopes

| Scope | Operations |
|-------|------------|
| `Contacts.Read` | GET `/v1.0/me/contacts`, GET `/v1.0/me/contacts/{contact_id}` |
| `Contacts.ReadWrite` | POST `/v1.0/me/contacts`, PATCH `/v1.0/me/contacts/{contact_id}`, DELETE `/v1.0/me/contacts/{contact_id}` |

## Endpoints

| Method | Path |
|--------|------|
| POST | `/oauth/token` |
| GET | `/oauth/tokeninfo` |
| GET | `/v1.0/me/contacts` |
| GET | `/v1.0/me/contacts/{contact_id}` |
| POST | `/v1.0/me/contacts` |
| PATCH | `/v1.0/me/contacts/{contact_id}` |
| DELETE | `/v1.0/me/contacts/{contact_id}` |

## Usage

```bash
TOKEN=$(curl -s -X POST "$OUTLOOK_CONTACTS_API_URL/oauth/token" -d grant_type=client_credentials \
  -d client_id="$OUTLOOK_CONTACTS_CLIENT_ID" -d client_secret="$OUTLOOK_CONTACTS_CLIENT_SECRET" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$OUTLOOK_CONTACTS_API_URL/v1.0/me/contacts?%24filter=startswith(displayName,'Diego')&%24select=displayName,emailAddresses,mobilePhone" -H "Authorization: Bearer $TOKEN"
```

## Paging

- `GET /v1.0/me/contacts` returns 10 per page by default (`$top`, up to 1000); when an answer carries `@odata.nextLink`, request that URL for the next page.
