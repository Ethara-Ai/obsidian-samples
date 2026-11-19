<!-- api-test-results:begin -->
# Instagram Messaging API (Mock) - Test Results

GENERATED SECTION. DO NOT HAND-EDIT. `python3 script/gen_api_test_results.py --only instagram-messages-api` writes everything between the api-test-results markers by sending the requests below to the service in-process; the text after the end marker is kept as written.

Base URL: `http://localhost:8112` (docker-compose: `http://instagram-messages-api:8112`)

## Authentication

Every operation needs `Authorization: Bearer <token>` from `POST /oauth/token` with client credentials. The connected client `igmsg-connector-app` (account `acct-maya-okafor`) is granted `instagram_messages.read`, `instagram_messages.send`; a token requested without `scope` carries `instagram_messages.read`. A request without a live token answers `401 invalid_token`, and a live token without the route's scope answers `403 insufficient_scope`.

## Endpoints

Each row is one request the generator sent. **Status** is the answer to the request as shown, sent with a token carrying every granted scope. **No token** is the same request with no `Authorization` header, and **Scope removed** the same request with a token carrying every granted scope except the route's own. The shared `/audit` and `/admin` planes every mock serves are described in `environment/API_DOCUMENTATION.md` and not listed.

| Method | Path | Scope | Request sent | Status | No token | Scope removed |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/oauth/token` | client credentials | `/oauth/token (form body)` | 200 | - | - |
| GET | `/health` | none | `/health` | 200 | - | - |
| GET | `/oauth/tokeninfo` | any live token | `/oauth/tokeninfo` | 200 | 401 | - |
| GET | `/v21.0/me/conversations` | `instagram_messages.read` | `/v21.0/me/conversations?platform=instagram&limit=10` | 200 | 401 | 403 |
| GET | `/v21.0/me/conversations` | `instagram_messages.read` | `/v21.0/me/conversations?user_id=<IGSID from the list>` | 200 | 401 | 403 |
| GET | `/v21.0/{conversation_id}/messages` | `instagram_messages.read` | `/v21.0/<conversation id>/messages?limit=10` | 200 | 401 | 403 |
| POST | `/v21.0/me/messages` | `instagram_messages.send` | `/v21.0/me/messages (JSON body)` | 200 | 401 | 403 |

## Seed files

| File | Records |
| --- | --- |
| `accounts.json` | 1 |
| `conversations.json` | 44 |
| `messages.json` | 170 |
| `users.json` | 44 |
<!-- api-test-results:end -->

## Connector operations covered

List conversations (`GET /v21.0/me/conversations`), list the messages of a conversation (`GET /v21.0/{conversation_id}/messages`), and send a message (`POST /v21.0/me/messages`), the routes of the Instagram API with Instagram Login. Nothing else is served.

## Mock simplifications

- Text messages only; seeded messages may carry an image attachment or a story reply. There are no reactions, no message-requests folder and no 24-hour messaging window, which would be measured against the wall clock rather than the task's dates.
- A message can be sent only to a user who already has a conversation with the account (`(#100) No matching user found`, subcode 2018001, otherwise), and its text is limited to 1000 UTF-8 bytes.
- `platform` is `instagram` (the default) or `messenger`; this account has no Messenger inbox, so `messenger` lists nothing. `user_id` narrows the list to the conversation with that IGSID. `limit` and `after` page; `fields` selects fields.
- Conversations are listed by most recent activity and messages newest first; a sent message updates its conversation's `updated_time`.

## Seed data

- Connected account `acct-maya-okafor`; professional account `saltmarsh.ceramics` (17841400000000101), the business instagram-api also serves
- 44 conversations and 170 messages from 2026-09-02 to 2026-10-03: orders, a damaged-in-transit return, a wrong-glaze shipment, wholesale and custom requests, class and studio-sale questions, press and job inquiries, story replies, and two scams (a fake ambassador program and a fake Meta copyright notice)
- The Lakeshore Design thread (six Fog Line planters, invoice SC-0412, prepaid September 15, delivered October 5) matches the Lakeshore order in google-sheets-api
- 1 OAuth client `igmsg-connector-app`: both scopes granted; a token requested without `scope` carries only `instagram_messages.read`
