<!-- api-test-results:begin -->
# Printify API (Mock) - Test Results

GENERATED SECTION. DO NOT HAND-EDIT. `python3 script/gen_api_test_results.py --only printify-api` writes everything between the api-test-results markers by sending the requests below to the service in-process; the text after the end marker is kept as written.

Base URL: `http://localhost:8126` (docker-compose: `http://printify-api:8126`)

## Authentication

Every operation needs `Authorization: Bearer <token>` from `POST /oauth/token` with client credentials. The connected client `printify-connector-app` (account `acct-maya-okafor`) is granted `shops.read`, `products.read`, `products.write`, `orders.read`; a token requested without `scope` carries `shops.read`, `products.read`, `orders.read`. A request without a live token answers `401 invalid_token`, and a live token without the route's scope answers `403 insufficient_scope`.

## Endpoints

Each row is one request the generator sent. **Status** is the answer to the request as shown, sent with a token carrying every granted scope. **No token** is the same request with no `Authorization` header, and **Scope removed** the same request with a token carrying every granted scope except the route's own. The shared `/audit` and `/admin` planes every mock serves are described in `environment/API_DOCUMENTATION.md` and not listed.

| Method | Path | Scope | Request sent | Status | No token | Scope removed |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/oauth/token` | client credentials | `/oauth/token (form body)` | 200 | - | - |
| GET | `/health` | none | `/health` | 200 | - | - |
| GET | `/oauth/tokeninfo` | any live token | `/oauth/tokeninfo` | 200 | 401 | - |
| GET | `/v1/shops.json` | `shops.read` | `/v1/shops.json` | 200 | 401 | 403 |
| GET | `/v1/shops/{shop_id}/products.json` | `products.read` | `/v1/shops/<Etsy shop id>/products.json?page=1&limit=20` | 200 | 401 | 403 |
| GET | `/v1/shops/{shop_id}/products/{product_id}.json` | `products.read` | `/v1/shops/<Etsy shop id>/products/<Fog Line Tote id>.json` | 200 | 401 | 403 |
| POST | `/v1/shops/{shop_id}/products.json` | `products.write` | `/v1/shops/<Etsy shop id>/products.json (JSON body)` | 200 | 401 | 403 |
| POST | `/v1/shops/{shop_id}/products/{product_id}/publish.json` | `products.write` | `/v1/shops/<Etsy shop id>/products/<new product id>/publish.json (JSON body)` | 200 | 401 | 403 |
| GET | `/v1/shops/{shop_id}/orders.json` | `orders.read` | `/v1/shops/<Etsy shop id>/orders.json?status=in-production&limit=5` | 200 | 401 | 403 |
| GET | `/v1/shops/{shop_id}/orders.json` | `orders.read` | `/v1/shops/<Etsy shop id>/orders.json?sku=<SKU from an order>&page=1` | 200 | 401 | 403 |
| GET | `/v1/shops/{shop_id}/orders/{order_id}.json` | `orders.read` | `/v1/shops/<Etsy shop id>/orders/<order id from the list>.json` | 200 | 401 | 403 |

## Seed files

| File | Records |
| --- | --- |
| `blueprints.json` | 8 |
| `catalog_variants.json` | 69 |
| `orders.json` | 96 |
| `print_providers.json` | 5 |
| `products.json` | 27 |
| `shops.json` | 2 |
| `uploads.json` | 21 |
<!-- api-test-results:end -->

## Connector operations covered

List shops (`GET /v1/shops.json`), list a shop's products (`GET /v1/shops/{shop_id}/products.json`), get a product (`GET /v1/shops/{shop_id}/products/{product_id}.json`), create a product from a catalog blueprint (`POST /v1/shops/{shop_id}/products.json`), publish a product (`POST /v1/shops/{shop_id}/products/{product_id}/publish.json`), list orders (`GET /v1/shops/{shop_id}/orders.json`), and get an order (`GET /v1/shops/{shop_id}/orders/{order_id}.json`). Nothing else is served.

## Mock simplifications

- Errors use Printify's body (`{"status": "error", "code", "message", "errors": {"reason", "code"}}`): `404` with code 8203 for a shop, product or order the connected account does not own, and `400` with code 8150 for a bad value, an unknown body field, or a query parameter the operation does not take. The codes and wording are approximations of Printify's.
- Lists use Printify's page object (`current_page`, `data`, `last_page`, `next_page_url`, `total`, ...). Products come newest first, `page` and `limit` (1 to 50, default 10) page them. Orders come newest first; `status` (Printify's order statuses) and `sku` (a line item's SKU) filter, and `page` and `limit` (1 to 10, default 10) page them.
- A new product needs `title`, `description`, `blueprint_id`, `print_provider_id`, `variants` (`id`, `price` in cents, optional `is_enabled`) and `print_areas` (`variant_ids` and `placeholders` with `position` and `images`). The blueprint, the provider, every variant, every print position and every image id are checked against the catalog and the account's uploads, and every enabled variant needs a print area. Catalog and upload routes are not served, so a new product reuses blueprint, provider, variant and image ids from an existing product or from the task.
- Publishing takes the seven sync flags Printify takes (`title`, `description`, `images`, `variants`, `tags`, `keyFeatures`, `shipping_template`) and answers `{}`. It completes at once: the product becomes `visible` and gets its sales channel `external` id and handle, with no waiting for the channel's callback.
- Prices, costs and totals are integers in cents, timestamps are `YYYY-MM-DD HH:MM:SS+00:00`. Products cannot be edited or deleted, and orders cannot be created, sent to production or canceled.

## Seed data

- Connected account `acct-maya-okafor`: Maya Okafor's Saltmarsh Ceramics merchandise, the Portland, Maine studio that instagram-api and threads-api also serve, in two shops: Saltmarsh Ceramics Merch on Etsy (8312447) and Saltmarsh Studio Shop on Shopify (8312490).
- A catalog of 8 blueprints (tees, hoodies, two mugs, a tote, posters, stickers, an apron), 5 print providers and 69 variants with costs, and 21 uploaded artworks drawn from the studio's glazes and sayings.
- 27 products (24 published with an external listing, 3 still drafts: Rockweed Sprig Tee on Etsy, Studio Apron and Kiln Gods Badge Mug on Shopify) and 96 orders from April to October 2026, most fulfilled with USPS or UPS shipments, the newest still pending, on hold, in production or with issues. Every customer is invented, with a 555-01xx phone number and a made-up street.
- 1 OAuth client `printify-connector-app`: `shops.read`, `products.read`, `products.write` and `orders.read` granted; a token requested without `scope` carries the three read scopes.
