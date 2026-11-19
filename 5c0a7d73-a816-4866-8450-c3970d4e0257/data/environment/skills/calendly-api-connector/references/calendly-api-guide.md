# Calendly API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$CALENDLY_API_URL`.** Every operation needs `Authorization: Bearer $TOKEN`, where `$TOKEN` comes from `POST /oauth/token` and carries only the scopes it was issued with (see SKILL.md, Authentication). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `CALENDLY_API_URL` | Base URL for all requests |
| `CALENDLY_CLIENT_ID` | OAuth client id of the connected account |
| `CALENDLY_CLIENT_SECRET` | OAuth client secret of the connected account |

## Token

```bash
TOKEN=$(curl -s -X POST "$CALENDLY_API_URL/oauth/token" -d grant_type=client_credentials -d client_id="$CALENDLY_CLIENT_ID" -d client_secret="$CALENDLY_CLIENT_SECRET" -d scope="<space-separated scopes>" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$CALENDLY_API_URL/oauth/tokeninfo" -H "Authorization: Bearer $TOKEN"
```

## Event_Types

```bash
curl -s "$CALENDLY_API_URL/event_types" -H "Authorization: Bearer $TOKEN"
```

## Scheduled_Events

```bash
curl -s "$CALENDLY_API_URL/scheduled_events" -H "Authorization: Bearer $TOKEN"
curl -s "$CALENDLY_API_URL/scheduled_events/<uuid>" -H "Authorization: Bearer $TOKEN"
curl -s "$CALENDLY_API_URL/scheduled_events/<uuid>/invitees" -H "Authorization: Bearer $TOKEN"
curl -s -X POST "$CALENDLY_API_URL/scheduled_events/<uuid>/cancellation" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
```

## Users

```bash
curl -s "$CALENDLY_API_URL/users/me" -H "Authorization: Bearer $TOKEN"
```
