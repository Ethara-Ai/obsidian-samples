# Gmail API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$GMAIL_API_URL`.** Auth headers are mocked (any token is accepted) and responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `GMAIL_API_URL` | Base URL for all requests |

## Gmail

```bash
curl -s "$GMAIL_API_URL/gmail/v1/users/me/profile"
curl -s "$GMAIL_API_URL/gmail/v1/users/me/labels"
curl -s "$GMAIL_API_URL/gmail/v1/users/me/labels/<label_id>"
curl -s -X POST "$GMAIL_API_URL/gmail/v1/users/me/labels" -H 'Content-Type: application/json' -d '{"name": "Follow-up"}'
curl -s "$GMAIL_API_URL/gmail/v1/users/me/messages"
curl -s "$GMAIL_API_URL/gmail/v1/users/me/messages/<message_id>"
curl -s -X POST "$GMAIL_API_URL/gmail/v1/users/me/messages/send" -H 'Content-Type: application/json' \
  -d '{"to": "jonas@orbit-labs.com", "subject": "Dual-write shim", "body": "Can we ship the shim on Thursday?"}'
curl -s -X POST "$GMAIL_API_URL/gmail/v1/users/me/messages/<message_id>/modify" -H 'Content-Type: application/json' -d '{"addLabelIds": ["STARRED"], "removeLabelIds": ["UNREAD"]}'
curl -s -X POST "$GMAIL_API_URL/gmail/v1/users/me/messages/<message_id>/trash" -H 'Content-Type: application/json' -d '{}'
curl -s -X DELETE "$GMAIL_API_URL/gmail/v1/users/me/messages/<message_id>"
curl -s "$GMAIL_API_URL/gmail/v1/users/me/threads"
curl -s "$GMAIL_API_URL/gmail/v1/users/me/threads/<thread_id>"
curl -s "$GMAIL_API_URL/gmail/v1/users/me/drafts"
curl -s "$GMAIL_API_URL/gmail/v1/users/me/drafts/<draft_id>"
curl -s -X POST "$GMAIL_API_URL/gmail/v1/users/me/drafts" -H 'Content-Type: application/json' \
  -d '{"to": "helena@orbit-labs.com", "subject": "Rollout notes", "body": "Draft of the rollout notes for review."}'
curl -s -X PUT "$GMAIL_API_URL/gmail/v1/users/me/drafts/<draft_id>" -H 'Content-Type: application/json' \
  -d '{"to": "helena@orbit-labs.com", "subject": "Rollout notes", "body": "Draft of the rollout notes for review."}'
curl -s -X POST "$GMAIL_API_URL/gmail/v1/users/me/drafts/<draft_id>/send" -H 'Content-Type: application/json' -d '{}'
curl -s -X DELETE "$GMAIL_API_URL/gmail/v1/users/me/drafts/<draft_id>"
```

## Sending mail (`POST /gmail/v1/users/me/messages/send`)

What a message may carry, which is less than Gmail takes:

- The body is JSON with `to`, `subject` and `body` (all required), and optionally `cc`, `threadId` (the
  thread to reply in) and `fromAddress` (the account's own address by default). Any other field is a `422`.
- `to` is a single address, as a string. A list of addresses is a `422`; to reach several people, send
  one message per address.
- Attachments are not supported: there is no field for them, and a message carrying `attachments` (or a
  `raw` MIME message) is a `422`.
- `POST /gmail/v1/users/me/drafts` and `PUT /gmail/v1/users/me/drafts/{draft_id}` take the same fields
  except `fromAddress`; `POST /gmail/v1/users/me/drafts/{draft_id}/send` sends a draft and takes no body.
