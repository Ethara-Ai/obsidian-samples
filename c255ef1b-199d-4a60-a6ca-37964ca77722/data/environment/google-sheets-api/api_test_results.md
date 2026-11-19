<!-- api-test-results:begin -->
# Google Sheets API (Mock) - Test Results

GENERATED SECTION. DO NOT HAND-EDIT. `python3 script/gen_api_test_results.py --only google-sheets-api` writes everything between the api-test-results markers by sending the requests below to the service in-process; the text after the end marker is kept as written.

Base URL: `http://localhost:8111` (docker-compose: `http://google-sheets-api:8111`)

## Authentication

Every operation needs `Authorization: Bearer <token>` from `POST /oauth/token` with client credentials. The connected client `gsheets-connector-app` (account `acct-dana-whitfield`) is granted `spreadsheets.readonly`, `spreadsheets`; a token requested without `scope` carries `spreadsheets.readonly`. A request without a live token answers `401 invalid_token`, and a live token without the route's scope answers `403 insufficient_scope`.

## Endpoints

Each row is one request the generator sent. **Status** is the answer to the request as shown, sent with a token carrying every granted scope. **No token** is the same request with no `Authorization` header, and **Scope removed** the same request with a token carrying every granted scope except the route's own. The shared `/audit` and `/admin` planes every mock serves are described in `environment/API_DOCUMENTATION.md` and not listed.

| Method | Path | Scope | Request sent | Status | No token | Scope removed |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/oauth/token` | client credentials | `/oauth/token (form body)` | 200 | - | - |
| GET | `/health` | none | `/health` | 200 | - | - |
| GET | `/oauth/tokeninfo` | any live token | `/oauth/tokeninfo` | 200 | 401 | - |
| GET | `/v4/spreadsheets/{spreadsheetId}` | `spreadsheets.readonly` or `spreadsheets` | `/v4/spreadsheets/17MhG1mZB-ymy5rKz_r69BAEGny1KAOziv` | 200 | 401 | - |
| GET | `/v4/spreadsheets/{spreadsheetId}` | `spreadsheets.readonly` or `spreadsheets` | `/v4/spreadsheets/17MhG1mZB-ymy5rKz_r69BAEGny1KAOziv?ranges=Summary!A1:B8&includeGridData=true` | 200 | 401 | - |
| GET | `/v4/spreadsheets/{spreadsheetId}/values/{range}` | `spreadsheets.readonly` or `spreadsheets` | `/v4/spreadsheets/17MhG1mZB-ymy5rKz_r69BAEGny1KAOziv/values/Invoices!A1:I46` | 200 | 401 | - |
| GET | `/v4/spreadsheets/{spreadsheetId}/values/{range}` | `spreadsheets.readonly` or `spreadsheets` | `/v4/spreadsheets/17MhG1mZB-ymy5rKz_r69BAEGny1KAOziv/values/A40:I46` | 200 | 401 | - |
| GET | `/v4/spreadsheets/{spreadsheetId}/values/{range}` | `spreadsheets.readonly` or `spreadsheets` | `/v4/spreadsheets/17MhG1mZB-ymy5rKz_r69BAEGny1KAOziv/values/Summary!A1:Z100?valueRenderOption=UNFORMATTED_VALUE` | 200 | 401 | - |
| PUT | `/v4/spreadsheets/{spreadsheetId}/values/{range}` | `spreadsheets` | `/v4/spreadsheets/1jfS2U8B39Y8cOH-59aYLRx4Emxj1LVdZu/values/Budget!E14?valueInputOption=USER_ENTERED&includeValuesInResponse=true (JSON body)` | 200 | 401 | 403 |
| POST | `/v4/spreadsheets/{spreadsheetId}/values/{range}:append` | `spreadsheets` | `/v4/spreadsheets/1xUAPAtugHP9RVrxlkgq5mKeAW2Wc348ms/values/Expenses!A1:G1:append?valueInputOption=USER_ENTERED (JSON body)` | 200 | 401 | 403 |
| POST | `/v4/spreadsheets` | `spreadsheets` | `/v4/spreadsheets (JSON body)` | 200 | 401 | 403 |

## Seed files

| File | Records |
| --- | --- |
| `rows.json` | 389 |
| `sheets.json` | 27 |
| `spreadsheets.json` | 22 |
<!-- api-test-results:end -->

## Connector operations covered

Get a spreadsheet (`GET /v4/spreadsheets/{spreadsheetId}`), read values (`GET .../values/{range}`), update values (`PUT .../values/{range}`), append rows (`POST .../values/{range}:append`), and create a spreadsheet (`POST /v4/spreadsheets`). Nothing else is served.

## Ranges

- Exact ranges (`Invoices!A2:I46`), quoted sheet names (`'River North'!A1:D11`), whole columns (`Budget!B:B`), whole rows (`Budget!1:3`), half-open ranges (`Invoices!F2:F`) and whole sheets (`Summary`) all parse. A range without a sheet name refers to the first sheet. An unknown sheet or malformed range is `400 Unable to parse range: ...`.
- Reads answer the requested range, clipped to the sheet's grid, and leave out trailing empty rows and columns, so a range larger than the data returns only the data. A range that starts outside the grid is the real API's `exceeds grid limits` 400.
- `values.update` writes from the range's top-left cell; a multi-cell range refuses more rows or columns than it spans (`Requested writing within range [...], but tried writing to row [...]`), a single cell takes any block. `null` skips a cell and `""` clears it. Writing past the grid grows it.
- `values.append` finds the table that starts inside the requested rows, follows it down while rows stay occupied, and writes below it at the table's first column; `INSERT_ROWS` shifts the rows below down, `OVERWRITE` writes over them.

## Mock simplifications

- Cells hold numbers, strings, booleans and formulas. Formulas are evaluated on every read and cover arithmetic, comparison, `&`, and SUM, AVERAGE, MIN, MAX, COUNT, COUNTA, ROUND, IF, ABS, SUMIF and COUNTIF, with references across sheets; an unknown function is `#NAME?`.
- `USER_ENTERED` parses formulas, TRUE/FALSE, numbers with thousands separators, `$` amounts, percentages and dates (`2026-10-04`, `10/4/2026`, `Oct 4, 2026`), and applies the matching number format; `RAW` stores strings as sent.
- Number formats are the currency, number, percent and date patterns the seed uses. There is no styling, merging, filtering, named range or `batchUpdate`.
- A query parameter the method does not take is a 400, as on Google. `fields` takes a field mask; when it is set, `includeGridData` is ignored and the mask decides, as on Google.

## Seed data

- Connected account `acct-dana-whitfield`, the same account google-drive-api serves
- 22 spreadsheets, 27 sheets and 389 rows: every Google Sheet in the google-drive-api seed, under the same id and title
- The content agrees with the Drive comments (row 14 of the Brightwell budget has no Lakefront travel spend, the terrazzo tile costs $42, Q4 contingency is 3 percent, invoice 2026-041 is overdue)
- Totals are formulas, so they follow edits; the Invoice Tracker `Summary` sheet counts and sums the `Invoices` sheet with open-ended ranges, so appended invoices are included
- 1 OAuth client `gsheets-connector-app`: both scopes granted; a token requested without `scope` carries only `spreadsheets.readonly`
