<!-- api-test-results:begin -->
# Google Docs API (Mock) - Test Results

GENERATED SECTION. DO NOT HAND-EDIT. `python3 script/gen_api_test_results.py --only google-docs-api` writes everything between the api-test-results markers by sending the requests below to the service in-process; the text after the end marker is kept as written.

Base URL: `http://localhost:8110` (docker-compose: `http://google-docs-api:8110`)

## Authentication

Every operation needs `Authorization: Bearer <token>` from `POST /oauth/token` with client credentials. The connected client `gdocs-connector-app` (account `acct-dana-whitfield`) is granted `documents.readonly`, `documents`; a token requested without `scope` carries `documents.readonly`. A request without a live token answers `401 invalid_token`, and a live token without the route's scope answers `403 insufficient_scope`.

## Endpoints

Each row is one request the generator sent. **Status** is the answer to the request as shown, sent with a token carrying every granted scope. **No token** is the same request with no `Authorization` header, and **Scope removed** the same request with a token carrying every granted scope except the route's own. The shared `/audit` and `/admin` planes every mock serves are described in `environment/API_DOCUMENTATION.md` and not listed.

| Method | Path | Scope | Request sent | Status | No token | Scope removed |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/oauth/token` | client credentials | `/oauth/token (form body)` | 200 | - | - |
| GET | `/health` | none | `/health` | 200 | - | - |
| GET | `/oauth/tokeninfo` | any live token | `/oauth/tokeninfo` | 200 | 401 | - |
| GET | `/v1/documents/{documentId}` | `documents.readonly` or `documents` | `/v1/documents/11Ghkpq7Ezu59E2pbjdz7BIbLUHtbo7Dr7` | 200 | 401 | - |
| GET | `/v1/documents/{documentId}` | `documents.readonly` or `documents` | `/v1/documents/11Ghkpq7Ezu59E2pbjdz7BIbLUHtbo7Dr7?includeTabsContent=true` | 200 | 401 | - |
| GET | `/v1/documents/{documentId}` | `documents.readonly` or `documents` | `/v1/documents/11Ghkpq7Ezu59E2pbjdz7BIbLUHtbo7Dr7?fields=title,revisionId` | 200 | 401 | - |
| POST | `/v1/documents` | `documents` | `/v1/documents (JSON body)` | 200 | 401 | 403 |
| POST | `/v1/documents/{documentId}:batchUpdate` | `documents` | `/v1/documents/<new document id>:batchUpdate (JSON body)` | 200 | 401 | 403 |
| POST | `/v1/documents/{documentId}:batchUpdate` | `documents` | `/v1/documents/<new document id>:batchUpdate (JSON body: insertText, updateParagraphStyle, updateTextStyle, createParagraphBullets, deleteParagraphBullets, deleteContentRange, insertTable)` | 200 | 401 | 403 |
| POST | `/v1/documents/{documentId}:batchUpdate` | `documents` | `/v1/documents/11Ghkpq7Ezu59E2pbjdz7BIbLUHtbo7Dr7:batchUpdate (JSON body)` | 200 | 401 | 403 |

## Seed files

| File | Records |
| --- | --- |
| `documents.json` | 25 |
| `paragraphs.json` | 281 |
<!-- api-test-results:end -->

## Connector operations covered

Get a document (`GET /v1/documents/{documentId}`), create a document (`POST /v1/documents`), and `documents.batchUpdate` with `insertText`, `replaceAllText`, `deleteContentRange`, `updateParagraphStyle`, `updateTextStyle`, `createParagraphBullets`, `deleteParagraphBullets` and `insertTable`. Nothing else is served.

## Mock simplifications

- A document has one tab (`t.0`) and no headers, footers, footnotes, inline objects or suggestions. Paragraphs keep their named style, alignment, heading id, list and nesting level, text runs their bold, italic, underline and strikethrough, and a table its rows and cells of paragraphs; `documents.get` returns each in Google's document structure.
- Indexes count UTF-16 code units from 1, after the section break at index 0, exactly as the real API counts them; a table takes one index for its start, one for each row and one for each cell. `insertText` and `insertTable` need exactly one of `location.index` or `endOfSegmentLocation`; an index of 0 or at or past the end of the body is the real API's 400. A newline in inserted or replacement text starts a new paragraph with the same style. `insertTable` inserts a newline, then the table, and does not insert into a table cell.
- `replaceAllText` matches within a paragraph, table cells included, case-insensitively unless `matchCase` is true; its reply omits `occurrencesChanged` when nothing matched, as the real API does.
- `deleteContentRange`, `updateParagraphStyle`, `updateTextStyle`, `createParagraphBullets` and `deleteParagraphBullets` take a `range` in the body; a range outside it, an empty one, or one that starts or ends inside a surrogate pair is a 400 and changes nothing. Deleting across paragraphs joins them, and the paragraph left keeps the properties of the paragraph whose newline remains. The body's last newline, a cell's last newline, the newline before a table and part of a table cannot be deleted (a 400); text inside one cell and a whole table can.
- `updateParagraphStyle` applies `namedStyleType` and `alignment`, and `updateTextStyle` applies `bold`, `italic`, `underline` and `strikethrough`, each only for the fields `fields` names (`*` names them all); a named field the request leaves unset goes back to its default. Another style field named in `fields` is a 400 naming it as unsupported.
- `createParagraphBullets` takes Google's `bulletPreset` values; leading tabs become the nesting level, and when the paragraph just before the range is in a list with the same preset the paragraphs join that list. `deleteParagraphBullets` keeps each paragraph's indent.
- A batch is atomic: one failing request applies none. `writeControl.requiredRevisionId` must match the current revision; `targetRevisionId` is accepted only for the latest revision. Every change gives the document a new `revisionId`.
- `documents.create` takes only `title`; output-only document fields such as `body` are refused with a 400 rather than silently dropped.
- The thirty other batch request kinds (for example `insertPageBreak`, `createHeader`, `insertTableRow`) answer a 400 naming them as unsupported.
- A query parameter the method does not take is a 400, as on Google. `fields` takes a field mask (`title,body.content(paragraph/elements/textRun/content)`); an unknown field is a 400.

## Seed data

- Connected account `acct-dana-whitfield` (Dana Whitfield, Lakeshore Design Studio, Chicago), the same account google-drive-api serves
- 25 documents with 281 paragraphs: every Google Doc in the google-drive-api seed, under the same id and title, so a document found through Drive opens here
- The content agrees with the Drive comments on these files (for example the Studio Handbook lists Hannah twice in the kitchen rota, and the Brightwell brief has no accessibility section and puts Lakefront last)
- `Invoice Template` and `Performance Review Template` carry `{{PLACEHOLDER}}` fields for `replaceAllText`
- 1 OAuth client `gdocs-connector-app`: both scopes granted; a token requested without `scope` carries only `documents.readonly`
