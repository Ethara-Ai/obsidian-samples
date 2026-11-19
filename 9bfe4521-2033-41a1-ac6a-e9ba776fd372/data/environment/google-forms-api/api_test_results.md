<!-- api-test-results:begin -->
# Google Forms API (Mock) - Test Results

GENERATED SECTION. DO NOT HAND-EDIT. `python3 script/gen_api_test_results.py --only google-forms-api` writes everything between the api-test-results markers by sending the requests below to the service in-process; the text after the end marker is kept as written.

Base URL: `http://localhost:8117` (docker-compose: `http://google-forms-api:8117`)

## Authentication

Every operation needs `Authorization: Bearer <token>` from `POST /oauth/token` with client credentials. The connected client `gforms-connector-app` (account `acct-dana-whitfield`) is granted `forms.body.readonly`, `forms.body`, `forms.responses.readonly`; a token requested without `scope` carries `forms.body.readonly`, `forms.responses.readonly`. A request without a live token answers `401 invalid_token`, and a live token without the route's scope answers `403 insufficient_scope`.

## Endpoints

Each row is one request the generator sent. **Status** is the answer to the request as shown, sent with a token carrying every granted scope. **No token** is the same request with no `Authorization` header, and **Scope removed** the same request with a token carrying every granted scope except the route's own. The shared `/audit` and `/admin` planes every mock serves are described in `environment/API_DOCUMENTATION.md` and not listed.

| Method | Path | Scope | Request sent | Status | No token | Scope removed |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/oauth/token` | client credentials | `/oauth/token (form body)` | 200 | - | - |
| GET | `/health` | none | `/health` | 200 | - | - |
| GET | `/oauth/tokeninfo` | any live token | `/oauth/tokeninfo` | 200 | 401 | - |
| GET | `/v1/forms/{formId}` | `forms.body.readonly` or `forms.body` | `/v1/forms/1Snliw-QCNZNy5tkr7Ly6rLJLKASQVtaEz0V3G5F4HuT` | 200 | 401 | 403 |
| GET | `/v1/forms/{formId}/responses` | `forms.responses.readonly` | `/v1/forms/1Snliw-QCNZNy5tkr7Ly6rLJLKASQVtaEz0V3G5F4HuT/responses?pageSize=3` | 200 | 401 | 403 |
| GET | `/v1/forms/{formId}/responses` | `forms.responses.readonly` | `/v1/forms/1Snliw-QCNZNy5tkr7Ly6rLJLKASQVtaEz0V3G5F4HuT/responses?filter=timestamp >= 2026-09-15T00:00:00Z` | 200 | 401 | 403 |
| GET | `/v1/forms/{formId}/responses/{responseId}` | `forms.responses.readonly` | `/v1/forms/1Snliw-QCNZNy5tkr7Ly6rLJLKASQVtaEz0V3G5F4HuT/responses/<response id from the list>` | 200 | 401 | 403 |
| POST | `/v1/forms` | `forms.body` | `/v1/forms (JSON body)` | 200 | 401 | 403 |
| POST | `/v1/forms/{formId}:batchUpdate` | `forms.body` | `/v1/forms/<new form id>:batchUpdate (JSON body)` | 200 | 401 | 403 |
| POST | `/v1/forms/{formId}:batchUpdate` | `forms.body` | `/v1/forms/<new form id>:batchUpdate (JSON body)` | 200 | 401 | 403 |

## Seed files

| File | Records |
| --- | --- |
| `forms.json` | 14 |
| `items.json` | 74 |
| `responses.json` | 233 |
<!-- api-test-results:end -->

## Connector operations covered

Get a form (`GET /v1/forms/{formId}`), create a form (`POST /v1/forms`), `forms.batchUpdate` with `createItem` and `updateItem` to add or change a question (`POST /v1/forms/{formId}:batchUpdate`), list a form's responses (`GET /v1/forms/{formId}/responses`) and get one response (`GET /v1/forms/{formId}/responses/{responseId}`). Nothing else is served.

## Mock simplifications

- Items are questions (choice as `RADIO`, `CHECKBOX` or `DROP_DOWN`, text, scale, date), page breaks or text blocks. Grids, images, videos, time, rating and file-upload questions, `isOther` options and quiz grading are not modelled, and a request naming one is a 400 that says it is not supported.
- `forms.create` takes only `info.title` and `info.documentTitle`, as on Google; any other field is a 400 that says to add items with `forms.batchUpdate`.
- A batch is atomic: one failing request applies none. `createItem` needs `location.index` from 0 to the item count and assigns the item id (and the question id, unless the request gives one not already in use). `updateItem` needs `location.index` of an existing item and an `updateMask` over `title`, `description` and `questionItem` (`*` means all three); replacing `questionItem` may change the question kind but keeps its `questionId`. `writeControl.requiredRevisionId` and `targetRevisionId` must name the current revision. Every change gives the form a new `revisionId`; `includeFormInResponse` returns the updated form.
- Responses are read-only and carry `textAnswers` only. `filter` takes `timestamp > T` or `timestamp >= T` over `lastSubmittedTime`, with `T` an RFC 3339 UTC time, as on Google; `pageSize` defaults to 5000. Responses are listed oldest first.
- A query parameter the method does not take is a 400, as on Google.

## Seed data

- Connected account `acct-dana-whitfield` (Dana Whitfield, Lakeshore Design Studio, Chicago), the same account google-drive-api and google-contacts-api serve
- 14 forms with 74 items and 233 responses: guest and resident surveys for Brightwell Hospitality, Harbor Street Cafe and Fulton Market Lofts, the Brightwell team's vote between the two lobby renders in the google-drive-api `Lobby Redesign` folder, the client intake questionnaire and post-project survey, the studio coordinator application from the `Hiring Plan 2026` sheet, vendor onboarding, workshop and volunteer sign-ups, an equipment request form, a team lunch order and the holiday party RSVP
- Respondents who are people of the other Lakeshore seeds (the studio, the Brightwell staff, clients, vendors) answer under the emails those seeds give them, and their answers agree with those seeds; survey and sign-up respondents are anonymous or invented
- `Brightwell Staff Lounge Preferences` has no responses yet
- 1 OAuth client `gforms-connector-app`: all three scopes granted; a token requested without `scope` carries `forms.body.readonly` and `forms.responses.readonly` but not `forms.body`
