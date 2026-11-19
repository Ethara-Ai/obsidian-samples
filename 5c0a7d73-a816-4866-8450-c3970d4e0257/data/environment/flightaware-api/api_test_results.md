<!-- api-test-results:begin -->
# FlightAware AeroAPI (Mock) - Test Results

GENERATED SECTION. DO NOT HAND-EDIT. `python3 script/gen_api_test_results.py --only flightaware-api` writes everything between the api-test-results markers by sending the requests below to the service in-process; the text after the end marker is kept as written.

Base URL: `http://localhost:8109` (docker-compose: `http://flightaware-api:8109`)

## Authentication

Every operation needs `Authorization: Bearer <token>` from `POST /oauth/token` with client credentials. The connected client `aeroapi-connector-app` (account `acct-harborline-ops`) is granted `flights.read`, `airports.read`; a token requested without `scope` carries `flights.read`. A request without a live token answers `401 invalid_token`, and a live token without the route's scope answers `403 insufficient_scope`.

## Endpoints

Each row is one request the generator sent. **Status** is the answer to the request as shown, sent with a token carrying every granted scope. **No token** is the same request with no `Authorization` header, and **Scope removed** the same request with a token carrying every granted scope except the route's own. The shared `/audit` and `/admin` planes every mock serves are described in `environment/API_DOCUMENTATION.md` and not listed.

| Method | Path | Scope | Request sent | Status | No token | Scope removed |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/oauth/token` | client credentials | `/oauth/token (form body)` | 200 | - | - |
| GET | `/health` | none | `/health` | 200 | - | - |
| GET | `/oauth/tokeninfo` | any live token | `/oauth/tokeninfo` | 200 | 401 | - |
| GET | `/aeroapi/ping` | any live token | `/aeroapi/ping` | 200 | 401 | - |
| GET | `/aeroapi/flights/{ident}` | `flights.read` | `/aeroapi/flights/UAL552` | 200 | 401 | 403 |
| GET | `/aeroapi/flights/{ident}` | `flights.read` | `/aeroapi/flights/DL418?start=2026-10-03T00:00:00Z&end=2026-10-04T00:00:00Z` | 200 | 401 | 403 |
| GET | `/aeroapi/airports/{id}/delays` | `airports.read` | `/aeroapi/airports/KORD/delays` | 200 | 401 | 403 |
| GET | `/aeroapi/airports/{id}/weather/observations` | `airports.read` | `/aeroapi/airports/SFO/weather/observations` | 200 | 401 | 403 |

## Seed files

| File | Records |
| --- | --- |
| `airport_delays.json` | 8 |
| `airports.json` | 15 |
| `flights.json` | 40 |
| `observations.json` | 90 |
<!-- api-test-results:end -->

## Connector operations covered

Check service reachability (`/aeroapi/ping`), Track a flight's status (`/aeroapi/flights/{ident}`), Check airport delays, Check airport weather. All read-only; nothing else is served.

Query and shape rules: `{ident}` is an ICAO (`UAL1234`) or IATA (`UA1234`) flight ident, case-insensitive; `{id}` is an ICAO or IATA airport code. `start`/`end` on flights are ISO 8601 dates or datetimes (a date-only value means 00:00:00Z); a flight is returned when `start <= scheduled_out < end`, oldest first, and no filter returns every seeded flight. Times are UTC. `departure_delay` and `arrival_delay` are seconds against `scheduled_out` and `scheduled_in` (actual when the event happened, otherwise the estimate); they are null for a cancelled flight, and `arrival_delay` is null for a diverted one. A flight is "Delayed" at 15 minutes or more. A diverted flight carries `diverted_to` and has no `actual_in`. Airport delay colors are green below 15 minutes, yellow below 60, red above; the departure and arrival summaries are the largest delay among the reasons that apply to that direction. Observation `clouds[].altitude` is in hundreds of feet, `visibility` in statute miles, `pressure` in hPa.

## Seed data

All data is a snapshot taken at 2026-10-03T18:00:00Z.

- 15 US airports (ICAO, IATA, name, city, timezone)
- 40 flights over 25 idents, 2026-10-01 to 2026-10-05: 12 Scheduled, 4 Scheduled / Delayed, 2 En Route / On Time, 5 En Route / Delayed, 10 Landed / On Time, 4 Landed / Delayed, 2 Cancelled, 1 Diverted
- 8 airport delay reasons across 6 airports (KORD, KATL, KJFK, KSFO, KDEN, KBOS); flights leaving those airports on 2026-10-03 carry matching delays
- 90 hourly weather observations (6 per airport, 12:53Z to 17:53Z on 2026-10-03), with a raw METAR string that agrees with the parsed fields
- 1 OAuth client `aeroapi-connector-app`: `flights.read` and `airports.read` granted; a token requested without `scope` carries only `flights.read`
