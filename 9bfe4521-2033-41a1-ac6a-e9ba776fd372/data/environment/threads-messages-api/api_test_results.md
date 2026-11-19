<!-- api-test-results:begin -->
# Threads Messaging API (Mock) - Test Results

GENERATED SECTION. DO NOT HAND-EDIT. `python3 script/gen_api_test_results.py --only threads-messages-api` writes everything between the api-test-results markers by sending the requests below to the service in-process; the text after the end marker is kept as written.

Base URL: `http://localhost:8128` (docker-compose: `http://threads-messages-api:8128`)

## Authentication

Every operation needs `Authorization: Bearer <token>` from `POST /oauth/token` with client credentials. The connected client `thmsg-connector-app` (account `acct-maya-okafor`) is granted `threads_messages.read`, `threads_messages.send`; a token requested without `scope` carries `threads_messages.read`. A request without a live token answers `401 invalid_token`, and a live token without the route's scope answers `403 insufficient_scope`.

## Endpoints

Each row is one request the generator sent. **Status** is the answer to the request as shown, sent with a token carrying every granted scope. **No token** is the same request with no `Authorization` header, and **Scope removed** the same request with a token carrying every granted scope except the route's own. The shared `/audit` and `/admin` planes every mock serves are described in `environment/API_DOCUMENTATION.md` and not listed.

| Method | Path | Scope | Request sent | Status | No token | Scope removed |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/oauth/token` | client credentials | `/oauth/token (form body)` | 200 | - | - |
| GET | `/health` | none | `/health` | 200 | - | - |
| GET | `/oauth/tokeninfo` | any live token | `/oauth/tokeninfo` | 200 | 401 | - |
| GET | `/v1.0/me/conversations` | `threads_messages.read` | `/v1.0/me/conversations?limit=10` | 200 | 401 | 403 |
| GET | `/v1.0/me/conversations` | `threads_messages.read` | `/v1.0/me/conversations?user_id=<Threads user id from the list>&fields=id,updated_time` | 200 | 401 | 403 |
| GET | `/v1.0/{conversation_id}/messages` | `threads_messages.read` | `/v1.0/<conversation id>/messages?limit=2` | 200 | 401 | 403 |
| GET | `/v1.0/{conversation_id}/messages` | `threads_messages.read` | `/v1.0/<conversation id>/messages?limit=2&after=<after cursor>&fields=message` | 200 | 401 | 403 |
| POST | `/v1.0/me/messages` | `threads_messages.send` | `/v1.0/me/messages (JSON body)` | 200 | 401 | 403 |

## Seed files

| File | Records |
| --- | --- |
| `accounts.json` | 1 |
| `conversations.json` | 40 |
| `messages.json` | 160 |
| `users.json` | 40 |
<!-- api-test-results:end -->

## Connector operations covered

List conversations (`GET /v1.0/me/conversations`), list the messages of a conversation (`GET /v1.0/{conversation_id}/messages`), and send a message (`POST /v1.0/me/messages`). Nothing else is served.

## API shape

Meta publishes no messaging endpoint in the Threads API that this mock could copy, so, as the client asked, it mirrors instagram-messages-api: the same Graph messaging routes, fields, paging and error envelope, on the Threads Graph version prefix `v1.0`. The scope names `threads_messages.read` and `threads_messages.send` are this mock's own, following that service's.

## Mock simplifications

- Errors use the Graph error envelope (`{"error": {"message", "type", "code", "fbtrace_id"}}`), request validation failures included; a query parameter the operation does not take is `(#100) Param <name> is not a valid parameter`. Instagram's `platform` parameter is not taken, since Threads has one inbox.
- Text messages only; seeded messages may carry an image attachment or a shared Threads post. No reactions, no message requests folder and no messaging window.
- A message can be sent only to a user who already has a conversation with the profile (`(#100) No matching user found`, subcode 2018001, otherwise), and its text is limited to 1000 UTF-8 bytes.
- `user_id` narrows the list to the conversation with that user; `limit` (1 to 100, default 25) and `after` page; `fields` selects fields. Conversations are listed by most recent activity and messages newest first; a sent message updates its conversation's `updated_time`.

## Seed data

- Connected account `acct-maya-okafor`; Threads profile `mayamakes` (26954413785410023), the profile threads-api also serves.
- 40 users and 40 conversations with 160 messages from September 5 to October 4, 2026, following the posts threads-api records: questions about the October 3 studio sale, the full Thursday beginner class and its waitlist, the kiln repair, the copper red glaze test, care and food safety, two damaged or missing orders, commissions, wholesale and a tea house order, a podcast invitation, a makers market booth and a guild jury, and two scams (a fake safety team and a paid "ambassador" offer).
- The Lakeshore Design Studio thread (the six Fog Line planters, shipped by freight, due by October 9 for the October 19 lobby install) matches the planters in instagram-messages-api and threads-api.
- 1 OAuth client `thmsg-connector-app`: both scopes granted; a token requested without `scope` carries only `threads_messages.read`.
