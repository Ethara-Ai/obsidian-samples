---
name: google-drive-api-connector
description: >
  Google Drive API (Mock) mock HTTP API. Base URL is provided via the
  `GOOGLE_DRIVE_API_URL` environment variable. 18 endpoint(s) across DELETE, GET, PATCH, POST.
  Every operation needs an OAuth bearer token that carries the operation's scope.
---

# Google Drive API (Mock)

Mock HTTP API. **All requests go to the base URL in `$GOOGLE_DRIVE_API_URL`.** Every operation needs a bearer token, and a token covers only the scopes it was issued with: a connected account is not permission for every action. Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `GOOGLE_DRIVE_API_URL` | Base URL for all requests (e.g. `http://google-drive-api:8106`) |
| `GOOGLE_DRIVE_CLIENT_ID` | OAuth client id of the connected account, when the task provides it |
| `GOOGLE_DRIVE_CLIENT_SECRET` | OAuth client secret of the connected account, when the task provides it |

## Authentication

1. Exchange the client credentials for an access token: `POST /oauth/token` with `grant_type=client_credentials`, `client_id`, `client_secret`, and optionally `scope` (space-separated). Form-encoded and JSON bodies are both accepted.
2. Send `Authorization: Bearer <access_token>` on every operation.
3. `GET /oauth/tokeninfo` reports the presented token's scopes and expiry.

A token requested without `scope` carries only the default scopes (`drive.readonly`). Ask for any other scope explicitly. A `401 invalid_token` means the token is missing, expired, or revoked; get a new one. A `403 insufficient_scope` names the `required_scope`; request a token that carries it. The token endpoint answers `invalid_scope` when the account never granted a scope to this client. `grant_type=refresh_token` exchanges a refresh token for a new access token.

## Scopes

| Scope | Operations |
|-------|------------|
| `drive.file` | POST `/drive/v3/files`, PATCH `/drive/v3/files/{fileId}`, DELETE `/drive/v3/files/{fileId}`, POST `/upload/drive/v3/files`, PATCH `/upload/drive/v3/files/{fileId}`, POST `/drive/v3/files/{fileId}/comments`, PATCH `/drive/v3/files/{fileId}/revisions/{revisionId}` |
| `drive.readonly` | GET `/drive/v3/files`, GET `/drive/v3/files/{fileId}`, GET `/drive/v3/files/{fileId}/export`, GET `/drive/v3/files/{fileId}/permissions`, GET `/drive/v3/files/{fileId}/comments`, GET `/drive/v3/files/{fileId}/revisions`, GET `/drive/v3/files/{fileId}/revisions/{revisionId}` |
| `drive.sharing` | POST `/drive/v3/files/{fileId}/permissions`, DELETE `/drive/v3/files/{fileId}/permissions/{permissionId}` |

## Endpoints

| Method | Path |
|--------|------|
| POST | `/oauth/token` |
| GET | `/oauth/tokeninfo` |
| GET | `/drive/v3/files` |
| GET | `/drive/v3/files/{fileId}` |
| GET | `/drive/v3/files/{fileId}/export` |
| POST | `/drive/v3/files` |
| PATCH | `/drive/v3/files/{fileId}` |
| DELETE | `/drive/v3/files/{fileId}` |
| POST | `/upload/drive/v3/files` |
| PATCH | `/upload/drive/v3/files/{fileId}` |
| GET | `/drive/v3/files/{fileId}/permissions` |
| POST | `/drive/v3/files/{fileId}/permissions` |
| DELETE | `/drive/v3/files/{fileId}/permissions/{permissionId}` |
| GET | `/drive/v3/files/{fileId}/comments` |
| POST | `/drive/v3/files/{fileId}/comments` |
| GET | `/drive/v3/files/{fileId}/revisions` |
| GET | `/drive/v3/files/{fileId}/revisions/{revisionId}` |
| PATCH | `/drive/v3/files/{fileId}/revisions/{revisionId}` |

## Usage

```bash
TOKEN=$(curl -s -X POST "$GOOGLE_DRIVE_API_URL/oauth/token" -d grant_type=client_credentials \
  -d client_id="$GOOGLE_DRIVE_CLIENT_ID" -d client_secret="$GOOGLE_DRIVE_CLIENT_SECRET" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$GOOGLE_DRIVE_API_URL/drive/v3/files?pageSize=10&orderBy=modifiedTime%20desc" -H "Authorization: Bearer $TOKEN"
```

## Uploads, downloads and deletes

- `POST /upload/drive/v3/files?uploadType=media`: the request body is the file's bytes and `Content-Type` its type; the file is named `Untitled` (rename it with `PATCH /drive/v3/files/{fileId}`).
- `POST /upload/drive/v3/files?uploadType=multipart`: a `multipart/related` body (curl's `-F` `multipart/form-data` works too) whose first part is the JSON metadata (`name`, `mimeType`, `parents`, `description`) and whose second part is the content with its own `Content-Type`.
- A JSON body `{"name", "mimeType", "content", "parents", "description"}` with text in `content` also creates a file, with `uploadType=multipart` or none.
- `PATCH /upload/drive/v3/files/{fileId}` with `uploadType=media` replaces the content (the file keeps its type); with `uploadType=multipart` the metadata part may also change `name`, `mimeType` and `description`. Each upload becomes the file's new head revision.
- `GET /drive/v3/files/{fileId}?alt=media` downloads the content, text or binary, byte for byte. A folder or a Google Docs editors file answers `403 fileNotDownloadable`; export a Doc instead.
- `DELETE /drive/v3/files/{fileId}` deletes the file for good, a folder with everything in it; `PATCH /drive/v3/files/{fileId}` with `{"trashed": true}` moves it to the trash instead.

```bash
curl -s -X POST "$GOOGLE_DRIVE_API_URL/upload/drive/v3/files?uploadType=multipart" -H "Authorization: Bearer $TOKEN" \
  -F 'metadata={"name": "report.pdf"};type=application/json' -F 'file=@report.pdf;type=application/pdf'
curl -s "$GOOGLE_DRIVE_API_URL/drive/v3/files/$FILE_ID?alt=media" -H "Authorization: Bearer $TOKEN" -o report.pdf
```

## Paging

- `GET /drive/v3/files` returns 100 per page by default (`pageSize`, up to 1000); when an answer carries `nextPageToken`, send it back as `pageToken` for the next page.
