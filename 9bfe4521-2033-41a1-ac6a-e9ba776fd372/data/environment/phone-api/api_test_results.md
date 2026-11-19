<!-- api-test-results:begin -->
# Phone API (Mock) - Test Results

GENERATED SECTION. DO NOT HAND-EDIT. `python3 script/gen_api_test_results.py --only phone-api` writes everything between the api-test-results markers by sending the requests below to the service in-process; the text after the end marker is kept as written.

Base URL: `http://localhost:8129` (docker-compose: `http://phone-api:8129`)

## Authentication

Every operation needs `Authorization: Bearer <token>` from `POST /oauth/token` with client credentials. The connected client `phone-connector-app` (account `acct-dana-whitfield`) is granted `calls.read`, `calls.write`, `messages.read`, `messages.send`; a token requested without `scope` carries `calls.read`, `messages.read`. A request without a live token answers `401 invalid_token`, and a live token without the route's scope answers `403 insufficient_scope`.

## Endpoints

Each row is one request the generator sent. **Status** is the answer to the request as shown, sent with a token carrying every granted scope. **No token** is the same request with no `Authorization` header, and **Scope removed** the same request with a token carrying every granted scope except the route's own. The shared `/audit` and `/admin` planes every mock serves are described in `environment/API_DOCUMENTATION.md` and not listed.

| Method | Path | Scope | Request sent | Status | No token | Scope removed |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/oauth/token` | client credentials | `/oauth/token (form body)` | 200 | - | - |
| GET | `/health` | none | `/health` | 200 | - | - |
| GET | `/oauth/tokeninfo` | any live token | `/oauth/tokeninfo` | 200 | 401 | - |
| GET | `/v1/calls` | `calls.read` | `/v1/calls?limit=10` | 200 | 401 | 403 |
| GET | `/v1/calls` | `calls.read` | `/v1/calls?direction=incoming&status=missed&since=2026-09-28&until=2026-10-04&limit=5&cursor=<next_cursor from the list>` | 200 | 401 | 403 |
| POST | `/v1/calls` | `calls.write` | `/v1/calls (JSON body)` | 201 | 401 | 403 |
| GET | `/v1/conversations` | `messages.read` | `/v1/conversations?unread_only=true&limit=5` | 200 | 401 | 403 |
| GET | `/v1/conversations` | `messages.read` | `/v1/conversations?limit=5&cursor=cGg6NQ` | 200 | 401 | 403 |
| GET | `/v1/conversations/{conversation_id}/messages` | `messages.read` | `/v1/conversations/<conversation id from the list>/messages?limit=2` | 200 | 401 | 403 |
| POST | `/v1/messages` | `messages.send` | `/v1/messages (JSON body)` | 201 | 401 | 403 |

## Seed files

| File | Records |
| --- | --- |
| `calls.json` | 121 |
| `contacts.json` | 29 |
| `conversations.json` | 27 |
| `lines.json` | 1 |
| `messages.json` | 73 |
<!-- api-test-results:end -->

## Connector operations covered

List recent calls (`GET /v1/calls`), place a call (`POST /v1/calls`, which records an outgoing call), list text conversations (`GET /v1/conversations`), list the messages in a conversation (`GET /v1/conversations/{conversation_id}/messages`), and send a text message (`POST /v1/messages`). Nothing else is served.

## Operation set and API shape

The client's connector list names a Phone connector without describing it, so this operation set is an assumption, stated in this service's README.md. No vendor publishes this API: the routes, fields, scope names (`calls.read`, `calls.write`, `messages.read`, `messages.send`) and error body are a plain REST shape of this mock's own.

## Mock simplifications

- Errors use this mock's body, `{"error": {"code", "message", "param"}}`: `404 not_found` for a conversation that is not on the connected line, `400 invalid_request` for a bad value, a number that is not E.164, the line's own number, an empty or over-long text, an unknown body field, or a query parameter the operation does not take.
- `GET /v1/calls` lists calls newest first. `direction` (`incoming`, `outgoing`), `status` (`answered`, `missed`, `declined`, `no_answer`, `placed`), `since` and `until` (a local date, inclusive, or an RFC 3339 instant) filter; `limit` (1 to 100, default 25) and the opaque `cursor` page. Each call names the contact when the number is in the address book.
- Placing a call cannot connect one: it records an outgoing call with status `placed` and duration 0, which the call list then shows.
- `GET /v1/conversations` lists one conversation per number, most recent first, with a snippet and unread count; `unread_only=true` keeps those with unread messages. Messages are listed newest first. Sending a text to a number with no conversation starts one. Texts are SMS only (up to 1600 characters): no MMS, group texts, read receipts to send, blocking or deleting.

## Seed data

- Connected account `acct-dana-whitfield`: Dana Whitfield's mobile line, +1 312-555-0110, with an address book of 29 contacts whose numbers match google-contacts-api: the Lakeshore Design Studio team and front desk, Brightwell Hospitality (Raj Patel, Frank Morales, Alicia Brandt, Ivy Chen, Carla Jensen), the contractors and vendors on the Brightwell install, and the clients and prospects calendly-api and granola-api record.
- 121 calls from September 1 to October 4, 2026: calls about the Halo 24 pendants, the reception desk power, the night install crew and change order 03, everyday studio calls, and declined and missed spam from unknown numbers; some missed calls left a voicemail.
- 27 text conversations with 73 messages, several still unread (Alicia Brandt still waiting for change order 03, Marcus on Saddlebrook, Jerome on the insurance certificates), and three scam texts.
- Every phone number is in the 555-01xx range set aside for fiction.
- 1 OAuth client `phone-connector-app`: all four scopes granted; a token requested without `scope` carries `calls.read` and `messages.read`.
