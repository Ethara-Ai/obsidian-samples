<!-- api-test-results:begin -->
# Uber Rides API (Mock) - Test Results

GENERATED SECTION. DO NOT HAND-EDIT. `python3 script/gen_api_test_results.py --only uber-api` writes everything between the api-test-results markers by sending the requests below to the service in-process; the text after the end marker is kept as written.

Base URL: `http://localhost:8115` (docker-compose: `http://uber-api:8115`)

## Authentication

Every operation needs `Authorization: Bearer <token>` from `POST /oauth/token` with client credentials. The connected client `uber-connector-app` (account `acct-dana-whitfield`) is granted `ride_request.estimate`, `all_trips`, `history`, `request`; a token requested without `scope` carries `ride_request.estimate`, `all_trips`, `history`. A request without a live token answers `401 invalid_token`, and a live token without the route's scope answers `403 insufficient_scope`.

## Endpoints

Each row is one request the generator sent. **Status** is the answer to the request as shown, sent with a token carrying every granted scope. **No token** is the same request with no `Authorization` header, and **Scope removed** the same request with a token carrying every granted scope except the route's own. The shared `/audit` and `/admin` planes every mock serves are described in `environment/API_DOCUMENTATION.md` and not listed.

| Method | Path | Scope | Request sent | Status | No token | Scope removed |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/oauth/token` | client credentials | `/oauth/token (form body)` | 200 | - | - |
| GET | `/health` | none | `/health` | 200 | - | - |
| GET | `/oauth/tokeninfo` | any live token | `/oauth/tokeninfo` | 200 | 401 | - |
| GET | `/v1.2/products` | `ride_request.estimate` | `/v1.2/products?latitude=41.9147&longitude=-87.6826` | 200 | 401 | 403 |
| GET | `/v1.2/estimates/price` | `ride_request.estimate` | `/v1.2/estimates/price?start_latitude=41.9147&start_longitude=-87.6826&end_latitude=41.8893&end_longitude=-87.6309` | 200 | 401 | 403 |
| GET | `/v1.2/estimates/time` | `ride_request.estimate` | `/v1.2/estimates/time?start_latitude=41.9147&start_longitude=-87.6826` | 200 | 401 | 403 |
| GET | `/v1.2/estimates/time` | `ride_request.estimate` | `/v1.2/estimates/time?start_latitude=41.9147&start_longitude=-87.6826&product_id=<UberX product id>` | 200 | 401 | 403 |
| POST | `/v1.2/requests` | `request` | `/v1.2/requests (JSON body)` | 202 | 401 | 403 |
| GET | `/v1.2/requests/{request_id}` | `all_trips` | `/v1.2/requests/<request id>` | 200 | 401 | 403 |
| DELETE | `/v1.2/requests/{request_id}` | `request` | `/v1.2/requests/<request id>` | 204 | 401 | 403 |
| GET | `/v1.2/history` | `history` | `/v1.2/history?offset=0&limit=10` | 200 | 401 | 403 |

## Seed files

| File | Records |
| --- | --- |
| `cities.json` | 4 |
| `drivers.json` | 26 |
| `products.json` | 20 |
| `riders.json` | 1 |
| `rides.json` | 161 |
<!-- api-test-results:end -->

## Connector operations covered

Products at a location (`GET /v1.2/products`), price estimate (`GET /v1.2/estimates/price`), time estimate (`GET /v1.2/estimates/time`), request a ride (`POST /v1.2/requests`), ride status (`GET /v1.2/requests/{request_id}`), cancel a ride (`DELETE /v1.2/requests/{request_id}`), and ride history (`GET /v1.2/history`). `current` works as a request id for status and cancel. Nothing else is served.

## Mock simplifications

- Products and estimates come from the city a point falls in (Chicago, New York, San Francisco, Austin); a point outside every city has no products. Distance is the great-circle distance times 1.25, duration follows the city's average speed, and a fare is the product's base, per-mile and per-minute rates, at least its minimum, times its surge multiplier, plus a $3.05 booking fee.
- A surged product (UberXL in Chicago, Uber Black in New York, UberX in San Francisco) first answers `409 surge` with a `surge_confirmation_id`, valid for two minutes; resending the request with it books the ride.
- A ride is matched with a driver when it is requested, so it starts `accepted`; it does not progress on its own (the admin plane moves it). One active ride at a time (`409 current_trip_exists`). Cancelling more than two minutes after the request charges the product's cancellation fee.
- History lists ended rides newest first (`offset`, `limit` up to 50) and each item carries its fare, which the real API serves from a separate receipt endpoint. There are no shared products, places or payment methods.

## Seed data

- Connected rider `acct-dana-whitfield` (Dana Whitfield, Chicago)
- 4 cities, 20 products, 26 drivers and 161 past rides from January to October 2, 2026: studio, client and airport trips in Chicago, and trips in Austin (March), San Francisco (May) and New York (September)
- Rides line up with Dana's OpenTable reservations (for example Copper Fern on July 14 and Gramercy Oak on September 10) and the Brightwell site visits
- 1 OAuth client `uber-connector-app`: every scope granted; a token requested without `scope` carries every read scope but not `request`
