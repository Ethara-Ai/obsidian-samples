---
name: square-api-connector
description: >
  Square API (Mock) mock HTTP API. Base URL is provided via the
  `SQUARE_API_URL` environment variable. 14 endpoint(s) across GET, POST.
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# Square API (Mock)

Mock HTTP API. **All requests go to the base URL in `$SQUARE_API_URL`.** Auth headers
are mocked (any token is accepted). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `SQUARE_API_URL` | Base URL for all requests (e.g. `http://square-api:8041`) |

## Endpoints

| Method | Path |
|--------|------|
| GET | `/v2/merchants/me` |
| GET | `/v2/payments` |
| GET | `/v2/payments/{payment_id}` |
| POST | `/v2/payments` |
| POST | `/v2/refunds` |
| GET | `/v2/refunds` |
| GET | `/v2/refunds/{refund_id}` |
| GET | `/v2/customers` |
| GET | `/v2/customers/{customer_id}` |
| POST | `/v2/customers` |
| GET | `/v2/catalog/list` |
| POST | `/v2/orders` |
| GET | `/v2/orders/{order_id}` |
| GET | `/v2/inventory/{catalog_object_id}` |

## Usage

```bash
# GET example
curl -s "$SQUARE_API_URL/v2/merchants/me"
```

## Paging

- `GET /v2/payments` returns at most 50 by default (`limit`, up to 100); there is no next page, so ask for a larger `limit`.
