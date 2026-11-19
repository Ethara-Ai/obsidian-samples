# FlightAware AeroAPI (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$FLIGHTAWARE_API_URL`.** Every operation needs `Authorization: Bearer $TOKEN`, where `$TOKEN` comes from `POST /oauth/token` and carries only the scopes it was issued with (see SKILL.md, Authentication). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `FLIGHTAWARE_API_URL` | Base URL for all requests |
| `FLIGHTAWARE_CLIENT_ID` | OAuth client id of the connected account |
| `FLIGHTAWARE_CLIENT_SECRET` | OAuth client secret of the connected account |

## Token

```bash
TOKEN=$(curl -s -X POST "$FLIGHTAWARE_API_URL/oauth/token" -d grant_type=client_credentials -d client_id="$FLIGHTAWARE_CLIENT_ID" -d client_secret="$FLIGHTAWARE_CLIENT_SECRET" -d scope="<space-separated scopes>" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$FLIGHTAWARE_API_URL/oauth/tokeninfo" -H "Authorization: Bearer $TOKEN"
```

## Aeroapi

```bash
curl -s "$FLIGHTAWARE_API_URL/aeroapi/ping" -H "Authorization: Bearer $TOKEN"
curl -s "$FLIGHTAWARE_API_URL/aeroapi/flights/<ident>" -H "Authorization: Bearer $TOKEN"
curl -s "$FLIGHTAWARE_API_URL/aeroapi/airports/<id>/delays" -H "Authorization: Bearer $TOKEN"
curl -s "$FLIGHTAWARE_API_URL/aeroapi/airports/<id>/weather/observations" -H "Authorization: Bearer $TOKEN"
```
