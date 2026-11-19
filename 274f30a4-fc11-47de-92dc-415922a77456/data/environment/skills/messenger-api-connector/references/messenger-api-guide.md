# Facebook Messenger (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$MESSENGER_API_URL`.** Every operation needs `Authorization: Bearer $TOKEN`, where `$TOKEN` comes from `POST /oauth/token` and carries only the scopes it was issued with (see SKILL.md, Authentication). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `MESSENGER_API_URL` | Base URL for all requests |
| `MESSENGER_CLIENT_ID` | OAuth client id of the connected account |
| `MESSENGER_CLIENT_SECRET` | OAuth client secret of the connected account |

## Token

```bash
TOKEN=$(curl -s -X POST "$MESSENGER_API_URL/oauth/token" -d grant_type=client_credentials -d client_id="$MESSENGER_CLIENT_ID" -d client_secret="$MESSENGER_CLIENT_SECRET" -d scope="<space-separated scopes>" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$MESSENGER_API_URL/oauth/tokeninfo" -H "Authorization: Bearer $TOKEN"
```

## V21.0

```bash
curl -s "$MESSENGER_API_URL/v21.0/me/conversations" -H "Authorization: Bearer $TOKEN"
curl -s "$MESSENGER_API_URL/v21.0/me/conversations/<thread_id>" -H "Authorization: Bearer $TOKEN"
curl -s "$MESSENGER_API_URL/v21.0/me/conversations/<thread_id>/messages" -H "Authorization: Bearer $TOKEN"
curl -s "$MESSENGER_API_URL/v21.0/me/unread" -H "Authorization: Bearer $TOKEN"
curl -s "$MESSENGER_API_URL/v21.0/me/sync" -H "Authorization: Bearer $TOKEN"
curl -s "$MESSENGER_API_URL/v21.0/me/search" -H "Authorization: Bearer $TOKEN"
curl -s "$MESSENGER_API_URL/v21.0/me/contacts" -H "Authorization: Bearer $TOKEN"
curl -s -X POST "$MESSENGER_API_URL/v21.0/me/messages" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s -X DELETE "$MESSENGER_API_URL/v21.0/me/messages/<message_id>" -H "Authorization: Bearer $TOKEN"
```
