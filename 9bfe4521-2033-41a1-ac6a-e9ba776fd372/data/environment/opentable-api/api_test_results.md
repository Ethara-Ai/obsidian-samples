<!-- api-test-results:begin -->
# OpenTable API (Mock) - Test Results

GENERATED SECTION. DO NOT HAND-EDIT. `python3 script/gen_api_test_results.py --only opentable-api` writes everything between the api-test-results markers by sending the requests below to the service in-process; the text after the end marker is kept as written.

Base URL: `http://localhost:8114` (docker-compose: `http://opentable-api:8114`)

## Authentication

Every operation needs `Authorization: Bearer <token>` from `POST /oauth/token` with client credentials. The connected client `opentable-connector-app` (account `acct-dana-whitfield`) is granted `directory.read`, `availability.read`, `reservations.read`, `reservations.write`; a token requested without `scope` carries `directory.read`, `availability.read`, `reservations.read`. A request without a live token answers `401 invalid_token`, and a live token without the route's scope answers `403 insufficient_scope`.

## Endpoints

Each row is one request the generator sent. **Status** is the answer to the request as shown, sent with a token carrying every granted scope. **No token** is the same request with no `Authorization` header, and **Scope removed** the same request with a token carrying every granted scope except the route's own. The shared `/audit` and `/admin` planes every mock serves are described in `environment/API_DOCUMENTATION.md` and not listed.

| Method | Path | Scope | Request sent | Status | No token | Scope removed |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/oauth/token` | client credentials | `/oauth/token (form body)` | 200 | - | - |
| GET | `/health` | none | `/health` | 200 | - | - |
| GET | `/oauth/tokeninfo` | any live token | `/oauth/tokeninfo` | 200 | 401 | - |
| GET | `/v2/directory/restaurants` | `directory.read` | `/v2/directory/restaurants?city=Chicago&cuisine=Italian` | 200 | 401 | 403 |
| GET | `/v2/directory/restaurants` | `directory.read` | `/v2/directory/restaurants?term=Marrow` | 200 | 401 | 403 |
| GET | `/v2/availability/{rid}` | `availability.read` | `/v2/availability/104000?start_date_time=2026-10-16T19:00&party_size=2` | 200 | 401 | 403 |
| GET | `/v2/availability/{rid}` | `availability.read` | `/v2/availability/104000?start_date_time=2026-10-15T19:00&party_size=2&forward_minutes=30&backward_minutes=0` | 200 | 401 | 403 |
| POST | `/v2/booking/{rid}/slot_locks` | `reservations.write` | `/v2/booking/104000/slot_locks (JSON body)` | 201 | 401 | 403 |
| POST | `/v2/booking/{rid}/reservations` | `reservations.write` | `/v2/booking/104000/reservations (JSON body)` | 201 | 401 | 403 |
| GET | `/v2/booking/{rid}/reservations/{confirmation_number}` | `reservations.read` | `/v2/booking/104000/reservations/<confirmation number>` | 200 | 401 | 403 |
| DELETE | `/v2/booking/{rid}/reservations/{confirmation_number}` | `reservations.write` | `/v2/booking/104000/reservations/<confirmation number>` | 200 | 401 | 403 |

## Seed files

| File | Records |
| --- | --- |
| `diners.json` | 1 |
| `reservations.json` | 133 |
| `restaurants.json` | 60 |
<!-- api-test-results:end -->

## Connector operations covered

Search restaurants (`GET /v2/directory/restaurants`), check availability (`GET /v2/availability/{rid}`), create a reservation (`POST /v2/booking/{rid}/slot_locks` on an available time, then `POST /v2/booking/{rid}/reservations` with the lock's `reservation_token`), get a reservation and cancel it (`GET` and `DELETE /v2/booking/{rid}/reservations/{confirmation_number}`). Nothing else is served.

## What is and is not OpenTable's

OpenTable publishes the routes of its partner platform (availability at `/v2/availability/{rid}`, slot locks and reservations under `/v2/booking/{rid}/`) but not its JSON schemas, its directory route, or its error body. The field names, the directory route and the `{status, code, message}` error body here are this service's own.

## Availability

- Each restaurant releases a number of tables per seating area (`default`, `bar`, `outdoor`, `high_top`) and table size to online booking. A party is seated at a table that fits it with at most two empty chairs and keeps it for its turn time (90 minutes up to 2 guests, 105 up to 4, 120 up to 6, 150 above). Every confirmed reservation and live slot lock holds one table.
- Availability lists the bookable times from `backward_minutes` before to `forward_minutes` after `start_date_time` (defaults 30 and 150, at most 240), each with the seating areas still open and the `slot_hash` a slot lock needs. `require_attributes` narrows the areas.
- A party larger than the restaurant's online limit is `400 PARTY_SIZE_NOT_SUPPORTED`; a slot taken in the meantime is `409 SLOT_UNAVAILABLE`. A slot lock lasts 10 minutes and books one reservation.
- A diner cannot hold two confirmed reservations within the longer of their turn times (`409 DINER_HAS_CONFLICTING_RESERVATION`). Only a `Confirmed` reservation can be cancelled.

## Seed data

- Connected diner `acct-dana-whitfield` (Dana Whitfield, Chicago)
- 60 restaurants: 30 in Chicago, 15 in New York, 15 in San Francisco; fictional names and addresses
- 133 reservations: Dana's 13 (completed, one no-show, one cancelled, and six upcoming, including Copper Fern on October 20 and Marrow & Vine on October 30) and 120 by other diners that fill six popular rooms around 7pm on October 16, 17, 23 and 30
- 1 OAuth client `opentable-connector-app`: every scope granted; a token requested without `scope` carries every read scope but not `reservations.write`
