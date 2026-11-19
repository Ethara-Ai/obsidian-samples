<!-- api-test-results:begin -->
# Facebook Graph API (Mock) - Test Results

GENERATED SECTION. DO NOT HAND-EDIT. `python3 script/gen_api_test_results.py --only facebook-api` writes everything between the api-test-results markers by sending the requests below to the service in-process; the text after the end marker is kept as written.

Base URL: `http://localhost:8103` (docker-compose: `http://facebook-api:8103`)

## Authentication

Every operation needs `Authorization: Bearer <token>` from `POST /oauth/token` with client credentials. The connected client `fb-connector-app` (account `acct-dana-whitfield`) is granted `public_profile`, `user_posts`, `publish_actions`, `user_feed`, `groups_access_member_info`, `user_saved`, `marketplace_listings`; a token requested without `scope` carries `public_profile`. A request without a live token answers `401 invalid_token`, and a live token without the route's scope answers `403 insufficient_scope`.

## Endpoints

Each row is one request the generator sent. **Status** is the answer to the request as shown, sent with a token carrying every granted scope. **No token** is the same request with no `Authorization` header, and **Scope removed** the same request with a token carrying every granted scope except the route's own. The shared `/audit` and `/admin` planes every mock serves are described in `environment/API_DOCUMENTATION.md` and not listed.

| Method | Path | Scope | Request sent | Status | No token | Scope removed |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/oauth/token` | client credentials | `/oauth/token (form body)` | 200 | - | - |
| GET | `/health` | none | `/health` | 200 | - | - |
| GET | `/oauth/tokeninfo` | any live token | `/oauth/tokeninfo` | 200 | 401 | - |
| GET | `/v21.0/me` | `public_profile` | `/v21.0/me` | 200 | 401 | 403 |
| GET | `/v21.0/me/feed` | `user_posts` | `/v21.0/me/feed?limit=5` | 200 | 401 | 403 |
| POST | `/v21.0/me/feed` | `publish_actions` | `/v21.0/me/feed (JSON body)` | 200 | 401 | 403 |
| GET | `/v21.0/me/home` | `user_feed` | `/v21.0/me/home?limit=10` | 200 | 401 | 403 |
| GET | `/v21.0/me/groups` | `groups_access_member_info` | `/v21.0/me/groups` | 200 | 401 | 403 |
| GET | `/v21.0/{group_id}/feed` | `groups_access_member_info` | `/v21.0/280100000000001/feed?limit=10` | 200 | 401 | 403 |
| GET | `/v21.0/me/saved` | `user_saved` | `/v21.0/me/saved` | 200 | 401 | 403 |
| GET | `/v21.0/marketplace_listings` | `marketplace_listings` | `/v21.0/marketplace_listings?q=lamp&location=Austin&max_price=100` | 200 | 401 | 403 |
| GET | `/v21.0/marketplace_listings/{listing_id}` | `marketplace_listings` | `/v21.0/marketplace_listings/3500100000000001` | 200 | 401 | 403 |
| GET | `/v21.0/posts` | `user_posts` | `/v21.0/posts?link=https://www.facebook.com/100090000000001/posts/12218930551286975` | 200 | 401 | 403 |
| GET | `/v21.0/{owner_id}_{post_suffix}` | `user_posts` | `/v21.0/100090000000001_12218930551286975` | 200 | 401 | 403 |
| GET | `/v21.0/{user_id}` | `public_profile` | `/v21.0/100090000000004` | 200 | 401 | 403 |

## Seed files

| File | Records |
| --- | --- |
| `group_members.json` | 29 |
| `groups.json` | 6 |
| `listings.json` | 50 |
| `posts.json` | 128 |
| `saved_items.json` | 12 |
| `users.json` | 21 |
<!-- api-test-results:end -->

## Connector operations covered

`.me`, `.timeline` (`GET /me/feed`), `.post` (create with `POST /me/feed`, retrieve by id or by permalink link), `.feed` (`GET /me/home`), `.groups` (membership list and group content), `.saved`, `.marketplace` (search and retrieve), `.profile`. Nothing else is served.

## Seed data

- 1 connected user (Dana Whitfield, Austin home-goods reseller, account `acct-dana-whitfield`) and 20 other profiles: 14 friends and 6 pages
- 128 posts: 25 own timeline posts, 60 news-feed posts from friends and pages, 43 group posts (40 in the 5 groups the user belongs to, 3 in a group she is not in; those return 404)
- 6 groups, 5 of them with the connected user as member (29 membership rows)
- 12 saved items: 5 posts, 3 links, 4 marketplace listings, in 4 collections
- 50 marketplace listings across 8 categories and 6 Texas cities, with prices, conditions, seller ids and creation times
- Dates run 2026-06-01 to 2026-09-30
- 1 OAuth client `fb-connector-app`: every scope granted; a token requested without `scope` carries only `public_profile`

## Notes

- `location` on marketplace search matches the listing's city name (case-insensitive); a distance radius is not modelled.
- `fields` projection is supported on `/me`, `/{user_id}` and `/{post_id}`; unknown names answer `400`.
- Created posts default to privacy `ALL_FRIENDS`; the new post is returned by `GET /me/feed`, `GET /{post_id}` and `GET /posts?link=`.
