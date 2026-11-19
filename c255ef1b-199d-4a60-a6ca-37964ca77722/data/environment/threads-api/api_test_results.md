<!-- api-test-results:begin -->
# Threads API (Mock) - Test Results

GENERATED SECTION. DO NOT HAND-EDIT. `python3 script/gen_api_test_results.py --only threads-api` writes everything between the api-test-results markers by sending the requests below to the service in-process; the text after the end marker is kept as written.

Base URL: `http://localhost:8113` (docker-compose: `http://threads-api:8113`)

## Authentication

Every operation needs `Authorization: Bearer <token>` from `POST /oauth/token` with client credentials. The connected client `threads-connector-app` (account `acct-maya-okafor`) is granted `threads_basic`, `threads_content_publish`, `threads_read_replies`; a token requested without `scope` carries `threads_basic`. A request without a live token answers `401 invalid_token`, and a live token without the route's scope answers `403 insufficient_scope`.

## Endpoints

Each row is one request the generator sent. **Status** is the answer to the request as shown, sent with a token carrying every granted scope. **No token** is the same request with no `Authorization` header, and **Scope removed** the same request with a token carrying every granted scope except the route's own. The shared `/audit` and `/admin` planes every mock serves are described in `environment/API_DOCUMENTATION.md` and not listed.

| Method | Path | Scope | Request sent | Status | No token | Scope removed |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/oauth/token` | client credentials | `/oauth/token (form body)` | 200 | - | - |
| GET | `/health` | none | `/health` | 200 | - | - |
| GET | `/oauth/tokeninfo` | any live token | `/oauth/tokeninfo` | 200 | 401 | - |
| GET | `/v1.0/me` | `threads_basic` | `/v1.0/me?fields=id,username,name,threads_biography` | 200 | 401 | 403 |
| GET | `/v1.0/{threads_media_id}` | `threads_basic` | `/v1.0/180624500000000037` | 200 | 401 | 403 |
| GET | `/v1.0/{threads_user_id}/threads` | `threads_basic` | `/v1.0/me/threads?limit=5` | 200 | 401 | 403 |
| GET | `/v1.0/{threads_user_id}/threads` | `threads_basic` | `/v1.0/me/threads?since=2026-09-01&until=2026-09-30` | 200 | 401 | 403 |
| POST | `/v1.0/{threads_user_id}/threads` | `threads_content_publish` | `/v1.0/me/threads (JSON body)` | 200 | 401 | 403 |
| POST | `/v1.0/{threads_user_id}/threads_publish` | `threads_content_publish` | `/v1.0/26954413785410023/threads_publish (JSON body)` | 200 | 401 | 403 |
| GET | `/v1.0/{threads_media_id}/replies` | `threads_read_replies` | `/v1.0/180624500000000037/replies` | 200 | 401 | 403 |
| GET | `/v1.0/{threads_media_id}/replies` | `threads_read_replies` | `/v1.0/180624500000000037/replies?reverse=false` | 200 | 401 | 403 |

## Seed files

| File | Records |
| --- | --- |
| `accounts.json` | 1 |
| `replies.json` | 158 |
| `threads.json` | 41 |
<!-- api-test-results:end -->

## Connector operations covered

Read the profile (`GET /v1.0/me`, which also gives the Threads user id; `GET /v1.0/{threads_media_id}` with that id answers the profile too), list the account's threads (`GET /v1.0/{threads_user_id}/threads`, `me` or the id), get one thread (`GET /v1.0/{threads_media_id}`), publish a text thread (`POST /v1.0/{threads_user_id}/threads`, then `POST /v1.0/{threads_user_id}/threads_publish` with the container id as `creation_id`), and list the replies to a thread or reply (`GET /v1.0/{threads_media_id}/replies`). Nothing else is served.

## Mock simplifications

- Only text posts (`media_type` `TEXT`) can be published; `IMAGE`, `VIDEO` and `CAROUSEL` are refused. Text is limited to 500 characters, an emoji counting as its UTF-8 length. A container is ready to publish as soon as it is created and can be published once.
- There are no insights, quote posts, reposts or reply management. Replies are media objects: a reply's own replies are reached through its `replies` edge.
- `since` and `until` take a unix timestamp or a date such as `2026-09-01`; `reverse` (default `true`, newest first) orders replies; `limit` and `after` page; `fields` selects fields.

## Seed data

- Connected account `acct-maya-okafor`; Threads profile `mayamakes` (Maya Okafor, the creator account instagram-api also serves)
- 41 threads from 2026-06-02 to 2026-10-03 and 158 replies, 45 of them nested; two spam replies are `HIDDEN`
- The threads follow the same studio timeline as the Instagram seeds (the Fog Line restock on September 9, the kiln repair on September 14, the Chicago planters, the October 3 studio sale)
- 1 OAuth client `threads-connector-app`: every scope granted; a token requested without `scope` carries only `threads_basic`
