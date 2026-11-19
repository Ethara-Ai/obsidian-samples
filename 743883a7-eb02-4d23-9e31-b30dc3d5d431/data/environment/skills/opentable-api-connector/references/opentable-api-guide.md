# OpenTable API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$OPENTABLE_API_URL`.** Every operation needs `Authorization: Bearer $TOKEN`, where `$TOKEN` comes from `POST /oauth/token` and carries only the scopes it was issued with (see SKILL.md, Authentication). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `OPENTABLE_API_URL` | Base URL for all requests |
| `OPENTABLE_CLIENT_ID` | OAuth client id of the connected account |
| `OPENTABLE_CLIENT_SECRET` | OAuth client secret of the connected account |

## Token

```bash
TOKEN=$(curl -s -X POST "$OPENTABLE_API_URL/oauth/token" -d grant_type=client_credentials -d client_id="$OPENTABLE_CLIENT_ID" -d client_secret="$OPENTABLE_CLIENT_SECRET" -d scope="<space-separated scopes>" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$OPENTABLE_API_URL/oauth/tokeninfo" -H "Authorization: Bearer $TOKEN"
```

## Availability

```bash
curl -s "$OPENTABLE_API_URL/v2/availability/<rid>" -H "Authorization: Bearer $TOKEN"
```

## Booking

```bash
curl -s -X POST "$OPENTABLE_API_URL/v2/booking/<rid>/slot_locks" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s -X POST "$OPENTABLE_API_URL/v2/booking/<rid>/reservations" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s "$OPENTABLE_API_URL/v2/booking/<rid>/reservations/<confirmation_number>" -H "Authorization: Bearer $TOKEN"
curl -s -X DELETE "$OPENTABLE_API_URL/v2/booking/<rid>/reservations/<confirmation_number>" -H "Authorization: Bearer $TOKEN"
```

## Directory

```bash
curl -s "$OPENTABLE_API_URL/v2/directory/restaurants" -H "Authorization: Bearer $TOKEN"
```
