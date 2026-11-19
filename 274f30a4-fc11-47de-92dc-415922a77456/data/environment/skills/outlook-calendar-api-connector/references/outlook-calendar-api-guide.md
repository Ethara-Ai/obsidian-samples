# Outlook Calendar API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$OUTLOOK_CALENDAR_API_URL`.** Every operation needs `Authorization: Bearer $TOKEN`, where `$TOKEN` comes from `POST /oauth/token` and carries only the scopes it was issued with (see SKILL.md, Authentication). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `OUTLOOK_CALENDAR_API_URL` | Base URL for all requests |
| `OUTLOOK_CALENDAR_CLIENT_ID` | OAuth client id of the connected account |
| `OUTLOOK_CALENDAR_CLIENT_SECRET` | OAuth client secret of the connected account |

## Token

```bash
TOKEN=$(curl -s -X POST "$OUTLOOK_CALENDAR_API_URL/oauth/token" -d grant_type=client_credentials -d client_id="$OUTLOOK_CALENDAR_CLIENT_ID" -d client_secret="$OUTLOOK_CALENDAR_CLIENT_SECRET" -d scope="<space-separated scopes>" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$OUTLOOK_CALENDAR_API_URL/oauth/tokeninfo" -H "Authorization: Bearer $TOKEN"
```

## V1.0

```bash
curl -s "$OUTLOOK_CALENDAR_API_URL/v1.0/me/calendars" -H "Authorization: Bearer $TOKEN"
curl -s "$OUTLOOK_CALENDAR_API_URL/v1.0/me/events" -H "Authorization: Bearer $TOKEN"
curl -s "$OUTLOOK_CALENDAR_API_URL/v1.0/me/calendars/<calendar_id>/events" -H "Authorization: Bearer $TOKEN"
curl -s "$OUTLOOK_CALENDAR_API_URL/v1.0/me/calendarView" -H "Authorization: Bearer $TOKEN"
curl -s "$OUTLOOK_CALENDAR_API_URL/v1.0/me/calendars/<calendar_id>/calendarView" -H "Authorization: Bearer $TOKEN"
curl -s "$OUTLOOK_CALENDAR_API_URL/v1.0/me/events/<event_id>" -H "Authorization: Bearer $TOKEN"
curl -s -X POST "$OUTLOOK_CALENDAR_API_URL/v1.0/me/events" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s -X POST "$OUTLOOK_CALENDAR_API_URL/v1.0/me/calendars/<calendar_id>/events" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s -X PATCH "$OUTLOOK_CALENDAR_API_URL/v1.0/me/events/<event_id>" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s -X DELETE "$OUTLOOK_CALENDAR_API_URL/v1.0/me/events/<event_id>" -H "Authorization: Bearer $TOKEN"
curl -s -X POST "$OUTLOOK_CALENDAR_API_URL/v1.0/me/calendar/getSchedule" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
```
