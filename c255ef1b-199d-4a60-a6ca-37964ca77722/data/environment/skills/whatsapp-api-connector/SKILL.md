---
name: whatsapp-api-connector
description: >
  WhatsApp Cloud API (Mock) mock HTTP API. Base URL is provided via the
  `WHATSAPP_API_URL` environment variable. 9 endpoint(s) across GET, POST.
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# WhatsApp Cloud API (Mock)

Mock HTTP API. **All requests go to the base URL in `$WHATSAPP_API_URL`.** Auth headers
are mocked (any token is accepted). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `WHATSAPP_API_URL` | Base URL for all requests (e.g. `http://whatsapp-api:8015`) |

## Endpoints

| Method | Path |
|--------|------|
| GET | `/v17.0/business` |
| GET | `/v17.0/contacts` |
| GET | `/v17.0/contacts/{wa_id}` |
| GET | `/v17.0/message_templates` |
| GET | `/v17.0/message_templates/{name}` |
| GET | `/v17.0/conversations` |
| GET | `/v17.0/messages` |
| POST | `/v17.0/messages` |
| POST | `/v17.0/messages/status` |

## Usage

```bash
# GET example
curl -s "$WHATSAPP_API_URL/v17.0/business"
```

## Paging

- `GET /v17.0/messages` returns at most 20 by default (`limit`, up to 100); there is no next page, so ask for a larger `limit`.
