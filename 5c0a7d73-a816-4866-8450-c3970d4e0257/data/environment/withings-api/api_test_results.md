<!-- api-test-results:begin -->
# Withings API (Mock) - Test Results

GENERATED SECTION. DO NOT HAND-EDIT. `python3 script/gen_api_test_results.py --only withings-api` writes everything between the api-test-results markers by sending the requests below to the service in-process; the text after the end marker is kept as written.

Base URL: `http://localhost:8135` (docker-compose: `http://withings-api:8135`)

## Authentication

Every operation needs `Authorization: Bearer <token>` from `POST /oauth/token` with client credentials. The connected client `withings-connector-app` (account `acct-dana-whitfield`) is granted `user.metrics`, `user.activity`, `user.info`; a token requested without `scope` carries `user.metrics`, `user.activity`, `user.info`. A request without a live token answers `401 invalid_token`, and a live token without the route's scope answers `403 insufficient_scope`.

## Endpoints

Each row is one request the generator sent. **Status** is the answer to the request as shown, sent with a token carrying every granted scope. **No token** is the same request with no `Authorization` header, and **Scope removed** the same request with a token carrying every granted scope except the route's own. The shared `/audit` and `/admin` planes every mock serves are described in `environment/API_DOCUMENTATION.md` and not listed.

| Method | Path | Scope | Request sent | Status | No token | Scope removed |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/oauth/token` | client credentials | `/oauth/token (form body)` | 200 | - | - |
| GET | `/health` | none | `/health` | 200 | - | - |
| GET | `/oauth/tokeninfo` | any live token | `/oauth/tokeninfo` | 200 | 401 | - |
| POST | `/measure` | `user.metrics` | `/measure (form: action=getmeas&meastypes=1,6,8&category=1&startdate=1788238800&enddate=1790830799)` | 200 | 401 | 403 |
| POST | `/measure` | `user.metrics` | `/measure (form: action=getmeas&category=1)` | 200 | 401 | 403 |
| POST | `/measure` | `user.metrics` | `/measure (form: action=getmeas&category=1&offset=<offset the first page returned>)` | 200 | 401 | 403 |
| POST | `/measure` | `user.metrics` | `/measure (form: action=getmeas&meastypes=9,10,11&lastupdate=1790830800)` | 200 | 401 | 403 |
| POST | `/v2/measure` | `user.activity` | `/v2/measure (form: action=getactivity&startdateymd=2026-09-28&enddateymd=2026-10-04&data_fields=steps,calories,intense)` | 200 | 401 | 403 |
| POST | `/v2/sleep` | `user.activity` | `/v2/sleep (form: action=getsummary&startdateymd=2026-09-28&enddateymd=2026-10-05)` | 200 | 401 | 403 |
| POST | `/v2/sleep` | `user.activity` | `/v2/sleep (form: action=getsummary&lastupdate=1788238800&data_fields=sleep_score,total_sleep_time)` | 200 | 401 | 403 |
| POST | `/v2/user` | `user.info` | `/v2/user (form: action=getdevice)` | 200 | 401 | 403 |

## Seed files

| File | Records |
| --- | --- |
| `activity.json` | 96 |
| `devices.json` | 4 |
| `measuregrps.json` | 128 |
| `sleep.json` | 97 |
<!-- api-test-results:end -->

## Connector operations covered

Body measures (weight, body fat, blood pressure) for a date range (`POST /measure`, `action=getmeas`), daily activity (`POST /v2/measure`, `action=getactivity`), sleep summaries (`POST /v2/sleep`, `action=getsummary`), and devices (`POST /v2/user`, `action=getdevice`). Nothing else is served, and nothing is written.

## API shape

The routes follow the Withings public API's action-style requests: one `POST` per webservice with `action` and its parameters as `application/x-www-form-urlencoded` form fields, answered with `{"status", "body"}`. The scopes are Withings' OAuth scopes. Page sizes are this mock's own.

## Mock simplifications

- As Withings does, errors answer HTTP 200 with a nonzero `status` and an `error` message: `503` (invalid parameters, including a form field the action does not take, a JSON body, a repeated field, or any query parameter) and `2554` (a wrong action for the webservice). A path the mock does not serve answers `404` and a `GET` answers `405`, both with `status` `2554`.
- `getmeas` returns measure groups newest first, 100 per page (`more` 1 and the next `offset` when there are more). `meastype` or `meastypes` keep only those measures (and the groups that have them), `category` picks real measures (1) or goals (2), `startdate` and `enddate` (Unix seconds, inclusive) or `lastupdate` (groups modified since) filter, and `offset` pages. A value is `value` x 10^`unit`.
- `getactivity` and `getsummary` need `startdateymd` and `enddateymd` (local dates, inclusive) or `lastupdate`, list oldest first, 50 per page, and take `offset` and `data_fields` (the activity fields, or the keys of a night's `data`, to return).
- `getdevice` lists the account's devices with model, battery and first and last session.
- No intraday activity, workouts, sleep stages, heart (ECG) or notification webservices.

## Seed data

- Connected account `acct-dana-whitfield`: Dana Whitfield's Withings account (America/Chicago) with a Body+ scale, a BPM Connect blood pressure monitor, a ScanWatch 2 (battery low) and a Sleep Analyzer. All values are invented.
- 128 measure groups: 80 morning weigh-ins from July 1 to October 5, 2026 (weight from 65.37 to 64.20 kg, body fat from 28.1 to 27.2 percent, with fat mass, fat-free mass, muscle, bone and hydration), 46 evening blood pressure readings averaging 118/75 (higher, around 129/83, in the week of September 21), the height entered at setup, and a goal of 62.5 kg. One weigh-in on August 13 was ambiguous and confirmed two days later, so its `modified` is later than its `created`.
- 97 nights of sleep summaries (July 1 to October 5): bed after the evening's workouts and drives, up before the next morning's ride or drive in peloton-api and tessie-api, sleep scores from 58 to 93.
- 96 days of activity (July 1 to October 4): steps, distance, calories and heart-rate zones, with each day's Peloton workouts counted as intense or moderate time and a 14,000-step Sunday in Lake Geneva on October 4.
- 1 OAuth client `withings-connector-app`: `user.metrics`, `user.activity` and `user.info`, all carried by a token requested without `scope`.
