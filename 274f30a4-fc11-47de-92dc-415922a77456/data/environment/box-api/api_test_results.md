<!-- api-test-results:begin -->
# Box API (Mock) - Test Results

GENERATED SECTION. DO NOT HAND-EDIT. `python3 script/gen_api_test_results.py --only box-api` writes everything between the api-test-results markers by sending the requests below to the service in-process; the text after the end marker is kept as written.

Base URL: `http://localhost:8124` (docker-compose: `http://box-api:8124`)

## Authentication

Every operation needs `Authorization: Bearer <token>` from `POST /oauth/token` with client credentials. The connected client `box-connector-app` (account `acct-dana-whitfield`) is granted `root_readonly`, `root_readwrite`; a token requested without `scope` carries `root_readonly`. A request without a live token answers `401 invalid_token`, and a live token without the route's scope answers `403 insufficient_scope`.

## Endpoints

Each row is one request the generator sent. **Status** is the answer to the request as shown, sent with a token carrying every granted scope. **No token** is the same request with no `Authorization` header, and **Scope removed** the same request with a token carrying every granted scope except the route's own. The shared `/audit` and `/admin` planes every mock serves are described in `environment/API_DOCUMENTATION.md` and not listed.

| Method | Path | Scope | Request sent | Status | No token | Scope removed |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/oauth/token` | client credentials | `/oauth/token (form body)` | 200 | - | - |
| GET | `/health` | none | `/health` | 200 | - | - |
| GET | `/oauth/tokeninfo` | any live token | `/oauth/tokeninfo` | 200 | 401 | - |
| GET | `/2.0/folders/{folder_id}/items` | `root_readonly` | `/2.0/folders/0/items` | 200 | 401 | 403 |
| GET | `/2.0/folders/{folder_id}/items` | `root_readonly` | `/2.0/folders/<Clients folder id>/items?fields=name,modified_at&sort=date&direction=DESC&limit=3` | 200 | 401 | 403 |
| GET | `/2.0/search` | `root_readonly` | `/2.0/search?query=Brightwell Lobby&type=folder` | 200 | 401 | 403 |
| GET | `/2.0/search` | `root_readonly` | `/2.0/search?query=change order&type=file&file_extensions=pdf&ancestor_folder_ids=<Brightwell Lobby Refresh folder id>&content_types=name&limit=5&offset=0&fields=name,size` | 200 | 401 | 403 |
| GET | `/2.0/folders/{folder_id}/items` | `root_readonly` | `/2.0/folders/<Brightwell Lobby Refresh folder id>/items?offset=0` | 200 | 401 | 403 |
| GET | `/2.0/folders/{folder_id}/items` | `root_readonly` | `/2.0/folders/<01 Contracts folder id>/items?fields=name` | 200 | 401 | 403 |
| GET | `/2.0/files/{file_id}` | `root_readonly` | `/2.0/files/<file id from the list>` | 200 | 401 | 403 |
| GET | `/2.0/files/{file_id}` | `root_readonly` | `/2.0/files/<file id from the list>?fields=name,shared_link` | 200 | 401 | 403 |
| POST | `/2.0/folders` | `root_readwrite` | `/2.0/folders (JSON body)` | 201 | 401 | 403 |
| POST | `/api/2.0/files/content` | `root_readwrite` | `/api/2.0/files/content?fields=name,size (JSON body)` | 201 | 401 | 403 |
| PUT | `/2.0/files/{file_id}` | `root_readwrite` | `/2.0/files/<file id from the list>?fields=shared_link (JSON body)` | 200 | 401 | 403 |

## Seed files

| File | Records |
| --- | --- |
| `files.json` | 195 |
| `folders.json` | 50 |
| `users.json` | 6 |
<!-- api-test-results:end -->

## Connector operations covered

List a folder's items (`GET /2.0/folders/{folder_id}/items`), get a file's details (`GET /2.0/files/{file_id}`), search by name (`GET /2.0/search`), create a folder (`POST /2.0/folders`), upload a small file (`POST /api/2.0/files/content`, the path upload.box.com serves), and create a shared link for a file (`PUT /2.0/files/{file_id}` with a `shared_link` body). Nothing else is served.

## Mock simplifications

- Errors use Box's client error body (`{"type": "error", "status", "code", "context_info", "help_url", "message", "request_id"}`): `404 not_found` for an id the connected account does not own, `409 item_name_in_use` with the clashing item in `context_info.conflicts` for a name already taken in the folder, `400 bad_request` with the offending parameter in `context_info.errors` for a bad value, an unknown body field, or a query parameter the operation does not take.
- `GET /2.0/folders/{folder_id}/items` lists folders before files, sorted by name unless `sort` (`id`, `name`, `date`, `size`) and `direction` (`ASC`, `DESC`) say otherwise; `limit` (1 to 1000, default 100) and `offset` page; `fields` returns `type`, `id`, `etag` and the named fields instead of the mini objects. The root folder is `0`, "All Files".
- `GET /2.0/search` needs `query`; every term must appear in the item's name or description (`content_types=name` or `content_types=description` narrows that). `type` (`file`, `folder`), `file_extensions`, and `ancestor_folder_ids` filter, newest-modified first; `limit` (1 to 200, default 30), `offset` and `fields` work as above. File contents, comments and tags are not searched.
- An upload is the multipart body Box takes, an `attributes` part (`name`, `parent.id`, optional `content_created_at` and `content_modified_at`) and a `file` part; a JSON body `{"attributes": {...}, "content": "<text>"}` is accepted as well. Uploads are capped at 1 MiB (`403 file_size_limit_exceeded`); there are no chunked upload sessions, no new versions of an existing file, and no download.
- `PUT /2.0/files/{file_id}` takes only `{"shared_link": {...}}`: `access` (`open` by default, `company`, `collaborators`), `password` (open links only, at least 8 characters with a number or symbol), `vanity_name`, `unshared_at`, and `permissions` (`can_download`, `can_preview`, `can_edit`). Calling it again changes the link's settings and keeps its URL. Removing a link and changing any other file field are not served.
- No trash, collaborations, comments, tags, metadata, locks or web links. Timestamps are in the studio's Chicago offset.

## Seed data

- Connected account `acct-dana-whitfield`: Dana Whitfield's Box account for Lakeshore Design Studio, with five colleagues (Marcus Oyelaran, Leah Novak, Priya Raman, Hannah Brooks, Tomas Lindqvist) as creators and editors.
- 50 folders and 195 files: four client projects under Clients (Brightwell Lobby Refresh, whose lobby installs October 19 to 30, Harbor Street Cafe Counter and Menu Boards, and the completed Fulton Market Lofts Model Unit and Pilsen Arts Collective Gallery), each with contracts, drawings, specifications, invoices, site photos and meeting notes; six prospects under Proposals (Lumen Coworking, Greenline Dental, whose agreement was signed September 11, Calloway & Finch, Midway Credit Union, Bluebird Hotel Group, Saddlebrook Hospitality), matching their bookings in calendly-api; and Studio Admin, Vendors, Templates, Marketing and Archive 2025.
- Four files carry a shared link already: the public portfolio (open, vanity name `lakeshore-portfolio-2026`), the press kit (open), Brightwell's floor plan (company) and one Brightwell invoice (collaborators).
- 1 OAuth client `box-connector-app`: `root_readonly` and `root_readwrite` granted; a token requested without `scope` carries only `root_readonly`.
