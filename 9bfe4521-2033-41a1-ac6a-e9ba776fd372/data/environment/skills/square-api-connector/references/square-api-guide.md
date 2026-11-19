# Square API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$SQUARE_API_URL`.** Auth headers are mocked (any token is accepted) and responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `SQUARE_API_URL` | Base URL for all requests |

## Catalog

```bash
curl -s "$SQUARE_API_URL/v2/catalog/list"
```

## Customers

```bash
curl -s "$SQUARE_API_URL/v2/customers"
curl -s "$SQUARE_API_URL/v2/customers/<customer_id>"
curl -s -X POST "$SQUARE_API_URL/v2/customers" -H 'Content-Type: application/json' -d '{}'
```

## Inventory

```bash
curl -s "$SQUARE_API_URL/v2/inventory/<catalog_object_id>"
```

## Merchants

```bash
curl -s "$SQUARE_API_URL/v2/merchants/me"
```

## Orders

```bash
curl -s -X POST "$SQUARE_API_URL/v2/orders" -H 'Content-Type: application/json' -d '{}'
curl -s "$SQUARE_API_URL/v2/orders/<order_id>"
```

## Payments

```bash
curl -s "$SQUARE_API_URL/v2/payments"
curl -s "$SQUARE_API_URL/v2/payments/<payment_id>"
curl -s -X POST "$SQUARE_API_URL/v2/payments" -H 'Content-Type: application/json' -d '{}'
```

## Refunds

```bash
curl -s -X POST "$SQUARE_API_URL/v2/refunds" -H 'Content-Type: application/json' \
  -d '{"payment_id": "<payment_id>", "amount_money": {"amount": 100, "currency": "USD"}, "reason": "Damaged item", "idempotency_key": "<unique key>"}'
curl -s "$SQUARE_API_URL/v2/refunds"
curl -s "$SQUARE_API_URL/v2/refunds/<refund_id>"
```

- Amounts are integer cents. Without `amount_money` the refund is everything still left on the payment.
- A payment's refunds can never add up to more than its amount: a refund that would is a `400` whose
  `error` says how much is left.
- `idempotency_key`: send a new unique key with each refund. Sending the same key again returns the refund it
  already made (`200`) instead of refunding twice; the same key with a different payment or amount is a `400`.
- Once refunded, `GET /v2/payments/<payment_id>` shows `refunded_money` (the total refunded) and `refund_ids`.
- `GET /v2/refunds` lists refunds oldest first; it takes `location_id`, `status` (`COMPLETED`) and `limit` (default and
  maximum 100).
