# Instagram Graph API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$INSTAGRAM_API_URL`.** Every operation needs `Authorization: Bearer $TOKEN`, where `$TOKEN` comes from `POST /oauth/token` and carries only the scopes it was issued with (see SKILL.md, Authentication). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `INSTAGRAM_API_URL` | Base URL for all requests |
| `INSTAGRAM_CLIENT_ID` | OAuth client id of the connected account |
| `INSTAGRAM_CLIENT_SECRET` | OAuth client secret of the connected account |

## Token

```bash
TOKEN=$(curl -s -X POST "$INSTAGRAM_API_URL/oauth/token" -d grant_type=client_credentials -d client_id="$INSTAGRAM_CLIENT_ID" -d client_secret="$INSTAGRAM_CLIENT_SECRET" -d scope="<space-separated scopes>" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$INSTAGRAM_API_URL/oauth/tokeninfo" -H "Authorization: Bearer $TOKEN"
```

## V21.0

```bash
curl -s "$INSTAGRAM_API_URL/v21.0/me/accounts" -H "Authorization: Bearer $TOKEN"
curl -s "$INSTAGRAM_API_URL/v21.0/<ig_user_id>" -H "Authorization: Bearer $TOKEN"
curl -s "$INSTAGRAM_API_URL/v21.0/<ig_user_id>/media" -H "Authorization: Bearer $TOKEN"
curl -s -X POST "$INSTAGRAM_API_URL/v21.0/<ig_user_id>/media" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s -X POST "$INSTAGRAM_API_URL/v21.0/<ig_user_id>/media_publish" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s "$INSTAGRAM_API_URL/v21.0/<ig_user_id>/insights" -H "Authorization: Bearer $TOKEN"
curl -s "$INSTAGRAM_API_URL/v21.0/<ig_user_id>/saved_media" -H "Authorization: Bearer $TOKEN"
curl -s "$INSTAGRAM_API_URL/v21.0/<media_id>/comments" -H "Authorization: Bearer $TOKEN"
curl -s "$INSTAGRAM_API_URL/v21.0/<ig_user_id>/followers" -H "Authorization: Bearer $TOKEN"
curl -s "$INSTAGRAM_API_URL/v21.0/<ig_user_id>/following" -H "Authorization: Bearer $TOKEN"
```
