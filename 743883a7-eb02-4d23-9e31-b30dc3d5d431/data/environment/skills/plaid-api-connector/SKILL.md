---
name: plaid-api-connector
description: >
  Plaid API (Mock) mock HTTP API. Base URL is provided via the
  `PLAID_API_URL` environment variable. 5 endpoint(s) across POST.
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# Plaid API (Mock)

Mock HTTP API. **All requests go to the base URL in `$PLAID_API_URL`.** Auth headers
are mocked (any token is accepted). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `PLAID_API_URL` | Base URL for all requests (e.g. `http://plaid-api:8022`) |

## Endpoints

| Method | Path |
|--------|------|
| POST | `/accounts/get` |
| POST | `/accounts/balance/get` |
| POST | `/transactions/get` |
| POST | `/institutions/get_by_id` |
| POST | `/identity/get` |

## Usage

```bash
# POST example
curl -s -X POST "$PLAID_API_URL/accounts/get" -H 'Content-Type: application/json' -d '{}'
```

## Paging

- `POST /transactions/get` returns 100 per page by default (`options.count` in the body); for the next page send `options.offset` raised by `options.count`, while it is below `total_transactions`.
