---
name: printify-api-connector
description: >
  Printify API (Mock) mock HTTP API. Base URL is provided via the
  `PRINTIFY_API_URL` environment variable. 9 endpoint(s) across GET, POST.
  Every operation needs an OAuth bearer token that carries the operation's scope.
---

# Printify API (Mock)

Mock HTTP API. **All requests go to the base URL in `$PRINTIFY_API_URL`.** Every operation needs a bearer token, and a token covers only the scopes it was issued with: a connected account is not permission for every action. Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `PRINTIFY_API_URL` | Base URL for all requests (e.g. `http://printify-api:8126`) |
| `PRINTIFY_CLIENT_ID` | OAuth client id of the connected account, when the task provides it |
| `PRINTIFY_CLIENT_SECRET` | OAuth client secret of the connected account, when the task provides it |

## Authentication

1. Exchange the client credentials for an access token: `POST /oauth/token` with `grant_type=client_credentials`, `client_id`, `client_secret`, and optionally `scope` (space-separated). Form-encoded and JSON bodies are both accepted.
2. Send `Authorization: Bearer <access_token>` on every operation.
3. `GET /oauth/tokeninfo` reports the presented token's scopes and expiry.

A token requested without `scope` carries only the default scopes (`shops.read products.read orders.read`). Ask for any other scope explicitly. A `401 invalid_token` means the token is missing, expired, or revoked; get a new one. A `403 insufficient_scope` names the `required_scope`; request a token that carries it. The token endpoint answers `invalid_scope` when the account never granted a scope to this client. `grant_type=refresh_token` exchanges a refresh token for a new access token.

## Scopes

| Scope | Operations |
|-------|------------|
| `orders.read` | GET `/v1/shops/{shop_id}/orders.json`, GET `/v1/shops/{shop_id}/orders/{order_id}.json` |
| `products.read` | GET `/v1/shops/{shop_id}/products.json`, GET `/v1/shops/{shop_id}/products/{product_id}.json` |
| `products.write` | POST `/v1/shops/{shop_id}/products.json`, POST `/v1/shops/{shop_id}/products/{product_id}/publish.json` |
| `shops.read` | GET `/v1/shops.json` |

## Endpoints

| Method | Path |
|--------|------|
| POST | `/oauth/token` |
| GET | `/oauth/tokeninfo` |
| GET | `/v1/shops.json` |
| GET | `/v1/shops/{shop_id}/products.json` |
| GET | `/v1/shops/{shop_id}/products/{product_id}.json` |
| POST | `/v1/shops/{shop_id}/products.json` |
| POST | `/v1/shops/{shop_id}/products/{product_id}/publish.json` |
| GET | `/v1/shops/{shop_id}/orders.json` |
| GET | `/v1/shops/{shop_id}/orders/{order_id}.json` |

## Usage

```bash
TOKEN=$(curl -s -X POST "$PRINTIFY_API_URL/oauth/token" -d grant_type=client_credentials \
  -d client_id="$PRINTIFY_CLIENT_ID" -d client_secret="$PRINTIFY_CLIENT_SECRET" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$PRINTIFY_API_URL/v1/shops.json" -H "Authorization: Bearer $TOKEN"
```

## Paging

- `GET /v1/shops/{shop_id}/products.json` returns 10 per page by default (`limit`, up to 50); while `current_page` is below `last_page`, ask for `page` + 1.
