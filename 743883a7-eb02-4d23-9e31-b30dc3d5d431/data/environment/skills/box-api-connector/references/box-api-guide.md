# Box API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$BOX_API_URL`.** Every operation needs `Authorization: Bearer $TOKEN`, where `$TOKEN` comes from `POST /oauth/token` and carries only the scopes it was issued with (see SKILL.md, Authentication). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `BOX_API_URL` | Base URL for all requests |
| `BOX_CLIENT_ID` | OAuth client id of the connected account |
| `BOX_CLIENT_SECRET` | OAuth client secret of the connected account |

## Token

```bash
TOKEN=$(curl -s -X POST "$BOX_API_URL/oauth/token" -d grant_type=client_credentials -d client_id="$BOX_CLIENT_ID" -d client_secret="$BOX_CLIENT_SECRET" -d scope="<space-separated scopes>" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$BOX_API_URL/oauth/tokeninfo" -H "Authorization: Bearer $TOKEN"
```

## 2.0

```bash
curl -s "$BOX_API_URL/2.0/folders/<folder_id>/items" -H "Authorization: Bearer $TOKEN"
curl -s "$BOX_API_URL/2.0/files/<file_id>" -H "Authorization: Bearer $TOKEN"
curl -s "$BOX_API_URL/2.0/search" -H "Authorization: Bearer $TOKEN"
curl -s -X POST "$BOX_API_URL/2.0/folders" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s -X PUT "$BOX_API_URL/2.0/files/<file_id>" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
```

## Api

```bash
curl -s -X POST "$BOX_API_URL/api/2.0/files/content" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
```
