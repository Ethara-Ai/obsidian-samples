---
name: google-calendar-api-connector
description: >
  Google Calendar API (Mock) mock HTTP API. Base URL is provided via the
  `GOOGLE_CALENDAR_API_URL` environment variable. 8 endpoint(s) across DELETE, GET, PATCH, POST.
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# Google Calendar API (Mock)

Mock HTTP API. **All requests go to the base URL in `$GOOGLE_CALENDAR_API_URL`.** Auth headers
are mocked (any token is accepted). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `GOOGLE_CALENDAR_API_URL` | Base URL for all requests (e.g. `http://google-calendar-api:8016`) |

## Endpoints

| Method | Path |
|--------|------|
| GET | `/calendar/v3/users/me/calendarList` |
| GET | `/calendar/v3/calendars/{calendar_id}` |
| GET | `/calendar/v3/calendars/{calendar_id}/events` |
| GET | `/calendar/v3/calendars/{calendar_id}/events/{event_id}` |
| POST | `/calendar/v3/calendars/{calendar_id}/events` |
| PATCH | `/calendar/v3/calendars/{calendar_id}/events/{event_id}` |
| DELETE | `/calendar/v3/calendars/{calendar_id}/events/{event_id}` |
| POST | `/calendar/v3/freeBusy` |

## Usage

```bash
# GET example
curl -s "$GOOGLE_CALENDAR_API_URL/calendar/v3/users/me/calendarList"
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

```bash
curl -s -X POST "$GOOGLE_CALENDAR_API_URL/calendar/v3/calendars/primary/events" -H 'Content-Type: application/json' \
  -d '{"summary": "Shim rollout review", "start": {"dateTime": "2026-05-21T15:00:00-07:00", "timeZone": "America/Los_Angeles"}, "end": {"dateTime": "2026-05-21T15:30:00-07:00", "timeZone": "America/Los_Angeles"}, "attendees": [{"email": "jonas@orbit-labs.com"}, {"email": "helena@orbit-labs.com", "optional": true}]}'
```

## Paging

- `GET /calendar/v3/calendars/{calendarId}/events` returns 25 per page by default (`maxResults`, up to 250); when an answer carries `nextPageToken`, send it back as `pageToken` for the next page.
