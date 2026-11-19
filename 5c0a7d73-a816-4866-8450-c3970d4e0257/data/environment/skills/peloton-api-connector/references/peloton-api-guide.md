# Peloton API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$PELOTON_API_URL`.** Every operation needs `Authorization: Bearer $TOKEN`, where `$TOKEN` comes from `POST /oauth/token` and carries only the scopes it was issued with (see SKILL.md, Authentication). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `PELOTON_API_URL` | Base URL for all requests |
| `PELOTON_CLIENT_ID` | OAuth client id of the connected account |
| `PELOTON_CLIENT_SECRET` | OAuth client secret of the connected account |

## Token

```bash
TOKEN=$(curl -s -X POST "$PELOTON_API_URL/oauth/token" -d grant_type=client_credentials -d client_id="$PELOTON_CLIENT_ID" -d client_secret="$PELOTON_CLIENT_SECRET" -d scope="<space-separated scopes>" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$PELOTON_API_URL/oauth/tokeninfo" -H "Authorization: Bearer $TOKEN"
```

## Api

```bash
curl -s "$PELOTON_API_URL/api/me" -H "Authorization: Bearer $TOKEN"
curl -s "$PELOTON_API_URL/api/user/<user_id>/workouts" -H "Authorization: Bearer $TOKEN"
curl -s "$PELOTON_API_URL/api/workout/<workout_id>" -H "Authorization: Bearer $TOKEN"
curl -s "$PELOTON_API_URL/api/workout/<workout_id>/performance_graph" -H "Authorization: Bearer $TOKEN"
curl -s "$PELOTON_API_URL/api/v2/ride/archived" -H "Authorization: Bearer $TOKEN"
```
