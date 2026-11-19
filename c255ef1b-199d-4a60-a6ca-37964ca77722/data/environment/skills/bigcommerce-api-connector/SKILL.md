---
name: bigcommerce-api-connector
description: >
  BigCommerce API (Mock) mock HTTP API. Base URL is provided via the
  `BIGCOMMERCE_API_URL` environment variable. 6 endpoint(s) across GET, POST.
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# BigCommerce API (Mock)

Mock HTTP API. **All requests go to the base URL in `$BIGCOMMERCE_API_URL`.** Auth headers
are mocked (any token is accepted). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `BIGCOMMERCE_API_URL` | Base URL for all requests (e.g. `http://bigcommerce-api:8084`) |

## Endpoints

| Method | Path |
|--------|------|
| GET | `/v3/catalog/products` |
| GET | `/v3/catalog/products/{product_id}` |
| GET | `/v2/orders` |
| GET | `/v2/orders/{order_id}` |
| POST | `/v2/orders` |
| GET | `/v3/customers` |

## Usage

```bash
# GET example
curl -s "$BIGCOMMERCE_API_URL/v3/catalog/products"
```

## Paging

- `GET /v3/catalog/products` returns 50 per page by default (`limit`); while `meta.pagination.current_page` is below `meta.pagination.total_pages`, ask for `page` + 1.
