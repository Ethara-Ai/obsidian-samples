# Printify API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$PRINTIFY_API_URL`.** Every operation needs `Authorization: Bearer $TOKEN`, where `$TOKEN` comes from `POST /oauth/token` and carries only the scopes it was issued with (see SKILL.md, Authentication). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `PRINTIFY_API_URL` | Base URL for all requests |
| `PRINTIFY_CLIENT_ID` | OAuth client id of the connected account |
| `PRINTIFY_CLIENT_SECRET` | OAuth client secret of the connected account |

## Token

```bash
TOKEN=$(curl -s -X POST "$PRINTIFY_API_URL/oauth/token" -d grant_type=client_credentials -d client_id="$PRINTIFY_CLIENT_ID" -d client_secret="$PRINTIFY_CLIENT_SECRET" -d scope="<space-separated scopes>" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$PRINTIFY_API_URL/oauth/tokeninfo" -H "Authorization: Bearer $TOKEN"
```

## Shops

```bash
curl -s "$PRINTIFY_API_URL/v1/shops/<shop_id>/products.json" -H "Authorization: Bearer $TOKEN"
curl -s "$PRINTIFY_API_URL/v1/shops/<shop_id>/products/<product_id>.json" -H "Authorization: Bearer $TOKEN"
curl -s -X POST "$PRINTIFY_API_URL/v1/shops/<shop_id>/products.json" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s -X POST "$PRINTIFY_API_URL/v1/shops/<shop_id>/products/<product_id>/publish.json" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s "$PRINTIFY_API_URL/v1/shops/<shop_id>/orders.json" -H "Authorization: Bearer $TOKEN"
curl -s "$PRINTIFY_API_URL/v1/shops/<shop_id>/orders/<order_id>.json" -H "Authorization: Bearer $TOKEN"
```

## Shops.Json

```bash
curl -s "$PRINTIFY_API_URL/v1/shops.json" -H "Authorization: Bearer $TOKEN"
```
