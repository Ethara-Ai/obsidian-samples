<!-- api-test-results:begin -->
# Google Slides API (Mock) - Test Results

GENERATED SECTION. DO NOT HAND-EDIT. `python3 script/gen_api_test_results.py --only google-slides-api` writes everything between the api-test-results markers by sending the requests below to the service in-process; the text after the end marker is kept as written.

Base URL: `http://localhost:8118` (docker-compose: `http://google-slides-api:8118`)

## Authentication

Every operation needs `Authorization: Bearer <token>` from `POST /oauth/token` with client credentials. The connected client `gslides-connector-app` (account `acct-dana-whitfield`) is granted `presentations.readonly`, `presentations`; a token requested without `scope` carries `presentations.readonly`. A request without a live token answers `401 invalid_token`, and a live token without the route's scope answers `403 insufficient_scope`.

## Endpoints

Each row is one request the generator sent. **Status** is the answer to the request as shown, sent with a token carrying every granted scope. **No token** is the same request with no `Authorization` header, and **Scope removed** the same request with a token carrying every granted scope except the route's own. The shared `/audit` and `/admin` planes every mock serves are described in `environment/API_DOCUMENTATION.md` and not listed.

| Method | Path | Scope | Request sent | Status | No token | Scope removed |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/oauth/token` | client credentials | `/oauth/token (form body)` | 200 | - | - |
| GET | `/health` | none | `/health` | 200 | - | - |
| GET | `/oauth/tokeninfo` | any live token | `/oauth/tokeninfo` | 200 | 401 | - |
| GET | `/v1/presentations/{presentationId}` | `presentations.readonly` or `presentations` | `/v1/presentations/1LHzfmVr0d7fHB8OFkeAIdDyECSVI331nM` | 200 | 401 | - |
| GET | `/v1/presentations/{presentationId}/pages/{pageObjectId}` | `presentations.readonly` or `presentations` | `/v1/presentations/1LHzfmVr0d7fHB8OFkeAIdDyECSVI331nM/pages/<fourth slide id>` | 200 | 401 | - |
| POST | `/v1/presentations` | `presentations` | `/v1/presentations (JSON body)` | 200 | 401 | 403 |
| POST | `/v1/presentations/{presentationId}:batchUpdate` | `presentations` | `/v1/presentations/<new presentation id>:batchUpdate (JSON body)` | 200 | 401 | 403 |
| POST | `/v1/presentations/{presentationId}:batchUpdate` | `presentations` | `/v1/presentations/1jNaqtPEtGd1eCh0DdL9iYxSyJd86Ok69v:batchUpdate (JSON body)` | 200 | 401 | 403 |

## Seed files

| File | Records |
| --- | --- |
| `elements.json` | 119 |
| `presentations.json` | 5 |
| `slides.json` | 50 |
<!-- api-test-results:end -->

## Connector operations covered

Get a presentation (`GET /v1/presentations/{presentationId}`), create a presentation (`POST /v1/presentations`), get one page (`GET /v1/presentations/{presentationId}/pages/{pageObjectId}`), and `presentations.batchUpdate` with `createSlide`, `insertText` and `replaceAllText`. Nothing else is served.

## Mock simplifications

- One master (`p`, Simple Light) with the predefined layouts `BLANK`, `CAPTION_ONLY`, `TITLE`, `TITLE_AND_BODY`, `TITLE_AND_TWO_COLUMNS`, `TITLE_ONLY`, `SECTION_HEADER`, `ONE_COLUMN_TEXT`, `MAIN_POINT` and `BIG_NUMBER`. Page elements are text boxes (placeholders or free text boxes) and images; there are no tables, groups, lines, videos or charts, and text carries no character or paragraph styling.
- Text indexes count UTF-16 code units from 0, and every paragraph ends in a newline, as on Google. `insertText` takes an index from 0 to the length of the shape's text (default 0); `cellLocation` is a 400 because there are no tables. Speaker notes live in each slide's notes page (`<slideId>:notes`), whose body shape (`<slideId>:notes:body`) takes `insertText`.
- `createSlide` takes `objectId` (5 to 50 characters, unique in the presentation), `insertionIndex` (default: the end), a `predefinedLayout` or `layoutId`, and `placeholderIdMappings` by `layoutPlaceholder` or `layoutPlaceholderObjectId`; the new slide gets the layout's empty placeholders.
- `replaceAllText` matches within each shape on the slides, case-insensitively unless `matchCase` is true; `pageObjectIds` limits it to the slides named. Its reply omits `occurrencesChanged` when nothing matched.
- A batch is atomic: one failing request applies none. `writeControl.requiredRevisionId` must match the current revision; every change gives the presentation a new `revisionId`.
- `presentations.create` takes `title` and an optional `presentationId`; the new deck has one `TITLE` slide. Any other field is refused with a 400 rather than silently dropped, a deliberate deviation from Google, which ignores them.
- Batch request kinds other than `createSlide`, `insertText` and `replaceAllText` (for example `deleteObject`) answer a 400 naming them as unsupported. A query parameter the method does not take is a 400, as on Google.

## Seed data

- Connected account `acct-dana-whitfield` (Dana Whitfield, Lakeshore Design Studio, Chicago), the same account google-drive-api serves
- 5 presentations with 50 slides and 119 page elements: every Google Slides deck in the google-drive-api seed, under the same id and title, so a deck found through Drive opens here
- The content agrees with the Drive comments on these files (slide 4 of `Brightwell Status Deck September` lists the River North install dates as text, which the client's CFO wants as a table; the renders slide still shows option B second; the moodboard's brass reads too yellow and its plaster stays on the north wall) and with the Brightwell brief, budget tracker, material selections and install schedule of the google-docs-api and google-sheets-api seeds
- `Proposal Template` carries `{{PLACEHOLDER}}` fields (`{{CLIENT_NAME}}`, `{{PROJECT_NAME}}`, `{{FEE_TOTAL}}` and others) for `replaceAllText`
- 1 OAuth client `gslides-connector-app`: both scopes granted; a token requested without `scope` carries only `presentations.readonly`
