# Function Health API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$FUNCTION_HEALTH_API_URL`.** Every operation needs `Authorization: Bearer $TOKEN`, where `$TOKEN` comes from `POST /oauth/token` and carries only the scopes it was issued with (see SKILL.md, Authentication). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `FUNCTION_HEALTH_API_URL` | Base URL for all requests |
| `FUNCTION_HEALTH_CLIENT_ID` | OAuth client id of the connected account |
| `FUNCTION_HEALTH_CLIENT_SECRET` | OAuth client secret of the connected account |

## Token

```bash
TOKEN=$(curl -s -X POST "$FUNCTION_HEALTH_API_URL/oauth/token" -d grant_type=client_credentials -d client_id="$FUNCTION_HEALTH_CLIENT_ID" -d client_secret="$FUNCTION_HEALTH_CLIENT_SECRET" -d scope="<space-separated scopes>" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$FUNCTION_HEALTH_API_URL/oauth/tokeninfo" -H "Authorization: Bearer $TOKEN"
```

## Biomarkers

```bash
curl -s "$FUNCTION_HEALTH_API_URL/v1/biomarkers/<biomarker_id>/history" -H "Authorization: Bearer $TOKEN"
```

## Recommendations

```bash
curl -s "$FUNCTION_HEALTH_API_URL/v1/recommendations" -H "Authorization: Bearer $TOKEN"
```

## Visits

```bash
curl -s "$FUNCTION_HEALTH_API_URL/v1/visits" -H "Authorization: Bearer $TOKEN"
curl -s "$FUNCTION_HEALTH_API_URL/v1/visits/<visit_id>/results" -H "Authorization: Bearer $TOKEN"
```
