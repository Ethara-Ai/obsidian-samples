---
name: google-contacts-api-connector
description: >
  Google Contacts API (Mock) mock HTTP API. Base URL is provided via the
  `GOOGLE_CONTACTS_API_URL` environment variable. 8 endpoint(s) across DELETE, GET, PATCH, POST.
  Every operation needs an OAuth bearer token that carries the operation's scope.
---

# Google Contacts API (Mock)

Mock HTTP API. **All requests go to the base URL in `$GOOGLE_CONTACTS_API_URL`.** Every operation needs a bearer token, and a token covers only the scopes it was issued with: a connected account is not permission for every action. Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `GOOGLE_CONTACTS_API_URL` | Base URL for all requests (e.g. `http://google-contacts-api:8116`) |
| `GOOGLE_CONTACTS_CLIENT_ID` | OAuth client id of the connected account, when the task provides it |
| `GOOGLE_CONTACTS_CLIENT_SECRET` | OAuth client secret of the connected account, when the task provides it |

## Authentication

1. Exchange the client credentials for an access token: `POST /oauth/token` with `grant_type=client_credentials`, `client_id`, `client_secret`, and optionally `scope` (space-separated). Form-encoded and JSON bodies are both accepted.
2. Send `Authorization: Bearer <access_token>` on every operation.
3. `GET /oauth/tokeninfo` reports the presented token's scopes and expiry.

A token requested without `scope` carries only the default scopes (`contacts.readonly`). Ask for any other scope explicitly. A `401 invalid_token` means the token is missing, expired, or revoked; get a new one. A `403 insufficient_scope` names the `required_scope`; request a token that carries it. The token endpoint answers `invalid_scope` when the account never granted a scope to this client. `grant_type=refresh_token` exchanges a refresh token for a new access token.

## Scopes

| Scope | Operations |
|-------|------------|
| `contacts` | POST `/v1/people:createContact`, PATCH `/v1/people/{personId}:updateContact`, DELETE `/v1/people/{personId}:deleteContact` |
| `contacts.readonly` | GET `/v1/people/me/connections`, GET `/v1/people:searchContacts`, GET `/v1/people/{personId}` |

A token carrying `contacts` also covers every `contacts.readonly` operation, so it does not need `contacts.readonly` as well. A token carrying only `contacts.readonly` cannot do the `contacts` operations.

## Endpoints

| Method | Path |
|--------|------|
| POST | `/oauth/token` |
| GET | `/oauth/tokeninfo` |
| GET | `/v1/people/me/connections` |
| GET | `/v1/people:searchContacts` |
| GET | `/v1/people/{personId}` |
| POST | `/v1/people:createContact` |
| PATCH | `/v1/people/{personId}:updateContact` |
| DELETE | `/v1/people/{personId}:deleteContact` |

## Usage

```bash
TOKEN=$(curl -s -X POST "$GOOGLE_CONTACTS_API_URL/oauth/token" -d grant_type=client_credentials \
  -d client_id="$GOOGLE_CONTACTS_CLIENT_ID" -d client_secret="$GOOGLE_CONTACTS_CLIENT_SECRET" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$GOOGLE_CONTACTS_API_URL/v1/people/me/connections?personFields=names,emailAddresses,phoneNumbers&pageSize=10" -H "Authorization: Bearer $TOKEN"
```

## Searching and writing contacts

- `GET /v1/people:searchContacts` needs `query` (the start of a name, email address or phone number) and `readMask`, the fields to return (for example `names,emailAddresses,phoneNumbers`); without one of them it is a `400`. It answers up to 10 matches (`pageSize`, up to 30), and `{}` when nothing matches.
- `GET /v1/people/me/connections` and `GET /v1/people/{personId}` need `personFields` the same way.
- `POST /v1/people:createContact` takes a person with at least one of `names`, `emailAddresses`, `phoneNumbers` or `organizations`.
- `PATCH /v1/people/{personId}:updateContact` changes only the fields named in `updatePersonFields`, and its body must carry the contact's current `etag` (read it with `GET /v1/people/{personId}`); without it, or with a stale one, it is a `400`.
- A query parameter the method does not take is a `400`. Writes need a token carrying `contacts`.

```bash
curl -s "$GOOGLE_CONTACTS_API_URL/v1/people:searchContacts?query=reza&readMask=names,emailAddresses,phoneNumbers" -H "Authorization: Bearer $TOKEN"
```

## Paging

- `GET /v1/people/me/connections` returns 100 per page by default (`pageSize`, up to 1000); when an answer carries `nextPageToken`, send it back as `pageToken` for the next page.
