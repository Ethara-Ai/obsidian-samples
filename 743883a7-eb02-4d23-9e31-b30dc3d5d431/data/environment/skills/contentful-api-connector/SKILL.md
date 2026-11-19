---
name: contentful-api-connector
description: >
  Contentful API (Mock) mock HTTP API. Base URL is provided via the
  `CONTENTFUL_API_URL` environment variable. 10 endpoint(s) across DELETE, GET, POST, PUT.
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# Contentful API (Mock)

Mock HTTP API. **All requests go to the base URL in `$CONTENTFUL_API_URL`.** Auth headers
are mocked (any token is accepted). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `CONTENTFUL_API_URL` | Base URL for all requests (e.g. `http://contentful-api:8066`) |

## Endpoints

| Method | Path |
|--------|------|
| GET | `/spaces/{space_id}` |
| GET | `/spaces/{space_id}/environments/{env_id}/content_types` |
| GET | `/spaces/{space_id}/environments/{env_id}/content_types/{content_type_id}` |
| GET | `/spaces/{space_id}/environments/{env_id}/entries` |
| GET | `/spaces/{space_id}/environments/{env_id}/entries/{entry_id}` |
| POST | `/spaces/{space_id}/environments/{env_id}/entries` |
| PUT | `/spaces/{space_id}/environments/{env_id}/entries/{entry_id}` |
| DELETE | `/spaces/{space_id}/environments/{env_id}/entries/{entry_id}` |
| GET | `/spaces/{space_id}/environments/{env_id}/assets` |
| GET | `/spaces/{space_id}/environments/{env_id}/assets/{asset_id}` |

## Usage

```bash
# GET example
curl -s "$CONTENTFUL_API_URL/spaces/space-orbit-cms"
```

## Paging

- `GET /spaces/{space_id}/environments/{env_id}/entries` returns 100 per page by default (`limit`, up to 1000); for the next page send `skip` raised by `limit`, while `skip` + `limit` is below `total`.
