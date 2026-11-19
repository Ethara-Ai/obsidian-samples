<!-- api-test-results:begin -->
# Google Drive API (Mock) - Test Results

GENERATED SECTION. DO NOT HAND-EDIT. `python3 script/gen_api_test_results.py --only google-drive-api` writes everything between the api-test-results markers by sending the requests below to the service in-process; the text after the end marker is kept as written.

Base URL: `http://localhost:8106` (docker-compose: `http://google-drive-api:8106`)

## Authentication

Every operation needs `Authorization: Bearer <token>` from `POST /oauth/token` with client credentials. The connected client `drive-connector-app` (account `acct-dana-whitfield`) is granted `drive.readonly`, `drive.file`, `drive.sharing`; a token requested without `scope` carries `drive.readonly`. A request without a live token answers `401 invalid_token`, and a live token without the route's scope answers `403 insufficient_scope`.

## Endpoints

Each row is one request the generator sent. **Status** is the answer to the request as shown, sent with a token carrying every granted scope. **No token** is the same request with no `Authorization` header, and **Scope removed** the same request with a token carrying every granted scope except the route's own. The shared `/audit` and `/admin` planes every mock serves are described in `environment/API_DOCUMENTATION.md` and not listed.

| Method | Path | Scope | Request sent | Status | No token | Scope removed |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/oauth/token` | client credentials | `/oauth/token (form body)` | 200 | - | - |
| GET | `/health` | none | `/health` | 200 | - | - |
| GET | `/oauth/tokeninfo` | any live token | `/oauth/tokeninfo` | 200 | 401 | - |
| GET | `/drive/v3/files` | `drive.readonly` | `/drive/v3/files?pageSize=10&orderBy=modifiedTime desc` | 200 | 401 | 403 |
| GET | `/drive/v3/files` | `drive.readonly` | `/drive/v3/files?q=name contains 'invoice'` | 200 | 401 | 403 |
| GET | `/drive/v3/files` | `drive.readonly` | `/drive/v3/files?q=sharedWithMe = false and name contains 'handbook'` | 200 | 401 | 403 |
| GET | `/drive/v3/files/{fileId}` | `drive.readonly` | `/drive/v3/files/1nMTHxx2-YAvai5wOVjhSvMAzjbWQzuhLa` | 200 | 401 | 403 |
| GET | `/drive/v3/files/{fileId}/export` | `drive.readonly` | `/drive/v3/files/17Er-fyawWVMekXr_X-vqPoPMUgbnitdJd/export?mimeType=text/plain` | 200 | 401 | 403 |
| POST | `/drive/v3/files` | `drive.file` | `/drive/v3/files (JSON body)` | 200 | 401 | 403 |
| PATCH | `/drive/v3/files/{fileId}` | `drive.file` | `/drive/v3/files/1nMTHxx2-YAvai5wOVjhSvMAzjbWQzuhLa?addParents=1rSB70Amcbioy36UmZViO5O27pPrGvK7TR&removeParents=1aRZ689Ly8tps6ueNXSI-ZQ6PZwSFvZGD0 (JSON body)` | 200 | 401 | 403 |
| POST | `/upload/drive/v3/files` | `drive.file` | `/upload/drive/v3/files?uploadType=multipart (JSON body)` | 200 | 401 | 403 |
| POST | `/upload/drive/v3/files` | `drive.file` | `/upload/drive/v3/files?uploadType=multipart (multipart body: JSON metadata, then text/plain content)` | 200 | 401 | 403 |
| POST | `/upload/drive/v3/files` | `drive.file` | `/upload/drive/v3/files?uploadType=media (media body: a 67-byte PNG)` | 200 | 401 | 403 |
| GET | `/drive/v3/files/{fileId}` | `drive.readonly` | `/drive/v3/files/<site-visit.txt id>?alt=media` | 200 | 401 | 403 |
| PATCH | `/upload/drive/v3/files/{fileId}` | `drive.file` | `/upload/drive/v3/files/<site-visit.txt id>?uploadType=media (media body: the new text)` | 200 | 401 | 403 |
| DELETE | `/drive/v3/files/{fileId}` | `drive.file` | `/drive/v3/files/<uploaded PNG id>` | 204 | 401 | 403 |
| GET | `/drive/v3/files/{fileId}/permissions` | `drive.readonly` | `/drive/v3/files/1nMTHxx2-YAvai5wOVjhSvMAzjbWQzuhLa/permissions` | 200 | 401 | 403 |
| POST | `/drive/v3/files/{fileId}/permissions` | `drive.sharing` | `/drive/v3/files/1nMTHxx2-YAvai5wOVjhSvMAzjbWQzuhLa/permissions (JSON body)` | 200 | 401 | 403 |
| DELETE | `/drive/v3/files/{fileId}/permissions/{permissionId}` | `drive.sharing` | `/drive/v3/files/1nMTHxx2-YAvai5wOVjhSvMAzjbWQzuhLa/permissions/<permission id>` | 204 | 401 | 403 |
| GET | `/drive/v3/files/{fileId}/comments` | `drive.readonly` | `/drive/v3/files/1nMTHxx2-YAvai5wOVjhSvMAzjbWQzuhLa/comments` | 200 | 401 | 403 |
| POST | `/drive/v3/files/{fileId}/comments` | `drive.file` | `/drive/v3/files/1nMTHxx2-YAvai5wOVjhSvMAzjbWQzuhLa/comments (JSON body)` | 200 | 401 | 403 |
| GET | `/drive/v3/files/{fileId}/revisions` | `drive.readonly` | `/drive/v3/files/17Er-fyawWVMekXr_X-vqPoPMUgbnitdJd/revisions` | 200 | 401 | 403 |
| GET | `/drive/v3/files/{fileId}/revisions/{revisionId}` | `drive.readonly` | `/drive/v3/files/17Er-fyawWVMekXr_X-vqPoPMUgbnitdJd/revisions/0B0gOv-DUkIC9LFD5Gihb1LhZwpIT0Qv` | 200 | 401 | 403 |
| PATCH | `/drive/v3/files/{fileId}/revisions/{revisionId}` | `drive.file` | `/drive/v3/files/1GTE1fjcPm0o73iICc76gmBRIlReWcE5_C/revisions/0Btc7iGlkYiWmM8W539s_QJ61pdrq2UO (JSON body)` | 200 | 401 | 403 |

## Seed files

| File | Records |
| --- | --- |
| `accounts.json` | 1 |
| `comments.json` | 31 |
| `directory.json` | 14 |
| `files.json` | 96 |
| `permissions.json` | 140 |
| `replies.json` | 26 |
| `revisions.json` | 65 |
<!-- api-test-results:end -->

## Connector operations covered

`.files` (list, retrieve, create, update, delete, download with `alt=media`, export), `.upload` (create and update content), `.permissions` (read and manage), `.comments` (read and manage), `.revisions` (retrieve and manage), `.search` and `.list` (both served by `GET /drive/v3/files` with the `q` parameter). Export serves a Google Doc as `text/plain` only.

## Mock simplifications

- `POST /upload/drive/v3/files` takes the file's bytes with `uploadType=media` (named `Untitled`, typed by `Content-Type`), a `multipart/related` or `multipart/form-data` body of JSON metadata then content with `uploadType=multipart`, or this mock's JSON body `{"name", "mimeType", "content", "parents"?, "description"?}` with text in `content` (`uploadType` omitted or `multipart`). Text and binary content are kept byte for byte, `size` is the byte length, and a first revision is created. `uploadType=resumable` is a 400. Uploading a Google-native type (Docs/Sheets/Slides/Forms) or a folder type is a 400.
- `PATCH /upload/drive/v3/files/{fileId}` replaces the content (`uploadType=media`, the file keeps its type, or `multipart`, whose metadata may also change `name`, `mimeType` and `description`, or the JSON body) as a new head revision; a folder or a Google Docs editors file is a 400.
- `GET /drive/v3/files/{fileId}?alt=media` returns the head revision's content with the file's type; a folder or a Google Docs editors file is `403 fileNotDownloadable`. A seeded binary file's revision holds descriptive text, which is what it downloads.
- `DELETE /drive/v3/files/{fileId}` deletes the file for good with its permissions, comments and revisions, and a folder with everything inside it; it answers `204`.
- A file has exactly one parent. `addParents`/`removeParents` (query parameters on PATCH) move it; a result with zero or two parents, a missing folder, or a move into the file's own subtree is a 400.
- Trashing a folder trashes everything inside it; restoring the folder restores only what that trashing trashed.
- `q` supports `name = '...'`, `name contains '...'` (case-insensitive substring), `fullText contains '...'` (name, description and head revision text), `mimeType = '...'`, `mimeType != '...'`, `'<folderId>' in parents` (the alias `root` works), `trashed = true|false`, `starred = true|false`, `sharedWithMe` or `sharedWithMe = true|false`, and `modifiedTime` with `>`, `>=`, `<` or `<=` against an RFC 3339 timestamp, joined by `and`/`or` with parentheses (`and` binds tighter). Anything else is `400 invalidQuery`. Trashed files are left out unless `q` mentions `trashed`. Every file this mock serves is owned by the connected account, so `sharedWithMe` matches none of them.
- Drive also lists every document, spreadsheet, presentation and form the google-docs-api, google-sheets-api, google-slides-api and google-forms-api seeds hold, a task's own data folder for those mocks included, as Google files (`application/vnd.google-apps.document`, `.spreadsheet`, `.presentation`, `.form`) filed in their owner's root folder. A file is the connected account's when its `owner_account_id` is the account id the token names, whether or not `accounts.json` has that account; a file `files.json` names is listed once, as `files.json` has it. Drive and those mocks are one system, as in Google: when one of them is deployed in the run, every Drive call first reads its live files over its peer routes (`environment/_linked_peer.py`), so a file created, renamed (its title; a form's `documentTitle`), edited or deleted there is seen here at once, an edit moves `modifiedTime`, and `PATCH` with a new `name`, `DELETE`, or `POST /drive/v3/files` with a Google editor `mimeType` renames, deletes or creates the document, spreadsheet, presentation or form there. Trashing does not touch it. A deployed editor mock that does not answer makes every Drive call `503 backendError` and adds a row to the `peer_failures` table, which the harness reports as `environment_faults.json`; Drive never answers from a seed that may no longer be true. An editor mock that is not deployed cannot change, so its seed is read instead: beside this service, or, in a delivered bundle where each mock is built from its own folder, from the copies its packager puts in `google-drive-api/linked/`.
- An account id the token names that `accounts.json` does not have is served as an empty Drive of its own (its root folder id derived from the account id), holding only the Google files above it owns; nothing answers 500. `script/preflight_task.py` fails a task whose Drive `auth.json` names such an account when the task ships Drive data of its own.
- `GET /drive/v3/files/{fileId}/export?mimeType=text/plain` returns a Google Doc's current text, one line per paragraph and one per table cell paragraph, read from google-docs-api. Any other target type, or a Google file that is not a Doc, is `400 badRequest`; a file that is not a Google Docs editors file is `403 fileNotExportable`.
- `orderBy` takes `name`, `modifiedTime`, `createdTime`, comma separated, each with an optional ` desc`; the default is `modifiedTime desc`.
- `fields` takes a Drive field selector (`nextPageToken,files(id,name)`); an unknown field is a 400. Without it the full resource is returned.
- Permissions: `type` user/group needs `emailAddress`, domain needs `domain`, anyone takes neither; `role` is reader, commenter or writer. Granting `owner` (ownership transfer) is a 400, as is deleting the owner permission. Sharing again with the same grantee updates the role.
- Revisions: `keepForever` applies to binary files only and `published` to Google Docs editors files only; each other combination is a 400, as is an empty body.

## Seed data

- 1 connected account `acct-dana-whitfield` (operations manager, Lakeshore Design Studio, Chicago); 14 directory entries (colleagues, a team group, clients, vendors)
- 12 folders in a 3-level tree and 84 files (Docs, Sheets, Slides, PDF, PNG/JPEG images, plain text); 6 trashed, 8 starred
- 140 permissions (one owner permission per item plus 44 shares: colleagues, the team group, clients, domain-wide and anyone-with-link)
- 31 comments (11 resolved) and 26 replies
- 65 revisions across 26 files (2 to 4 each); two published Docs revisions and three kept-forever revisions
- 1 OAuth client `drive-connector-app`: every scope granted; a token requested without `scope` carries only `drive.readonly`
