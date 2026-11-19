# Ring API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$RING_API_URL`.** Every operation needs `Authorization: Bearer $TOKEN`, where `$TOKEN` comes from `POST /oauth/token` and carries only the scopes it was issued with (see SKILL.md, Authentication). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `RING_API_URL` | Base URL for all requests |
| `RING_CLIENT_ID` | OAuth client id of the connected account |
| `RING_CLIENT_SECRET` | OAuth client secret of the connected account |

## Token

```bash
TOKEN=$(curl -s -X POST "$RING_API_URL/oauth/token" -d grant_type=client_credentials -d client_id="$RING_CLIENT_ID" -d client_secret="$RING_CLIENT_SECRET" -d scope="<space-separated scopes>" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$RING_API_URL/oauth/tokeninfo" -H "Authorization: Bearer $TOKEN"
```

## Api

```bash
curl -s -X PUT "$RING_API_URL/api/v1/mode/location/<location_id>" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
```

## Clients_Api

```bash
curl -s "$RING_API_URL/clients_api/ring_devices" -H "Authorization: Bearer $TOKEN"
curl -s "$RING_API_URL/clients_api/doorbots/<device_id>/health" -H "Authorization: Bearer $TOKEN"
curl -s "$RING_API_URL/clients_api/doorbots/<device_id>/history" -H "Authorization: Bearer $TOKEN"
curl -s "$RING_API_URL/clients_api/dings/<ding_id>/recording" -H "Authorization: Bearer $TOKEN"
```
