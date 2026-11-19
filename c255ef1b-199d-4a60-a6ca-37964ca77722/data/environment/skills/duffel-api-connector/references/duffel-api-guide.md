# Duffel API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$DUFFEL_API_URL`.** Every operation needs `Authorization: Bearer $TOKEN`, where `$TOKEN` comes from `POST /oauth/token` and carries only the scopes it was issued with (see SKILL.md, Authentication). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `DUFFEL_API_URL` | Base URL for all requests |
| `DUFFEL_CLIENT_ID` | OAuth client id of the connected account |
| `DUFFEL_CLIENT_SECRET` | OAuth client secret of the connected account |

## Token

```bash
TOKEN=$(curl -s -X POST "$DUFFEL_API_URL/oauth/token" -d grant_type=client_credentials -d client_id="$DUFFEL_CLIENT_ID" -d client_secret="$DUFFEL_CLIENT_SECRET" -d scope="<space-separated scopes>" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$DUFFEL_API_URL/oauth/tokeninfo" -H "Authorization: Bearer $TOKEN"
```

## Air

```bash
curl -s -X POST "$DUFFEL_API_URL/air/offer_requests" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s "$DUFFEL_API_URL/air/seat_maps" -H "Authorization: Bearer $TOKEN"
curl -s "$DUFFEL_API_URL/air/offers/<offer_id>" -H "Authorization: Bearer $TOKEN"
curl -s -X POST "$DUFFEL_API_URL/air/orders" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s "$DUFFEL_API_URL/air/orders/<order_id>" -H "Authorization: Bearer $TOKEN"
curl -s -X POST "$DUFFEL_API_URL/air/order_cancellations" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s -X POST "$DUFFEL_API_URL/air/order_cancellations/<cancellation_id>/actions/confirm" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
```

## Stays

```bash
curl -s -X POST "$DUFFEL_API_URL/stays/search" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s -X POST "$DUFFEL_API_URL/stays/search_results/<search_result_id>/actions/fetch_all_rates" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
```
