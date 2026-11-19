# Health Records API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$HEALTH_API_URL`.** Every operation needs `Authorization: Bearer $TOKEN`, where `$TOKEN` comes from `POST /oauth/token` and carries only the scopes it was issued with (see SKILL.md, Authentication). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `HEALTH_API_URL` | Base URL for all requests |
| `HEALTH_CLIENT_ID` | OAuth client id of the connected account |
| `HEALTH_CLIENT_SECRET` | OAuth client secret of the connected account |

## Token

```bash
TOKEN=$(curl -s -X POST "$HEALTH_API_URL/oauth/token" -d grant_type=client_credentials -d client_id="$HEALTH_CLIENT_ID" -d client_secret="$HEALTH_CLIENT_SECRET" -d scope="<space-separated scopes>" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$HEALTH_API_URL/oauth/tokeninfo" -H "Authorization: Bearer $TOKEN"
```

## Measurements

```bash
curl -s "$HEALTH_API_URL/v1/measurements" -H "Authorization: Bearer $TOKEN"
```

## Nutrition

```bash
curl -s "$HEALTH_API_URL/v1/nutrition" -H "Authorization: Bearer $TOKEN"
```

## Sleep

```bash
curl -s "$HEALTH_API_URL/v1/sleep" -H "Authorization: Bearer $TOKEN"
```

## Workouts

```bash
curl -s "$HEALTH_API_URL/v1/workouts" -H "Authorization: Bearer $TOKEN"
```
