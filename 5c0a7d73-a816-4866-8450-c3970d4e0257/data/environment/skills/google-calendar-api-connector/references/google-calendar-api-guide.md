# Google Calendar API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$GOOGLE_CALENDAR_API_URL`.** Auth headers are mocked (any token is accepted) and responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `GOOGLE_CALENDAR_API_URL` | Base URL for all requests |

## Calendar

```bash
curl -s "$GOOGLE_CALENDAR_API_URL/calendar/v3/users/me/calendarList"
curl -s "$GOOGLE_CALENDAR_API_URL/calendar/v3/calendars/<calendar_id>"
curl -s "$GOOGLE_CALENDAR_API_URL/calendar/v3/calendars/<calendar_id>/events"
curl -s "$GOOGLE_CALENDAR_API_URL/calendar/v3/calendars/<calendar_id>/events/<event_id>"
curl -s -X POST "$GOOGLE_CALENDAR_API_URL/calendar/v3/calendars/primary/events" -H 'Content-Type: application/json' \
  -d '{"summary": "Shim rollout review", "start": {"dateTime": "2026-05-21T15:00:00-07:00", "timeZone": "America/Los_Angeles"}, "end": {"dateTime": "2026-05-21T15:30:00-07:00", "timeZone": "America/Los_Angeles"}, "attendees": [{"email": "jonas@orbit-labs.com"}, {"email": "helena@orbit-labs.com", "optional": true}]}'
curl -s -X PATCH "$GOOGLE_CALENDAR_API_URL/calendar/v3/calendars/<calendar_id>/events/<event_id>" -H 'Content-Type: application/json' \
  -d '{"location": "Room 4B", "attendees": [{"email": "jonas@orbit-labs.com"}, {"email": "rohit@orbit-labs.com"}]}'
curl -s -X DELETE "$GOOGLE_CALENDAR_API_URL/calendar/v3/calendars/<calendar_id>/events/<event_id>"
curl -s -X POST "$GOOGLE_CALENDAR_API_URL/calendar/v3/freeBusy" -H 'Content-Type: application/json' \
  -d '{"timeMin": "2026-05-21T00:00:00Z", "timeMax": "2026-05-22T00:00:00Z", "items": [{"id": "primary"}]}'
```

## Creating and changing events

- `POST /calendar/v3/calendars/{calendar_id}/events` takes `summary`, `start` and `end` (all required;
  `start` and `end` are each `{"dateTime": ..., "timeZone": ...}`, or `{"date": "YYYY-MM-DD"}` for an
  all-day event), and optionally `description`, `location`, `attendees`, `recurrence`, `visibility`,
  `creator` and `organizer`. Any other field is a `422`. `calendar_id` may be `primary`.
- `attendees` is a list of objects, one per guest: `{"email": ...}`, optionally with `displayName`,
  `optional` and `responseStatus`. A list of plain address strings is a `422`.
- `PATCH /calendar/v3/calendars/{calendar_id}/events/{event_id}` takes any of the same fields, plus
  `status`. An `attendees` list there replaces the event's guests, so send the whole list.
- `POST /calendar/v3/freeBusy` takes `timeMin`, `timeMax` and `items`, a list of `{"id": <calendar id>}`.
