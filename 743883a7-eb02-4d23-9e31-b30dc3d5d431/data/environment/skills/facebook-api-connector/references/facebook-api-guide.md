# Facebook Graph API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$FACEBOOK_API_URL`.** Every operation needs `Authorization: Bearer $TOKEN`, where `$TOKEN` comes from `POST /oauth/token` and carries only the scopes it was issued with (see SKILL.md, Authentication). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `FACEBOOK_API_URL` | Base URL for all requests |
| `FACEBOOK_CLIENT_ID` | OAuth client id of the connected account |
| `FACEBOOK_CLIENT_SECRET` | OAuth client secret of the connected account |

## Token

```bash
TOKEN=$(curl -s -X POST "$FACEBOOK_API_URL/oauth/token" -d grant_type=client_credentials -d client_id="$FACEBOOK_CLIENT_ID" -d client_secret="$FACEBOOK_CLIENT_SECRET" -d scope="<space-separated scopes>" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$FACEBOOK_API_URL/oauth/tokeninfo" -H "Authorization: Bearer $TOKEN"
```

## V21.0

```bash
curl -s "$FACEBOOK_API_URL/v21.0/me" -H "Authorization: Bearer $TOKEN"
curl -s "$FACEBOOK_API_URL/v21.0/me/feed" -H "Authorization: Bearer $TOKEN"
curl -s -X POST "$FACEBOOK_API_URL/v21.0/me/feed" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s "$FACEBOOK_API_URL/v21.0/me/home" -H "Authorization: Bearer $TOKEN"
curl -s "$FACEBOOK_API_URL/v21.0/me/groups" -H "Authorization: Bearer $TOKEN"
curl -s "$FACEBOOK_API_URL/v21.0/<group_id>/feed" -H "Authorization: Bearer $TOKEN"
curl -s "$FACEBOOK_API_URL/v21.0/me/saved" -H "Authorization: Bearer $TOKEN"
curl -s "$FACEBOOK_API_URL/v21.0/marketplace_listings" -H "Authorization: Bearer $TOKEN"
curl -s "$FACEBOOK_API_URL/v21.0/marketplace_listings/<listing_id>" -H "Authorization: Bearer $TOKEN"
curl -s "$FACEBOOK_API_URL/v21.0/posts" -H "Authorization: Bearer $TOKEN"
curl -s "$FACEBOOK_API_URL/v21.0/<owner_id>_<post_suffix>" -H "Authorization: Bearer $TOKEN"
curl -s "$FACEBOOK_API_URL/v21.0/<user_id>" -H "Authorization: Bearer $TOKEN"
```
