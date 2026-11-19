---
name: google-tasks-api-connector
description: >
  Google Tasks API (Mock) mock HTTP API. Base URL is provided via the
  `GOOGLE_TASKS_API_URL` environment variable. 9 endpoint(s) across DELETE, GET, PATCH, POST, PUT.
  Every operation needs an OAuth bearer token that carries the operation's scope.
---

# Google Tasks API (Mock)

Mock HTTP API. **All requests go to the base URL in `$GOOGLE_TASKS_API_URL`.** Every operation needs a bearer token, and a token covers only the scopes it was issued with: a connected account is not permission for every action. Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `GOOGLE_TASKS_API_URL` | Base URL for all requests (e.g. `http://google-tasks-api:8119`) |
| `GOOGLE_TASKS_CLIENT_ID` | OAuth client id of the connected account, when the task provides it |
| `GOOGLE_TASKS_CLIENT_SECRET` | OAuth client secret of the connected account, when the task provides it |

## Authentication

1. Exchange the client credentials for an access token: `POST /oauth/token` with `grant_type=client_credentials`, `client_id`, `client_secret`, and optionally `scope` (space-separated). Form-encoded and JSON bodies are both accepted.
2. Send `Authorization: Bearer <access_token>` on every operation.
3. `GET /oauth/tokeninfo` reports the presented token's scopes and expiry.

A token requested without `scope` carries only the default scopes (`tasks.readonly`). Ask for any other scope explicitly. A `401 invalid_token` means the token is missing, expired, or revoked; get a new one. A `403 insufficient_scope` names the `required_scope`; request a token that carries it. The token endpoint answers `invalid_scope` when the account never granted a scope to this client. `grant_type=refresh_token` exchanges a refresh token for a new access token.

## Scopes

| Scope | Operations |
|-------|------------|
| `tasks` | POST `/tasks/v1/lists/{tasklist}/tasks`, PUT `/tasks/v1/lists/{tasklist}/tasks/{task}`, PATCH `/tasks/v1/lists/{tasklist}/tasks/{task}`, DELETE `/tasks/v1/lists/{tasklist}/tasks/{task}` |
| `tasks.readonly` | GET `/tasks/v1/users/@me/lists`, GET `/tasks/v1/lists/{tasklist}/tasks`, GET `/tasks/v1/lists/{tasklist}/tasks/{task}` |

A token carrying `tasks` also covers every `tasks.readonly` operation, so it does not need `tasks.readonly` as well. A token carrying only `tasks.readonly` cannot do the `tasks` operations.

## Endpoints

| Method | Path |
|--------|------|
| POST | `/oauth/token` |
| GET | `/oauth/tokeninfo` |
| GET | `/tasks/v1/users/@me/lists` |
| GET | `/tasks/v1/lists/{tasklist}/tasks` |
| GET | `/tasks/v1/lists/{tasklist}/tasks/{task}` |
| POST | `/tasks/v1/lists/{tasklist}/tasks` |
| PUT | `/tasks/v1/lists/{tasklist}/tasks/{task}` |
| PATCH | `/tasks/v1/lists/{tasklist}/tasks/{task}` |
| DELETE | `/tasks/v1/lists/{tasklist}/tasks/{task}` |

## Usage

```bash
TOKEN=$(curl -s -X POST "$GOOGLE_TASKS_API_URL/oauth/token" -d grant_type=client_credentials \
  -d client_id="$GOOGLE_TASKS_CLIENT_ID" -d client_secret="$GOOGLE_TASKS_CLIENT_SECRET" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$GOOGLE_TASKS_API_URL/tasks/v1/users/@me/lists" -H "Authorization: Bearer $TOKEN"
```

## Paging

- `GET /tasks/v1/lists/{tasklist}/tasks` returns 20 per page by default (`maxResults`, up to 100); when an answer carries `nextPageToken`, send it back as `pageToken` for the next page.
