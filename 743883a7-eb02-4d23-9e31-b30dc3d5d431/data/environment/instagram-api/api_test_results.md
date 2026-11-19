<!-- api-test-results:begin -->
# Instagram Graph API (Mock) - Test Results

GENERATED SECTION. DO NOT HAND-EDIT. `python3 script/gen_api_test_results.py --only instagram-api` writes everything between the api-test-results markers by sending the requests below to the service in-process; the text after the end marker is kept as written.

Base URL: `http://localhost:8102` (docker-compose: `http://instagram-api:8102`)

## Authentication

Every operation needs `Authorization: Bearer <token>` from `POST /oauth/token` with client credentials. The connected client `ig-connector-app` (account `acct-maya-okafor`) is granted `instagram_basic`, `instagram_content_publish`, `instagram_manage_insights`, `instagram_manage_comments`, `instagram_saved_media`, `instagram_relationships`; a token requested without `scope` carries `instagram_basic`. A request without a live token answers `401 invalid_token`, and a live token without the route's scope answers `403 insufficient_scope`.

## Endpoints

Each row is one request the generator sent. **Status** is the answer to the request as shown, sent with a token carrying every granted scope. **No token** is the same request with no `Authorization` header, and **Scope removed** the same request with a token carrying every granted scope except the route's own. The shared `/audit` and `/admin` planes every mock serves are described in `environment/API_DOCUMENTATION.md` and not listed.

| Method | Path | Scope | Request sent | Status | No token | Scope removed |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/oauth/token` | client credentials | `/oauth/token (form body)` | 200 | - | - |
| GET | `/health` | none | `/health` | 200 | - | - |
| GET | `/oauth/tokeninfo` | any live token | `/oauth/tokeninfo` | 200 | 401 | - |
| GET | `/v21.0/me/accounts` | `instagram_basic` | `/v21.0/me/accounts` | 200 | 401 | 403 |
| GET | `/v21.0/{ig_user_id}` | `instagram_basic` | `/v21.0/17841400000000101` | 200 | 401 | 403 |
| GET | `/v21.0/{ig_user_id}/media` | `instagram_basic` | `/v21.0/17841400000000101/media?limit=5` | 200 | 401 | 403 |
| POST | `/v21.0/{ig_user_id}/media` | `instagram_content_publish` | `/v21.0/17841400000000101/media (JSON body)` | 201 | 401 | 403 |
| POST | `/v21.0/{ig_user_id}/media` | `instagram_content_publish` | `/v21.0/17841400000000101/media (JSON body)` | 201 | 401 | 403 |
| POST | `/v21.0/{ig_user_id}/media_publish` | `instagram_content_publish` | `/v21.0/17841400000000101/media_publish (JSON body)` | 201 | 401 | 403 |
| GET | `/v21.0/{ig_user_id}/insights` | `instagram_manage_insights` | `/v21.0/17841400000000101/insights?metric=reach,follower_count&period=week` | 200 | 401 | 403 |
| GET | `/v21.0/{ig_user_id}/saved_media` | `instagram_saved_media` | `/v21.0/17841400000000101/saved_media` | 200 | 401 | 403 |
| GET | `/v21.0/{media_id}/comments` | `instagram_manage_comments` | `/v21.0/18050100000000001/comments` | 200 | 401 | 403 |
| GET | `/v21.0/{ig_user_id}/followers` | `instagram_relationships` | `/v21.0/17841400000000101/followers` | 200 | 401 | 403 |
| GET | `/v21.0/{ig_user_id}/following` | `instagram_relationships` | `/v21.0/17841400000000101/following` | 200 | 401 | 403 |

## Seed files

| File | Records |
| --- | --- |
| `accounts.json` | 2 |
| `comments.json` | 85 |
| `followers.json` | 70 |
| `following.json` | 40 |
| `insights.json` | 56 |
| `media.json` | 27 |
| `saved_media.json` | 11 |
<!-- api-test-results:end -->

## Connector operations covered

`.accounts`, `.profile`, `.posts`, `.post-feed` and `.post-story` (one container flow, `media_type` `IMAGE`/`VIDEO` or `STORIES`), `.account-insights`, `.saved-posts`, `.fetch-post-comments`, `.followers`, `.following`. Nothing else is served.

## Seed data

- 2 professional accounts linked to connected account `acct-maya-okafor` (business `saltmarsh.ceramics`, creator `mayamakes`)
- 27 media items: 24 feed and reels posts, 3 stories (stories never appear in `/media` or `media_count`)
- 85 comments with owner replies, 70 followers, 40 followed accounts, 11 saved posts
- 28 days of daily insights per account (2026-09-03 to 2026-09-30); `follower_count` is derived from follower dates
- 1 OAuth client `ig-connector-app`: every scope granted; a token requested without `scope` carries only `instagram_basic`
