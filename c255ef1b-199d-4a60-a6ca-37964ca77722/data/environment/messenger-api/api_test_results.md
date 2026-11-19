<!-- api-test-results:begin -->
# Facebook Messenger (Mock) - Test Results

GENERATED SECTION. DO NOT HAND-EDIT. `python3 script/gen_api_test_results.py --only messenger-api` writes everything between the api-test-results markers by sending the requests below to the service in-process; the text after the end marker is kept as written.

Base URL: `http://localhost:8107` (docker-compose: `http://messenger-api:8107`)

## Authentication

Every operation needs `Authorization: Bearer <token>` from `POST /oauth/token` with client credentials. The connected client `msgr-connector-app` (account `acct-tessa-marlowe`) is granted `messenger.read`, `messenger.contacts`, `messenger.send`; a token requested without `scope` carries `messenger.read`. A request without a live token answers `401 invalid_token`, and a live token without the route's scope answers `403 insufficient_scope`.

## Endpoints

Each row is one request the generator sent. **Status** is the answer to the request as shown, sent with a token carrying every granted scope. **No token** is the same request with no `Authorization` header, and **Scope removed** the same request with a token carrying every granted scope except the route's own. The shared `/audit` and `/admin` planes every mock serves are described in `environment/API_DOCUMENTATION.md` and not listed.

| Method | Path | Scope | Request sent | Status | No token | Scope removed |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/oauth/token` | client credentials | `/oauth/token (form body)` | 200 | - | - |
| GET | `/health` | none | `/health` | 200 | - | - |
| GET | `/oauth/tokeninfo` | any live token | `/oauth/tokeninfo` | 200 | 401 | - |
| GET | `/v21.0/me/conversations` | `messenger.read` | `/v21.0/me/conversations?limit=10` | 200 | 401 | 403 |
| GET | `/v21.0/me/conversations/{thread_id}` | `messenger.read` | `/v21.0/me/conversations/t_100060000000001` | 200 | 401 | 403 |
| GET | `/v21.0/me/conversations/{thread_id}/messages` | `messenger.read` | `/v21.0/me/conversations/t_100060000000001/messages?limit=10` | 200 | 401 | 403 |
| GET | `/v21.0/me/unread` | `messenger.read` | `/v21.0/me/unread` | 200 | 401 | 403 |
| GET | `/v21.0/me/sync` | `messenger.read` | `/v21.0/me/sync` | 200 | 401 | 403 |
| GET | `/v21.0/me/sync` | `messenger.read` | `/v21.0/me/sync?cursor=<cursor from the previous sync>` | 200 | 401 | 403 |
| GET | `/v21.0/me/search` | `messenger.read` | `/v21.0/me/search?q=sparkler` | 200 | 401 | 403 |
| GET | `/v21.0/me/contacts` | `messenger.contacts` | `/v21.0/me/contacts?limit=30` | 200 | 401 | 403 |
| POST | `/v21.0/me/messages` | `messenger.send` | `/v21.0/me/messages (JSON body)` | 200 | 401 | 403 |
| POST | `/v21.0/me/messages` | `messenger.send` | `/v21.0/me/messages (JSON body)` | 200 | 401 | 403 |
| DELETE | `/v21.0/me/messages/{message_id}` | `messenger.send` | `/v21.0/me/messages/<message id from the send>` | 200 | 401 | 403 |

## Seed files

| File | Records |
| --- | --- |
| `attachments.json` | 8 |
| `messages.json` | 311 |
| `reactions.json` | 35 |
| `thread_participants.json` | 47 |
| `threads.json` | 18 |
| `users.json` | 31 |
<!-- api-test-results:end -->

## Connector operations covered

`.threads` (list and retrieve), `.messages`, `.check` (`/me/unread`), `.sync`, `.search`, `.contacts`, `.send`, `.unsend`. Nothing else is served.

## Seed data

- Connected user Tessa Marlowe (freelance wedding photographer, Atlanta; account `acct-tessa-marlowe`) and 30 contacts, 10 of them not friends (prospective clients and vendors)
- 18 threads (14 one-to-one, 4 group), 311 messages from 2026-08-15 to 2026-09-30, 8 attachments, 35 reactions, 2 unsent messages
- 6 threads carry unread messages; unread is every message from someone else, not unsent, created after the thread's `last_read_time`
- 1 OAuth client `msgr-connector-app`: every scope granted; a token requested without `scope` carries only `messenger.read`

## Notes

- Unsend works only on the connected user's own messages sent within the last 10 minutes. Seeded messages are all older, so they answer `400`; send a message and unsend it to exercise the success path. Unsent messages keep their row with `unsent: true` and empty text, and the thread snippet becomes `You unsent a message` when it was the latest message.
- `sync` without `cursor` returns every thread and message changed in the 48 hours up to the newest seeded message; with a `cursor` it returns what changed after that cursor. Every response carries a new opaque `cursor`.
- Sending to a contact with no existing one-to-one thread creates the thread; sending by `thread_id` can also reach group threads. Sending does not mark a thread read.
