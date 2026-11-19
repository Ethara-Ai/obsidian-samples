# Google Slides API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$GOOGLE_SLIDES_API_URL`.** Every operation needs `Authorization: Bearer $TOKEN`, where `$TOKEN` comes from `POST /oauth/token` and carries only the scopes it was issued with (see SKILL.md, Authentication). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `GOOGLE_SLIDES_API_URL` | Base URL for all requests |
| `GOOGLE_SLIDES_CLIENT_ID` | OAuth client id of the connected account |
| `GOOGLE_SLIDES_CLIENT_SECRET` | OAuth client secret of the connected account |

## Token

```bash
TOKEN=$(curl -s -X POST "$GOOGLE_SLIDES_API_URL/oauth/token" -d grant_type=client_credentials -d client_id="$GOOGLE_SLIDES_CLIENT_ID" -d client_secret="$GOOGLE_SLIDES_CLIENT_SECRET" -d scope="<space-separated scopes>" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$GOOGLE_SLIDES_API_URL/oauth/tokeninfo" -H "Authorization: Bearer $TOKEN"
```

## Presentations

```bash
curl -s "$GOOGLE_SLIDES_API_URL/v1/presentations/<presentationId>" -H "Authorization: Bearer $TOKEN"
curl -s "$GOOGLE_SLIDES_API_URL/v1/presentations/<presentationId>/pages/<pageObjectId>" -H "Authorization: Bearer $TOKEN"
curl -s -X POST "$GOOGLE_SLIDES_API_URL/v1/presentations" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s -X POST "$GOOGLE_SLIDES_API_URL/v1/presentations/<presentationId>:batchUpdate" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
```
