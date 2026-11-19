---
name: outlook-calendar-api-connector
description: >
  Outlook Calendar API (Mock) mock HTTP API. Base URL is provided via the
  `OUTLOOK_CALENDAR_API_URL` environment variable. 13 endpoint(s) across DELETE, GET, PATCH, POST.
  Every operation needs an OAuth bearer token that carries the operation's scope.
---

# Outlook Calendar API (Mock)

Mock HTTP API. **All requests go to the base URL in `$OUTLOOK_CALENDAR_API_URL`.** Every operation needs a bearer token, and a token covers only the scopes it was issued with: a connected account is not permission for every action. Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `OUTLOOK_CALENDAR_API_URL` | Base URL for all requests (e.g. `http://outlook-calendar-api:8120`) |
| `OUTLOOK_CALENDAR_CLIENT_ID` | OAuth client id of the connected account, when the task provides it |
| `OUTLOOK_CALENDAR_CLIENT_SECRET` | OAuth client secret of the connected account, when the task provides it |

## Authentication

1. Exchange the client credentials for an access token: `POST /oauth/token` with `grant_type=client_credentials`, `client_id`, `client_secret`, and optionally `scope` (space-separated). Form-encoded and JSON bodies are both accepted.
2. Send `Authorization: Bearer <access_token>` on every operation.
3. `GET /oauth/tokeninfo` reports the presented token's scopes and expiry.

A token requested without `scope` carries only the default scopes (`Calendars.Read`). Ask for any other scope explicitly. A `401 invalid_token` means the token is missing, expired, or revoked; get a new one. A `403 insufficient_scope` names the `required_scope`; request a token that carries it. The token endpoint answers `invalid_scope` when the account never granted a scope to this client. `grant_type=refresh_token` exchanges a refresh token for a new access token.

## Scopes

| Scope | Operations |
|-------|------------|
| `Calendars.Read` | GET `/v1.0/me/calendars`, GET `/v1.0/me/events`, GET `/v1.0/me/calendars/{calendar_id}/events`, GET `/v1.0/me/calendarView`, GET `/v1.0/me/calendars/{calendar_id}/calendarView`, GET `/v1.0/me/events/{event_id}`, POST `/v1.0/me/calendar/getSchedule` |
| `Calendars.ReadWrite` | POST `/v1.0/me/events`, POST `/v1.0/me/calendars/{calendar_id}/events`, PATCH `/v1.0/me/events/{event_id}`, DELETE `/v1.0/me/events/{event_id}` |

## Endpoints

| Method | Path |
|--------|------|
| POST | `/oauth/token` |
| GET | `/oauth/tokeninfo` |
| GET | `/v1.0/me/calendars` |
| GET | `/v1.0/me/events` |
| GET | `/v1.0/me/calendars/{calendar_id}/events` |
| GET | `/v1.0/me/calendarView` |
| GET | `/v1.0/me/calendars/{calendar_id}/calendarView` |
| GET | `/v1.0/me/events/{event_id}` |
| POST | `/v1.0/me/events` |
| POST | `/v1.0/me/calendars/{calendar_id}/events` |
| PATCH | `/v1.0/me/events/{event_id}` |
| DELETE | `/v1.0/me/events/{event_id}` |
| POST | `/v1.0/me/calendar/getSchedule` |

## Usage

```bash
TOKEN=$(curl -s -X POST "$OUTLOOK_CALENDAR_API_URL/oauth/token" -d grant_type=client_credentials \
  -d client_id="$OUTLOOK_CALENDAR_CLIENT_ID" -d client_secret="$OUTLOOK_CALENDAR_CLIENT_SECRET" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$OUTLOOK_CALENDAR_API_URL/v1.0/me/calendars?%24select=name,canEdit" -H "Authorization: Bearer $TOKEN"
```

## Paging

- `GET /v1.0/me/events` returns 10 per page by default (`$top`, up to 1000); when an answer carries `@odata.nextLink`, request that URL for the next page.
