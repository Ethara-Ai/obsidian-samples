# Granola API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$GRANOLA_API_URL`.** Every operation needs `Authorization: Bearer $TOKEN`, where `$TOKEN` comes from `POST /oauth/token` and carries only the scopes it was issued with (see SKILL.md, Authentication). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `GRANOLA_API_URL` | Base URL for all requests |
| `GRANOLA_CLIENT_ID` | OAuth client id of the connected account |
| `GRANOLA_CLIENT_SECRET` | OAuth client secret of the connected account |

## Token

```bash
TOKEN=$(curl -s -X POST "$GRANOLA_API_URL/oauth/token" -d grant_type=client_credentials -d client_id="$GRANOLA_CLIENT_ID" -d client_secret="$GRANOLA_CLIENT_SECRET" -d scope="<space-separated scopes>" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$GRANOLA_API_URL/oauth/tokeninfo" -H "Authorization: Bearer $TOKEN"
```

## Notes

```bash
curl -s "$GRANOLA_API_URL/v1/notes" -H "Authorization: Bearer $TOKEN"
curl -s "$GRANOLA_API_URL/v1/notes/search" -H "Authorization: Bearer $TOKEN"
curl -s "$GRANOLA_API_URL/v1/notes/<note_id>" -H "Authorization: Bearer $TOKEN"
```
