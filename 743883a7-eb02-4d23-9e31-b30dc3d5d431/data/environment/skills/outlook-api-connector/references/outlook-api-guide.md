# Outlook API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$OUTLOOK_API_URL`.** Auth headers are mocked (any token is accepted) and responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `OUTLOOK_API_URL` | Base URL for all requests |

## V1.0

```bash
curl -s "$OUTLOOK_API_URL/v1.0/me/messages"
curl -s "$OUTLOOK_API_URL/v1.0/me/messages/<message_id>"
curl -s -X POST "$OUTLOOK_API_URL/v1.0/me/sendMail" -H 'Content-Type: application/json' \
  -d '{"message": {"subject": "Thursday review", "body": {"contentType": "Text", "content": "Can we move the review to 3pm?"}, "toRecipients": [{"emailAddress": {"address": "jordan.lee@contoso.com"}}]}}'
curl -s "$OUTLOOK_API_URL/v1.0/me/events"
curl -s "$OUTLOOK_API_URL/v1.0/me/contacts"
```

## Sending mail (`POST /v1.0/me/sendMail`)

What this mock keeps of a message, which is less than Microsoft Graph keeps:

- It delivers to the first `toRecipients` entry only. Any further entries are dropped, and the
  answer is still `202`.
- The stored and returned body is the first 255 characters of `body.content`.
- `ccRecipients`, `bccRecipients` and `saveToSentItems` are not accepted (`422`). The body takes
  `message.subject`, `message.body` (`contentType`, `content`) and `message.toRecipients`, nothing else.
- To reach several people, send one message per recipient, and keep each body within 255 characters.
