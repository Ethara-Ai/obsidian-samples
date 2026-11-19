<!-- api-test-results:begin -->
# Calendly API (Mock) - Test Results

GENERATED SECTION. DO NOT HAND-EDIT. `python3 script/gen_api_test_results.py --only calendly-api` writes everything between the api-test-results markers by sending the requests below to the service in-process; the text after the end marker is kept as written.

Base URL: `http://localhost:8123` (docker-compose: `http://calendly-api:8123`)

## Authentication

Every operation needs `Authorization: Bearer <token>` from `POST /oauth/token` with client credentials. The connected client `calendly-connector-app` (account `acct-dana-whitfield`) is granted `users:read`, `event_types:read`, `scheduled_events:read`, `scheduled_events:write`; a token requested without `scope` carries `users:read`, `event_types:read`, `scheduled_events:read`. A request without a live token answers `401 invalid_token`, and a live token without the route's scope answers `403 insufficient_scope`.

## Endpoints

Each row is one request the generator sent. **Status** is the answer to the request as shown, sent with a token carrying every granted scope. **No token** is the same request with no `Authorization` header, and **Scope removed** the same request with a token carrying every granted scope except the route's own. The shared `/audit` and `/admin` planes every mock serves are described in `environment/API_DOCUMENTATION.md` and not listed.

| Method | Path | Scope | Request sent | Status | No token | Scope removed |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/oauth/token` | client credentials | `/oauth/token (form body)` | 200 | - | - |
| GET | `/health` | none | `/health` | 200 | - | - |
| GET | `/oauth/tokeninfo` | any live token | `/oauth/tokeninfo` | 200 | 401 | - |
| GET | `/users/me` | `users:read` | `/users/me` | 200 | 401 | 403 |
| GET | `/event_types` | `event_types:read` | `/event_types?user=<your user URI>&active=true` | 200 | 401 | 403 |
| GET | `/scheduled_events` | `scheduled_events:read` | `/scheduled_events?user=<your user URI>&status=active&min_start_time=2026-10-05T00:00:00Z&max_start_time=2026-11-01T00:00:00Z&sort=start_time:asc` | 200 | 401 | 403 |
| GET | `/scheduled_events/{uuid}` | `scheduled_events:read` | `/scheduled_events/<Greenline Dental site visit uuid>` | 200 | 401 | 403 |
| GET | `/scheduled_events/{uuid}/invitees` | `scheduled_events:read` | `/scheduled_events/<Greenline Dental site visit uuid>/invitees?status=active` | 200 | 401 | 403 |
| POST | `/scheduled_events/{uuid}/cancellation` | `scheduled_events:write` | `/scheduled_events/<Greenline Dental site visit uuid>/cancellation (JSON body)` | 201 | 401 | 403 |

## Seed files

| File | Records |
| --- | --- |
| `accounts.json` | 1 |
| `event_types.json` | 9 |
| `invitees.json` | 80 |
| `organizations.json` | 1 |
| `scheduled_events.json` | 75 |
| `users.json` | 3 |
<!-- api-test-results:end -->

## Connector operations covered

Get the current user (`GET /users/me`), list event types (`GET /event_types`), list scheduled events filtered by status, a start-time window and an invitee's email (`GET /scheduled_events`), get one scheduled event (`GET /scheduled_events/{uuid}`), list an event's invitees (`GET /scheduled_events/{uuid}/invitees`), and cancel a scheduled event (`POST /scheduled_events/{uuid}/cancellation`). Nothing else is served.

## Mock simplifications

- Scopes are this mock's own: `users:read`, `event_types:read`, `scheduled_events:read` and `scheduled_events:write`, one per operation, so read access is not permission to cancel. Calendly's own OAuth scope names were not available to check against.
- Lists need `user` or `organization`, as on Calendly. `user` must be a member of the connected user's organization, and only the organization's owner or an admin lists another member's event types and events; Dana is the owner. URIs are matched on their trailing id, so a URI with this service's host works too.
- `GET /event_types` filters by `active` and sorts by name (the default), position, created_at or updated_at. `GET /scheduled_events` filters by `status`, `invitee_email` (ignoring case), `min_start_time` (inclusive) and `max_start_time` (exclusive), and sorts by start_time, earliest first by default. `GET /scheduled_events/{uuid}/invitees` filters by `status` and `email` and sorts by created_at. `count` runs from 1 to 100 (default 20), `page_token` is opaque, and `next_page` points back at this service. Any other query parameter, `group` or `admin_managed` for example, is a 400.
- Event types are solo, plus one group type with a 20-invitee limit; there are no collective or round-robin types, and no availability, scheduling links, routing forms, webhooks or no-show marking.
- Cancellation is the one write. It cancels the event and its active invitees, records the reason with `canceler_type: host`, and answers 201 with the cancellation; canceling an event twice is a 403 `Permission Denied`. The date is not checked: Calendly is expected to refuse to cancel an event that has already ended, but this mock lets any event be canceled, so the seed stays usable whatever day a task runs.
- Errors use Calendly's body (`{"title", "message", "details"}`), and a body field the endpoint does not take is a 400 `Invalid Argument`.

## Seed data

- Connected account `acct-dana-whitfield`: Dana Whitfield, owner of the Lakeshore Design Studio organization, the account the studio's Google Drive, Docs, Sheets, Contacts, Forms, Slides and Tasks seeds serve; Marcus Oyelaran and Leah Novak are members
- 9 event types: Dana's Discovery call, Design consultation, Site visit, Press interview (secret), Portfolio review (inactive) and Fall open house (a group event type); Marcus's Partnership intro and Proposal walkthrough; Leah's Studio coordinator interview
- 75 scheduled events from November 2025 to November 2026, as of October 2, 2026, with 80 invitees who answered the event type's questions: 17 events fall after October 2, and 3 of those are canceled (one by Dana because of the River North install week, two by the invitees, with their reasons); two earlier bookings were canceled too, a portfolio review by the applicant and a partnership intro by Marcus; the Fall open house on November 12 has six invitees, one of whom canceled
- Dana's discovery calls follow the google-forms-api Client Intake Questionnaire, one to two weeks after each submission and with the same budget range, and most of those clients go on to a design consultation, a site visit and Marcus's proposal walkthrough; Leah's interviews on October 8 and 9 are with applicants from the Studio Coordinator Application form, with the start dates they gave there; the Greenline Dental site visit on October 8 comes before the October 15 contract date in google-tasks-api, and Marcus walks Midway Credit Union and Lumen Coworking through their proposals on October 20 and 27
- 1 OAuth client `calendly-connector-app`: all four scopes granted; a token requested without `scope` carries the three read scopes
