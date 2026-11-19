# Phone API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$PHONE_API_URL`.** Every operation needs `Authorization: Bearer $TOKEN`, where `$TOKEN` comes from `POST /oauth/token` and carries only the scopes it was issued with (see SKILL.md, Authentication). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `PHONE_API_URL` | Base URL for all requests |
| `PHONE_CLIENT_ID` | OAuth client id of the connected account |
| `PHONE_CLIENT_SECRET` | OAuth client secret of the connected account |

## Token

```bash
TOKEN=$(curl -s -X POST "$PHONE_API_URL/oauth/token" -d grant_type=client_credentials -d client_id="$PHONE_CLIENT_ID" -d client_secret="$PHONE_CLIENT_SECRET" -d scope="<space-separated scopes>" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$PHONE_API_URL/oauth/tokeninfo" -H "Authorization: Bearer $TOKEN"
```

## Calls

```bash
curl -s "$PHONE_API_URL/v1/calls" -H "Authorization: Bearer $TOKEN"
curl -s -X POST "$PHONE_API_URL/v1/calls" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
```

## Conversations

```bash
curl -s "$PHONE_API_URL/v1/conversations" -H "Authorization: Bearer $TOKEN"
curl -s "$PHONE_API_URL/v1/conversations/<conversation_id>/messages" -H "Authorization: Bearer $TOKEN"
```

## Messages

```bash
curl -s -X POST "$PHONE_API_URL/v1/messages" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
```
