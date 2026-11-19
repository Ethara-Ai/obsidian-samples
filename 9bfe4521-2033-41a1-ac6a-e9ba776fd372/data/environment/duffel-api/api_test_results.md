<!-- api-test-results:begin -->
# Duffel API (Mock) - Test Results

GENERATED SECTION. DO NOT HAND-EDIT. `python3 script/gen_api_test_results.py --only duffel-api` writes everything between the api-test-results markers by sending the requests below to the service in-process; the text after the end marker is kept as written.

Base URL: `http://localhost:8105` (docker-compose: `http://duffel-api:8105`)

## Authentication

Every operation needs `Authorization: Bearer <token>` from `POST /oauth/token` with client credentials. The connected client `duffel-connector-app` (account `acct-aurora-travel`) is granted `air.offers.read`, `air.orders.read`, `air.orders.write`, `air.orders.cancel`, `stays.read`; a token requested without `scope` carries `air.offers.read`. A request without a live token answers `401 invalid_token`, and a live token without the route's scope answers `403 insufficient_scope`.

## Endpoints

Each row is one request the generator sent. **Status** is the answer to the request as shown, sent with a token carrying every granted scope. **No token** is the same request with no `Authorization` header, and **Scope removed** the same request with a token carrying every granted scope except the route's own. The shared `/audit` and `/admin` planes every mock serves are described in `environment/API_DOCUMENTATION.md` and not listed.

| Method | Path | Scope | Request sent | Status | No token | Scope removed |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/oauth/token` | client credentials | `/oauth/token (form body)` | 200 | - | - |
| GET | `/health` | none | `/health` | 200 | - | - |
| GET | `/oauth/tokeninfo` | any live token | `/oauth/tokeninfo` | 200 | 401 | - |
| POST | `/air/offer_requests` | `air.offers.read` | `/air/offer_requests (JSON body)` | 201 | 401 | 403 |
| GET | `/air/seat_maps` | `air.offers.read` | `/air/seat_maps?offer_id=<offer id>` | 200 | 401 | 403 |
| GET | `/air/offers/{offer_id}` | `air.offers.read` | `/air/offers/<offer id>` | 200 | 401 | 403 |
| POST | `/air/orders` | `air.orders.write` | `/air/orders (JSON body)` | 201 | 401 | 403 |
| GET | `/air/orders/{order_id}` | `air.orders.read` | `/air/orders/<order id>` | 200 | 401 | 403 |
| POST | `/air/order_cancellations` | `air.orders.cancel` | `/air/order_cancellations (JSON body)` | 201 | 401 | 403 |
| POST | `/air/order_cancellations/{cancellation_id}/actions/confirm` | `air.orders.cancel` | `/air/order_cancellations/<cancellation id>/actions/confirm` | 200 | 401 | 403 |
| POST | `/stays/search` | `stays.read` | `/stays/search (JSON body)` | 200 | 401 | 403 |
| POST | `/stays/search_results/{search_result_id}/actions/fetch_all_rates` | `stays.read` | `/stays/search_results/<search result id>/actions/fetch_all_rates` | 200 | 401 | 403 |

## Seed files

| File | Records |
| --- | --- |
| `accommodations.json` | 30 |
| `aircraft.json` | 4 |
| `airlines.json` | 8 |
| `airports.json` | 12 |
| `blocked_inventory.json` | 4 |
| `rates.json` | 270 |
| `rooms.json` | 90 |
| `schedules.json` | 52 |
| `seat_layouts.json` | 11 |
<!-- api-test-results:end -->

## Connector operations covered

`.search` (`POST /air/offer_requests`), `.seat-options` (`GET /air/seat_maps`), `.validate-booking` (`GET /air/offers/{offer_id}`), `.book` (`POST /air/orders`), `.booking-status` (`GET /air/orders/{order_id}`), `.cancellation-quote` (`POST /air/order_cancellations`), `.cancel-booking` (`.../actions/confirm`), `.stays-search` (`POST /stays/search`), `.stays-fetch-rates` (`.../actions/fetch_all_rates`). Nothing else is served: no stays booking, no order changes.

## Behaviour notes

- Offers are generated deterministically from `schedules.json` (nonstop weekly flights valid 2026-10-01 to 2026-12-31). The same request returns the same flights and prices on any day; only ids and `expires_at` (30 minutes after creation) differ. Price = seeded base fare for the cabin x a weekday factor x a seasonal factor (Thanksgiving week and 15-31 December are dearer), per passenger type (child 75 %, infant without seat 10 %), plus tax by origin region.
- A multi-slice request combines flights of one airline in one cabin. Without `cabin_class` every cabin the flight sells is offered. A departure date outside the schedule window is a 400.
- Seat maps cover every cabin of the segment's aircraft. A seat with a fee carries one seat service per travelling passenger (`ase_<offer>_<segment>_<designator>_<passenger>`); free seats carry no service. Between 20 and 38 percent of the seats in a cabin (by cabin) are already taken, deterministically.
- `POST /air/orders` checks the offer exists and has not expired, that every passenger id of the offer appears exactly once, that `born_on` matches the passenger type, that the single `balance` payment equals the offer total plus the seat services, and that each seat is still free. A booked seat is unavailable to every later offer on that flight until the order is cancelled.
- Refund on a cancellation quote = offer total minus the `refund_before_departure` penalty for the whole party (0.00 when the fare is not refundable). Seat services are not refunded. A quote expires after 30 minutes; confirming it sets `confirmed_at`, turns the order `cancelled` and frees its seats.
- `offer_expired`, `offer_no_longer_available` (sold out or already booked), `seat_unavailable`, `payment_amount_mismatch`, `cancellation_already_confirmed`, `cancellation_expired` and `order_already_cancelled` are 422s. A recognised but unsupported request (several offers or payments, seat quantity other than 1, an unknown airport, a stay over 30 nights) is a 400.
- Every offer request, offer, order, cancellation and stay search belongs to the connected account that created it; another account's id answers 404.
- `fetch_all_rates` stamps `rates_fetched_at` on the stored search result and re-prices the stay from the seeded rates.
- Money is always a decimal string with 2 places; `passenger_identity_documents_required` is `false` on every offer because the booking passenger schema carries no identity documents.

## Seed data

- 12 airports (6 US, 6 Europe), 8 airlines (4 USD, 4 EUR) with per-cabin refund and change penalties
- 4 aircraft types (A320, 737-800, A330-300, 787-9) with 11 cabin layouts
- 52 weekly schedule rows (26 routes, both directions); 4 blocked-inventory rows that sell out a cabin on one date
- 30 accommodations in 6 cities (New York, Chicago, London, Paris, Madrid, Rome), 90 rooms, 270 rates (flexible, flexible with breakfast, non-refundable)
- 1 OAuth client `duffel-connector-app` for connected account `acct-aurora-travel` (a small travel agency's Duffel test account): every scope granted; a token requested without `scope` carries only `air.offers.read`
