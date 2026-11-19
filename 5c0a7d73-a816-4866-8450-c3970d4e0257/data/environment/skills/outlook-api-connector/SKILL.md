---
name: outlook-api-connector
description: >
  Outlook API (Mock) mock HTTP API. Base URL is provided via the
  `OUTLOOK_API_URL` environment variable. 5 endpoint(s) across GET, POST.
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# Outlook API (Mock)

Mock HTTP API. **All requests go to the base URL in `$OUTLOOK_API_URL`.** Auth headers
are mocked (any token is accepted). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `OUTLOOK_API_URL` | Base URL for all requests (e.g. `http://outlook-api:8087`) |

## Endpoints

| Method | Path |
|--------|------|
| GET | `/v1.0/me/messages` |
| GET | `/v1.0/me/messages/{message_id}` |
| POST | `/v1.0/me/sendMail` |
| GET | `/v1.0/me/events` |
| GET | `/v1.0/me/contacts` |

## Usage

```bash
# GET example
curl -s "$OUTLOOK_API_URL/v1.0/me/messages"
```

## Sending mail (`POST /v1.0/me/sendMail`)

What this mock keeps of a message, which is less than Microsoft Graph keeps:

- It delivers to the first `toRecipients` entry only. Any further entries are dropped, and the
  answer is still `202`.
- The stored and returned body is the first 255 characters of `body.content`.
- `ccRecipients`, `bccRecipients` and `saveToSentItems` are not accepted (`422`). The body takes
  `message.subject`, `message.body` (`contentType`, `content`) and `message.toRecipients`, nothing else.
- To reach several people, send one message per recipient, and keep each body within 255 characters.

```bash
curl -s -X POST "$OUTLOOK_API_URL/v1.0/me/sendMail" -H 'Content-Type: application/json' \
  -d '{"message": {"subject": "Thursday review", "body": {"contentType": "Text", "content": "Can we move the review to 3pm?"}, "toRecipients": [{"emailAddress": {"address": "jordan.lee@contoso.com"}}]}}'
```
