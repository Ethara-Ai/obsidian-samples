# Uber Rides API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$UBER_API_URL`.** Every operation needs `Authorization: Bearer $TOKEN`, where `$TOKEN` comes from `POST /oauth/token` and carries only the scopes it was issued with (see SKILL.md, Authentication). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `UBER_API_URL` | Base URL for all requests |
| `UBER_CLIENT_ID` | OAuth client id of the connected account |
| `UBER_CLIENT_SECRET` | OAuth client secret of the connected account |

## Token

```bash
TOKEN=$(curl -s -X POST "$UBER_API_URL/oauth/token" -d grant_type=client_credentials -d client_id="$UBER_CLIENT_ID" -d client_secret="$UBER_CLIENT_SECRET" -d scope="<space-separated scopes>" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$UBER_API_URL/oauth/tokeninfo" -H "Authorization: Bearer $TOKEN"
```

## V1.2

```bash
curl -s "$UBER_API_URL/v1.2/products" -H "Authorization: Bearer $TOKEN"
curl -s "$UBER_API_URL/v1.2/estimates/price" -H "Authorization: Bearer $TOKEN"
curl -s "$UBER_API_URL/v1.2/estimates/time" -H "Authorization: Bearer $TOKEN"
curl -s -X POST "$UBER_API_URL/v1.2/requests" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s "$UBER_API_URL/v1.2/requests/<request_id>" -H "Authorization: Bearer $TOKEN"
curl -s -X DELETE "$UBER_API_URL/v1.2/requests/<request_id>" -H "Authorization: Bearer $TOKEN"
curl -s "$UBER_API_URL/v1.2/history" -H "Authorization: Bearer $TOKEN"
```
