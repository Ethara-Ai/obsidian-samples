<!-- api-test-results:begin -->
# Outlook Calendar API (Mock) - Test Results

GENERATED SECTION. DO NOT HAND-EDIT. `python3 script/gen_api_test_results.py --only outlook-calendar-api` writes everything between the api-test-results markers by sending the requests below to the service in-process; the text after the end marker is kept as written.

Base URL: `http://localhost:8120` (docker-compose: `http://outlook-calendar-api:8120`)

## Authentication

Every operation needs `Authorization: Bearer <token>` from `POST /oauth/token` with client credentials. The connected client `ocal-connector-app` (account `acct-alex-carter`) is granted `Calendars.Read`, `Calendars.ReadWrite`; a token requested without `scope` carries `Calendars.Read`. A request without a live token answers `401 invalid_token`, and a live token without the route's scope answers `403 insufficient_scope`.

## Endpoints

Each row is one request the generator sent. **Status** is the answer to the request as shown, sent with a token carrying every granted scope. **No token** is the same request with no `Authorization` header, and **Scope removed** the same request with a token carrying every granted scope except the route's own. The shared `/audit` and `/admin` planes every mock serves are described in `environment/API_DOCUMENTATION.md` and not listed.

| Method | Path | Scope | Request sent | Status | No token | Scope removed |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/oauth/token` | client credentials | `/oauth/token (form body)` | 200 | - | - |
| GET | `/health` | none | `/health` | 200 | - | - |
| GET | `/oauth/tokeninfo` | any live token | `/oauth/tokeninfo` | 200 | 401 | - |
| GET | `/v1.0/me/calendars` | `Calendars.Read` | `/v1.0/me/calendars?$select=name,canEdit` | 200 | 401 | 403 |
| GET | `/v1.0/me/calendarView` | `Calendars.Read` | `/v1.0/me/calendarView?startDateTime=2026-10-05T00:00:00-07:00&endDateTime=2026-10-10T00:00:00-07:00&$select=subject,start,end,type&$top=50` | 200 | 401 | 403 |
| GET | `/v1.0/me/calendars/{calendar_id}/calendarView` | `Calendars.Read` | `/v1.0/me/calendars/<Platform Team calendar id>/calendarView?startDateTime=2026-10-05T00:00:00-07:00&endDateTime=2026-10-10T00:00:00-07:00` | 200 | 401 | 403 |
| GET | `/v1.0/me/events` | `Calendars.Read` | `/v1.0/me/events?$filter=categories/any(c:c eq 'Customer')&$orderby=start/dateTime desc&$select=subject,start&$top=5` | 200 | 401 | 403 |
| GET | `/v1.0/me/calendars/{calendar_id}/events` | `Calendars.Read` | `/v1.0/me/calendars/<Platform Team calendar id>/events?$filter=isAllDay eq true and startswith(subject,'Release')&$select=subject,start` | 200 | 401 | 403 |
| GET | `/v1.0/me/events/{event_id}` | `Calendars.Read` | `/v1.0/me/events/<occurrence id>?$select=subject,start,seriesMasterId` | 200 | 401 | 403 |
| POST | `/v1.0/me/calendar/getSchedule` | `Calendars.Read` | `/v1.0/me/calendar/getSchedule (JSON body)` | 200 | 401 | 403 |
| POST | `/v1.0/me/events` | `Calendars.ReadWrite` | `/v1.0/me/events (JSON body)` | 201 | 401 | 403 |
| PATCH | `/v1.0/me/events/{event_id}` | `Calendars.ReadWrite` | `/v1.0/me/events/<new event id> (JSON body)` | 200 | 401 | 403 |
| DELETE | `/v1.0/me/events/{event_id}` | `Calendars.ReadWrite` | `/v1.0/me/events/<new event id>` | 204 | 401 | 403 |
| POST | `/v1.0/me/calendars/{calendar_id}/events` | `Calendars.ReadWrite` | `/v1.0/me/calendars/<Platform Team calendar id>/events (JSON body)` | 201 | 401 | 403 |

## Seed files

| File | Records |
| --- | --- |
| `calendars.json` | 4 |
| `events.json` | 159 |
| `people.json` | 11 |
| `schedule_items.json` | 282 |
<!-- api-test-results:end -->

## Connector operations covered

List calendars (`GET /v1.0/me/calendars`), list the events of the default calendar or of a named one (`GET /v1.0/me/events`, `GET /v1.0/me/calendars/{calendar_id}/events`), a calendar view of a date range with every series expanded into its occurrences (`GET /v1.0/me/calendarView`, `GET /v1.0/me/calendars/{calendar_id}/calendarView`), get an event or one occurrence (`GET /v1.0/me/events/{event_id}`), create an event in the default calendar or a named one (`POST /v1.0/me/events`, `POST /v1.0/me/calendars/{calendar_id}/events`), update an event (`PATCH /v1.0/me/events/{event_id}`), delete an event (`DELETE /v1.0/me/events/{event_id}`), and free/busy for a list of people (`POST /v1.0/me/calendar/getSchedule`). Nothing else is served. outlook-api is a separate service and still serves the same mailbox's mail, its own short event list and contacts.

## Mock simplifications

- Time zones are UTC and the US zones (Pacific, Mountain, Arizona, Central, Eastern), by Windows or IANA name, under the US daylight saving rule; any other zone, in a body or in `Prefer: outlook.timezone`, is a 400 `TimeZoneNotSupportedException`. Event times come back in UTC unless `Prefer: outlook.timezone` names a zone; other `Prefer` values are ignored, as RFC 7240 lets a server do. An event keeps one original time zone, its start's, and a `dateTime` ending in `Z` is taken only with `timeZone` UTC.
- A series is daily or weekly (interval, days of the week, first day of the week) and ends on a date, after a count, or never; a monthly or yearly pattern is a 400. A series has no exceptions: an occurrence, whose id is `<seriesMasterId>_<yyyymmdd>` for its UTC start date, can be read, and is changed or deleted only through its series master.
- `/me/events` and `/me/calendarView` read the default calendar, as on Graph; the other calendars are read by id. `United States holidays` and `Birthdays` are read-only, and a write to them is a 403 `ErrorAccessDenied`.
- `$filter` takes `eq`, `ne`, `gt`, `ge`, `lt`, `le`, `and`, `or`, `not`, parentheses, `startswith`, `endswith`, `contains` and `categories/any(c:c eq '...')` over the properties the server names; `$orderby` takes subject, start/dateTime, end/dateTime, createdDateTime, lastModifiedDateTime, importance, showAs and organizer/emailAddress/name. Filtering and ordering on a time compare UTC times, whatever zone the answer is given in. `$select`, `$top` (default 10, at most 1000) and `$skip` work, and `@odata.nextLink` points back at this service. `$expand`, `$count` and `$search` are not served. An unknown `$` option is a 400, as on Graph; an unknown plain query parameter is a 400 too, where Graph would ignore it, so a misspelt option cannot pass for one that worked.
- A location is a display name, a location type and a street address, with no rooms, coordinates or unique ids. Attendees keep the response they already gave when the list is sent again (attendee `status` is read-only, as on Graph). There are no attachments, extensions, meeting responses, cancel or forward actions, and no invitations go out. Enum values ignore case. A property the event type does not have is a 400 `RequestBodyRead`, nested ones included, and errors use Graph's envelope (`{"error": {"code", "message", "innerError"}}`).
- Free/busy: the owner's schedule comes from the default calendar, leaving out cancelled and `free` items. A colleague's comes from the default calendar's meetings they organize or were invited to (busy once accepted, tentative until they answer, left out once declined), so a meeting created here shows on its invitees' schedules, plus their own seeded commitments from September 28 to November 6, 2026. An address outside the directory gets an entry with an `ErrorMailRecipientNotFound` error. The window is at most 62 days, the interval 5 to 1440 minutes (default 30), and a request names at most 100 schedules.

## Seed data

- Connected account `acct-alex-carter` (Alex Carter, alex.carter@contoso.com, Contoso, Pacific time), the mailbox outlook-api serves; Alex joined in early May 2026, as outlook-api's mail shows
- 4 calendars: `Calendar` (the default, 117 events), `Platform Team` (24: the on-call rotation, release dates and the deploy window), `United States holidays` (12, read-only) and `Birthdays` (6, read-only)
- 159 events from May to December 2026, as of October 2: outlook-api's six May events unchanged (ids, UTC times, organizers and attendees), 11 series (the weekday standup, three 1:1s, biweekly sprint planning, the leads meeting in Eastern time, a five-day release go/no-go, a metrics review that ended September 28, a six-session onboarding course, focus time and the deploy window), a cancelled meeting still on the calendar, two private appointments, three vacations, and 12 meetings Alex has answered tentatively or not at all
- 11 people in the directory, with working hours in five US time zones, and 282 of their own commitments for free/busy
- 1 OAuth client `ocal-connector-app`: both scopes granted; a token requested without `scope` carries only `Calendars.Read`
