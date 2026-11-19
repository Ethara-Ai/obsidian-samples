# Tessie API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$TESSIE_API_URL`.** Every operation needs `Authorization: Bearer $TOKEN`, where `$TOKEN` comes from `POST /oauth/token` and carries only the scopes it was issued with (see SKILL.md, Authentication). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `TESSIE_API_URL` | Base URL for all requests |
| `TESSIE_CLIENT_ID` | OAuth client id of the connected account |
| `TESSIE_CLIENT_SECRET` | OAuth client secret of the connected account |

## Token

```bash
TOKEN=$(curl -s -X POST "$TESSIE_API_URL/oauth/token" -d grant_type=client_credentials -d client_id="$TESSIE_CLIENT_ID" -d client_secret="$TESSIE_CLIENT_SECRET" -d scope="<space-separated scopes>" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$TESSIE_API_URL/oauth/tokeninfo" -H "Authorization: Bearer $TOKEN"
```

## Battery

```bash
curl -s "$TESSIE_API_URL/<vin>/battery" -H "Authorization: Bearer $TOKEN"
```

## Command

```bash
curl -s -X POST "$TESSIE_API_URL/<vin>/command/lock" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s -X POST "$TESSIE_API_URL/<vin>/command/unlock" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s -X POST "$TESSIE_API_URL/<vin>/command/start_climate" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s -X POST "$TESSIE_API_URL/<vin>/command/stop_climate" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s -X POST "$TESSIE_API_URL/<vin>/command/start_charging" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s -X POST "$TESSIE_API_URL/<vin>/command/stop_charging" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
```

## Drives

```bash
curl -s "$TESSIE_API_URL/<vin>/drives" -H "Authorization: Bearer $TOKEN"
```

## Location

```bash
curl -s "$TESSIE_API_URL/<vin>/location" -H "Authorization: Bearer $TOKEN"
```

## State

```bash
curl -s "$TESSIE_API_URL/<vin>/state" -H "Authorization: Bearer $TOKEN"
```

## Vehicles

```bash
curl -s "$TESSIE_API_URL/vehicles" -H "Authorization: Bearer $TOKEN"
```
