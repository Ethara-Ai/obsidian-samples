---
name: google-docs-api-connector
description: >
  Google Docs API (Mock) mock HTTP API. Base URL is provided via the
  `GOOGLE_DOCS_API_URL` environment variable. 5 endpoint(s) across GET, POST.
  Every operation needs an OAuth bearer token that carries the operation's scope.
---

# Google Docs API (Mock)

Mock HTTP API. **All requests go to the base URL in `$GOOGLE_DOCS_API_URL`.** Every operation needs a bearer token, and a token covers only the scopes it was issued with: a connected account is not permission for every action. Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `GOOGLE_DOCS_API_URL` | Base URL for all requests (e.g. `http://google-docs-api:8110`) |
| `GOOGLE_DOCS_CLIENT_ID` | OAuth client id of the connected account, when the task provides it |
| `GOOGLE_DOCS_CLIENT_SECRET` | OAuth client secret of the connected account, when the task provides it |

## Authentication

1. Exchange the client credentials for an access token: `POST /oauth/token` with `grant_type=client_credentials`, `client_id`, `client_secret`, and optionally `scope` (space-separated). Form-encoded and JSON bodies are both accepted.
2. Send `Authorization: Bearer <access_token>` on every operation.
3. `GET /oauth/tokeninfo` reports the presented token's scopes and expiry.

A token requested without `scope` carries only the default scopes (`documents.readonly`). Ask for any other scope explicitly. A `401 invalid_token` means the token is missing, expired, or revoked; get a new one. A `403 insufficient_scope` names the `required_scope`; request a token that carries it. The token endpoint answers `invalid_scope` when the account never granted a scope to this client. `grant_type=refresh_token` exchanges a refresh token for a new access token.

## Scopes

| Scope | Operations |
|-------|------------|
| `documents` | POST `/v1/documents`, POST `/v1/documents/{documentId}:batchUpdate` |
| `documents.readonly` | GET `/v1/documents/{documentId}` |

A token carrying `documents` also covers every `documents.readonly` operation, so it does not need `documents.readonly` as well. A token carrying only `documents.readonly` cannot do the `documents` operations.

## Endpoints

| Method | Path |
|--------|------|
| POST | `/oauth/token` |
| GET | `/oauth/tokeninfo` |
| GET | `/v1/documents/{documentId}` |
| POST | `/v1/documents` |
| POST | `/v1/documents/{documentId}:batchUpdate` |

## Usage

```bash
TOKEN=$(curl -s -X POST "$GOOGLE_DOCS_API_URL/oauth/token" -d grant_type=client_credentials \
  -d client_id="$GOOGLE_DOCS_CLIENT_ID" -d client_secret="$GOOGLE_DOCS_CLIENT_SECRET" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$GOOGLE_DOCS_API_URL/v1/documents/11Ghkpq7Ezu59E2pbjdz7BIbLUHtbo7Dr7" -H "Authorization: Bearer $TOKEN"
```

## batchUpdate requests

`POST /v1/documents/{documentId}:batchUpdate` applies its `requests` in order, each to the document as the requests before it left it, and applies none of them when one fails. Each request sets exactly one of:

- `insertText`: `text` at `location.index` or at `endOfSegmentLocation`; a newline in it starts a new paragraph.
- `replaceAllText`: every `containsText.text` (`matchCase` optional) becomes `replaceText`, in table cells too.
- `deleteContentRange`: deletes `range`, from `startIndex` up to but not including `endIndex`; deleting a paragraph's newline joins it to the next paragraph. A table is deleted whole or only inside one cell.
- `updateParagraphStyle`: sets `paragraphStyle.namedStyleType` (`NORMAL_TEXT`, `TITLE`, `SUBTITLE`, `HEADING_1` to `HEADING_6`) and `paragraphStyle.alignment` (`START`, `CENTER`, `END`, `JUSTIFIED`) on every paragraph `range` touches, only those `fields` names.
- `updateTextStyle`: sets `textStyle.bold`, `italic`, `underline` and `strikethrough` on the text in `range`, only those `fields` names; a field `fields` names and `textStyle` leaves out is cleared.
- `createParagraphBullets`: makes the paragraphs `range` touches a list in `bulletPreset` (for example `BULLET_DISC_CIRCLE_SQUARE` or `NUMBERED_DECIMAL_ALPHA_ROMAN`); leading tabs become the nesting level.
- `deleteParagraphBullets`: removes the bullets of the paragraphs `range` touches, keeping their indent.
- `insertTable`: a table of `rows` by `columns` empty cells at `location.index` or at `endOfSegmentLocation`, after a newline it inserts first.

Indexes count UTF-16 code units from 1; read the document with `GET /v1/documents/{documentId}` for the current ones. A range outside the body, or one that starts or ends inside a character such as an emoji, is a `400`. Every other Docs request kind (headers, footers, images, named ranges, table rows and columns, ...) is a `400` naming it as not supported.

```bash
curl -s -X POST "$GOOGLE_DOCS_API_URL/v1/documents/$DOC_ID:batchUpdate" -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"requests": [
  {"updateParagraphStyle": {"range": {"startIndex": 1, "endIndex": 10}, "paragraphStyle": {"namedStyleType": "HEADING_1"}, "fields": "namedStyleType"}},
  {"createParagraphBullets": {"range": {"startIndex": 10, "endIndex": 40}, "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE"}}]}'
```
