<!-- api-test-results:begin -->
# Granola API (Mock) - Test Results

GENERATED SECTION. DO NOT HAND-EDIT. `python3 script/gen_api_test_results.py --only granola-api` writes everything between the api-test-results markers by sending the requests below to the service in-process; the text after the end marker is kept as written.

Base URL: `http://localhost:8125` (docker-compose: `http://granola-api:8125`)

## Authentication

Every operation needs `Authorization: Bearer <token>` from `POST /oauth/token` with client credentials. The connected client `granola-connector-app` (account `acct-dana-whitfield`) is granted `notes:read`, `notes:search`; a token requested without `scope` carries `notes:read`, `notes:search`. A request without a live token answers `401 invalid_token`, and a live token without the route's scope answers `403 insufficient_scope`.

## Endpoints

Each row is one request the generator sent. **Status** is the answer to the request as shown, sent with a token carrying every granted scope. **No token** is the same request with no `Authorization` header, and **Scope removed** the same request with a token carrying every granted scope except the route's own. The shared `/audit` and `/admin` planes every mock serves are described in `environment/API_DOCUMENTATION.md` and not listed.

| Method | Path | Scope | Request sent | Status | No token | Scope removed |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/oauth/token` | client credentials | `/oauth/token (form body)` | 200 | - | - |
| GET | `/health` | none | `/health` | 200 | - | - |
| GET | `/oauth/tokeninfo` | any live token | `/oauth/tokeninfo` | 200 | 401 | - |
| GET | `/v1/notes` | `notes:read` | `/v1/notes?start_date=2026-09-21&end_date=2026-09-30&limit=5` | 200 | 401 | 403 |
| GET | `/v1/notes` | `notes:read` | `/v1/notes?start_date=2026-09-21&end_date=2026-09-30&limit=5&cursor=<next_cursor from the list>` | 200 | 401 | 403 |
| GET | `/v1/notes/{note_id}` | `notes:read` | `/v1/notes/<Brightwell September status note id>` | 200 | 401 | 403 |
| GET | `/v1/notes/search` | `notes:search` | `/v1/notes/search?q=change order 03&limit=2` | 200 | 401 | 403 |
| GET | `/v1/notes/search` | `notes:search` | `/v1/notes/search?q=change order 03&limit=2&cursor=<next_cursor from the search>` | 200 | 401 | 403 |

## Seed files

| File | Records |
| --- | --- |
| `action_items.json` | 92 |
| `notes.json` | 42 |
| `people.json` | 31 |
<!-- api-test-results:end -->

## Connector operations covered

List meeting notes with a date filter (`GET /v1/notes`), get one note with its summary, action items and transcript (`GET /v1/notes/{note_id}`), and search notes by text (`GET /v1/notes/search`). Nothing else is served.

## API shape

Granola publishes no widely documented public REST API, so this mock does not copy one: the routes, fields, scope names (`notes:read`, `notes:search`) and error body are a plain REST shape of this mock's own, stated in this service's README.md.

## Mock simplifications

- Errors use this mock's body, `{"error": {"code", "message", "param"}}`: `404 not_found` for a note the connected account does not own, `400 invalid_request` for a bad value, a malformed date, or a query parameter the operation does not take.
- `GET /v1/notes` lists notes newest first. `start_date` and `end_date` (`YYYY-MM-DD`, inclusive, on the meeting's local start date) filter; `limit` (1 to 100, default 20) and the opaque `cursor` from `next_cursor` page. Each list item carries the attendees and the number of action items, open and in total.
- `GET /v1/notes/{note_id}` adds the calendar event, the generated summary (Markdown with Overview, Decisions, Discussion and Next steps), the action items with assignee, due date and completion, and the transcript as timed utterances (`start` in seconds from the start of the recording).
- `GET /v1/notes/search` needs `q`; every term must appear somewhere in the note's title, summary, action items or transcript, and each result names the fields that matched with a snippet. Results come newest first; `limit` and `cursor` page as above.
- No writes: notes, action items and transcripts cannot be created or edited, and there are no folders, sharing, templates or live recording.

## Seed data

- Connected account `acct-dana-whitfield`: Dana Whitfield's Granola notes at Lakeshore Design Studio, August 3 to October 2, 2026, with 31 people in the attendee directory.
- 42 notes and 92 action items: the nine Monday studio standups; the client meetings Calendly booked (Calloway & Finch, Fennimore PR, Harbor Street Cafe, Midway Credit Union, Lumen Coworking, Bluebird Hotel Group, Greenline Dental, Saddlebrook Hospitality, Third Coast Interiors), on the dates calendly-api records; five Brightwell lobby meetings, from design development through the October 19 to 30 install plan and change order 03, the $18,640 pendant upgrade still awaiting Dana's pricing approval; vendor meetings with Copperleaf, Cobblestone Lighting, Linnet Acoustics and North Branch Millwork; and internal planning (open house on November 12, Q4 capacity, the studio coordinator hire, the 2027 rate card, Q3 estimated tax).
- 1 OAuth client `granola-connector-app`: `notes:read` and `notes:search` granted, and a token requested without `scope` carries both, since every operation only reads.
