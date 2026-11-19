---
name: duffel-api-connector
description: >
  Duffel API (Mock) mock HTTP API. Base URL is provided via the
  `DUFFEL_API_URL` environment variable. 11 endpoint(s) across GET, POST.
  Every operation needs an OAuth bearer token that carries the operation's scope.
---

# Duffel API (Mock)

Mock HTTP API. **All requests go to the base URL in `$DUFFEL_API_URL`.** Every operation needs a bearer token, and a token covers only the scopes it was issued with: a connected account is not permission for every action. Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `DUFFEL_API_URL` | Base URL for all requests (e.g. `http://duffel-api:8105`) |
| `DUFFEL_CLIENT_ID` | OAuth client id of the connected account, when the task provides it |
| `DUFFEL_CLIENT_SECRET` | OAuth client secret of the connected account, when the task provides it |

## Authentication

1. Exchange the client credentials for an access token: `POST /oauth/token` with `grant_type=client_credentials`, `client_id`, `client_secret`, and optionally `scope` (space-separated). Form-encoded and JSON bodies are both accepted.
2. Send `Authorization: Bearer <access_token>` on every operation.
3. `GET /oauth/tokeninfo` reports the presented token's scopes and expiry.

A token requested without `scope` carries only the default scopes (`air.offers.read`). Ask for any other scope explicitly. A `401 invalid_token` means the token is missing, expired, or revoked; get a new one. A `403 insufficient_scope` names the `required_scope`; request a token that carries it. The token endpoint answers `invalid_scope` when the account never granted a scope to this client. `grant_type=refresh_token` exchanges a refresh token for a new access token.

## Scopes

| Scope | Operations |
|-------|------------|
| `air.offers.read` | POST `/air/offer_requests`, GET `/air/seat_maps`, GET `/air/offers/{offer_id}` |
| `air.orders.cancel` | POST `/air/order_cancellations`, POST `/air/order_cancellations/{cancellation_id}/actions/confirm` |
| `air.orders.read` | GET `/air/orders/{order_id}` |
| `air.orders.write` | POST `/air/orders` |
| `stays.read` | POST `/stays/search`, POST `/stays/search_results/{search_result_id}/actions/fetch_all_rates` |

## Endpoints

| Method | Path |
|--------|------|
| POST | `/oauth/token` |
| GET | `/oauth/tokeninfo` |
| POST | `/air/offer_requests` |
| GET | `/air/seat_maps` |
| GET | `/air/offers/{offer_id}` |
| POST | `/air/orders` |
| GET | `/air/orders/{order_id}` |
| POST | `/air/order_cancellations` |
| POST | `/air/order_cancellations/{cancellation_id}/actions/confirm` |
| POST | `/stays/search` |
| POST | `/stays/search_results/{search_result_id}/actions/fetch_all_rates` |

## Usage

```bash
TOKEN=$(curl -s -X POST "$DUFFEL_API_URL/oauth/token" -d grant_type=client_credentials \
  -d client_id="$DUFFEL_CLIENT_ID" -d client_secret="$DUFFEL_CLIENT_SECRET" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s -X POST "$DUFFEL_API_URL/air/offer_requests" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"data": {"slices": [{"origin": "JFK", "destination": "LHR", "departure_date": "2026-11-10"}], "passengers": [{"type": "adult"}, {"age": 7}], "cabin_class": "premium_economy"}}'
```
