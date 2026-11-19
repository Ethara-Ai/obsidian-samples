# Threads API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$THREADS_API_URL`.** Every operation needs `Authorization: Bearer $TOKEN`, where `$TOKEN` comes from `POST /oauth/token` and carries only the scopes it was issued with (see SKILL.md, Authentication). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `THREADS_API_URL` | Base URL for all requests |
| `THREADS_CLIENT_ID` | OAuth client id of the connected account |
| `THREADS_CLIENT_SECRET` | OAuth client secret of the connected account |

## Token

```bash
TOKEN=$(curl -s -X POST "$THREADS_API_URL/oauth/token" -d grant_type=client_credentials -d client_id="$THREADS_CLIENT_ID" -d client_secret="$THREADS_CLIENT_SECRET" -d scope="<space-separated scopes>" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$THREADS_API_URL/oauth/tokeninfo" -H "Authorization: Bearer $TOKEN"
```

## V1.0

```bash
curl -s "$THREADS_API_URL/v1.0/me" -H "Authorization: Bearer $TOKEN"
curl -s "$THREADS_API_URL/v1.0/<threads_media_id>" -H "Authorization: Bearer $TOKEN"
curl -s "$THREADS_API_URL/v1.0/<threads_user_id>/threads" -H "Authorization: Bearer $TOKEN"
curl -s -X POST "$THREADS_API_URL/v1.0/<threads_user_id>/threads" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s -X POST "$THREADS_API_URL/v1.0/<threads_user_id>/threads_publish" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s "$THREADS_API_URL/v1.0/<threads_media_id>/replies" -H "Authorization: Bearer $TOKEN"
```
