<!-- api-test-results:begin -->
# Notion API (Mock) - Test Results

GENERATED SECTION. DO NOT HAND-EDIT. `python3 script/gen_api_test_results.py --only notion-api` writes everything between the api-test-results markers by sending the requests below to the service in-process; the text after the end marker is kept as written.

Base URL: `http://localhost:8122` (docker-compose: `http://notion-api:8122`)

## Authentication

Every operation needs `Authorization: Bearer <token>` from `POST /oauth/token` with client credentials. The connected client `notion-connector-app` (account `acct-alex-carter`) is granted `read_content`, `insert_content`, `update_content`; a token requested without `scope` carries `read_content`. A request without a live token answers `401 invalid_token`, and a live token without the route's scope answers `403 insufficient_scope`.

## Endpoints

Each row is one request the generator sent. **Status** is the answer to the request as shown, sent with a token carrying every granted scope. **No token** is the same request with no `Authorization` header, and **Scope removed** the same request with a token carrying every granted scope except the route's own. The shared `/audit` and `/admin` planes every mock serves are described in `environment/API_DOCUMENTATION.md` and not listed.

| Method | Path | Scope | Request sent | Status | No token | Scope removed |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/oauth/token` | client credentials | `/oauth/token (form body)` | 200 | - | - |
| GET | `/health` | none | `/health` | 200 | - | - |
| GET | `/oauth/tokeninfo` | any live token | `/oauth/tokeninfo` | 200 | 401 | - |
| POST | `/v1/search` | `read_content` | `/v1/search (JSON body)` | 200 | 401 | 403 |
| POST | `/v1/databases/{database_id}/query` | `read_content` | `/v1/databases/<Projects database id>/query (JSON body)` | 200 | 401 | 403 |
| GET | `/v1/pages/{page_id}` | `read_content` | `/v1/pages/<Event bus migration page id>` | 200 | 401 | 403 |
| GET | `/v1/blocks/{block_id}/children` | `read_content` | `/v1/blocks/<Event bus migration page id>/children?page_size=5` | 200 | 401 | 403 |
| POST | `/v1/pages` | `insert_content` | `/v1/pages (JSON body)` | 200 | 401 | 403 |
| PATCH | `/v1/pages/{page_id}` | `update_content` | `/v1/pages/<new page id> (JSON body)` | 200 | 401 | 403 |
| PATCH | `/v1/blocks/{block_id}/children` | `insert_content` | `/v1/blocks/<new page id>/children (JSON body)` | 200 | 401 | 403 |

## Seed files

| File | Records |
| --- | --- |
| `blocks.json` | 130 |
| `databases.json` | 3 |
| `pages.json` | 45 |
| `users.json` | 11 |
| `workspaces.json` | 1 |
<!-- api-test-results:end -->

## Connector operations covered

Search pages and databases (`POST /v1/search`), get a page (`GET /v1/pages/{page_id}`), create a page in a database or under a page (`POST /v1/pages`), update page properties or archive a page (`PATCH /v1/pages/{page_id}`), query a database with a filter and sorts (`POST /v1/databases/{database_id}/query`), list a block's or a page's children (`GET /v1/blocks/{block_id}/children`), and append blocks to a page or a block (`PATCH /v1/blocks/{block_id}/children`). Nothing else is served.

## Mock simplifications

- Responses follow Notion-Version 2022-06-28. The `Notion-Version` header is optional here (Notion requires it); any other version is a 400.
- Rich text is text only: annotations and links are kept, mentions and equations are a 400, and one text object holds at most 2,000 characters. `plain_text` and `href` sent back are accepted and recomputed.
- Blocks written: paragraph, heading_1 to heading_3, bulleted and numbered list items, to_do, toggle, quote, callout, code and divider, nested two levels deep and 100 to a request at most; child_page and child_database blocks appear when reading. A block that cannot hold children (a divider, code, a heading that is not toggleable) refuses them with a 400.
- Properties written: title, rich_text, number, select, multi_select, status, date, people, checkbox, url, email, phone_number and relation. A new select or multi_select option is added to the database, as on Notion; a status option must already exist. created_time and last_edited_time are read-only; formulas, rollups, files and unique ids are not modeled.
- Database queries take every condition the 2022-06-28 API lists for those property types, the created_time and last_edited_time timestamp filters, and `and`/`or` nested two levels deep. Text conditions ignore case, and the relative date conditions (`past_week` to `next_year`) count from the real current date. Without sorts the order is created_time, newest first; empty values sort last.
- Search matches the query against titles only, ignoring case, can be filtered to pages or databases, and sorts by last_edited_time (newest first by default). Archived pages are left out of search and queries; a direct `GET` still returns one, with `archived: true`.
- `start_cursor` is the id of the first item of the next page, as on Notion, and `page_size` runs from 1 to 100 (default 100).
- Pages are archived, not deleted, and an archived page refuses edits until it is unarchived. An integration cannot create a page at the top of the workspace.
- Everything in the workspace is shared with the integration. There are no comment, user or database-schema endpoints and no rate limits.
- Errors use Notion's error object (`{"object": "error", "status", "code", "message", "request_id"}`); a body field the endpoint does not take is a 400 `validation_error`, nested ones included, and so is a query parameter the endpoint does not take, where Notion would ignore it.

## Seed data

- Connected account `acct-alex-carter`: Alex Carter's "Contoso Platform" workspace, the team outlook-calendar-api and outlook-contacts-api describe, as of October 2, 2026
- 11 users: Alex and nine colleagues, plus the integration's bot, Platform Connector, which writes everything the agent creates
- 3 inline databases on the Platform Team page: Projects (17 pages, one archived, with status, owner, priority, quarter, target date, tags, progress, customer and design doc), Incidents (9, with severity, status, start time, commander, services, customer impact and the related project) and Meeting Notes (12, with date, type, attendees and the related projects)
- 45 pages and 130 blocks in all, including the Platform Team home page, the On-call Runbook, the Release Process, the six-session Platform Architecture Tour, the Q4 Planning Offsite page and Alex's own notes
- The facts agree with the calendar and contacts seeds: the September 30 payments retry storm and its October 5 review, the October 6 event bus architecture review and its partition-key decision, the Vandelay SSO block and the October 13 escalation, release 26.10 (freeze October 16, ship October 22), the deploy windows, the on-call rotation, and the offsite at Seacliff Lodge on October 14 and 15
- 1 OAuth client `notion-connector-app`: `read_content`, `insert_content` and `update_content` granted; a token requested without `scope` carries only `read_content`
