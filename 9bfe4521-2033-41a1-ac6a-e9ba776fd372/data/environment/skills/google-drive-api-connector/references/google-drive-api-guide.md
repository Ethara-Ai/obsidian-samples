# Google Drive API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$GOOGLE_DRIVE_API_URL`.** Every operation needs `Authorization: Bearer $TOKEN`, where `$TOKEN` comes from `POST /oauth/token` and carries only the scopes it was issued with (see SKILL.md, Authentication). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `GOOGLE_DRIVE_API_URL` | Base URL for all requests |
| `GOOGLE_DRIVE_CLIENT_ID` | OAuth client id of the connected account |
| `GOOGLE_DRIVE_CLIENT_SECRET` | OAuth client secret of the connected account |

## Token

```bash
TOKEN=$(curl -s -X POST "$GOOGLE_DRIVE_API_URL/oauth/token" -d grant_type=client_credentials -d client_id="$GOOGLE_DRIVE_CLIENT_ID" -d client_secret="$GOOGLE_DRIVE_CLIENT_SECRET" -d scope="<space-separated scopes>" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$GOOGLE_DRIVE_API_URL/oauth/tokeninfo" -H "Authorization: Bearer $TOKEN"
```

## Drive

```bash
curl -s "$GOOGLE_DRIVE_API_URL/drive/v3/files" -H "Authorization: Bearer $TOKEN"
curl -s "$GOOGLE_DRIVE_API_URL/drive/v3/files/<fileId>" -H "Authorization: Bearer $TOKEN"
curl -s "$GOOGLE_DRIVE_API_URL/drive/v3/files/<fileId>/export" -H "Authorization: Bearer $TOKEN"
curl -s -X POST "$GOOGLE_DRIVE_API_URL/drive/v3/files" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s -X PATCH "$GOOGLE_DRIVE_API_URL/drive/v3/files/<fileId>" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s -X DELETE "$GOOGLE_DRIVE_API_URL/drive/v3/files/<fileId>" -H "Authorization: Bearer $TOKEN"
curl -s "$GOOGLE_DRIVE_API_URL/drive/v3/files/<fileId>/permissions" -H "Authorization: Bearer $TOKEN"
curl -s -X POST "$GOOGLE_DRIVE_API_URL/drive/v3/files/<fileId>/permissions" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s -X DELETE "$GOOGLE_DRIVE_API_URL/drive/v3/files/<fileId>/permissions/<permissionId>" -H "Authorization: Bearer $TOKEN"
curl -s "$GOOGLE_DRIVE_API_URL/drive/v3/files/<fileId>/comments" -H "Authorization: Bearer $TOKEN"
curl -s -X POST "$GOOGLE_DRIVE_API_URL/drive/v3/files/<fileId>/comments" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s "$GOOGLE_DRIVE_API_URL/drive/v3/files/<fileId>/revisions" -H "Authorization: Bearer $TOKEN"
curl -s "$GOOGLE_DRIVE_API_URL/drive/v3/files/<fileId>/revisions/<revisionId>" -H "Authorization: Bearer $TOKEN"
curl -s -X PATCH "$GOOGLE_DRIVE_API_URL/drive/v3/files/<fileId>/revisions/<revisionId>" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
```

## Upload

```bash
curl -s -X POST "$GOOGLE_DRIVE_API_URL/upload/drive/v3/files" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s -X PATCH "$GOOGLE_DRIVE_API_URL/upload/drive/v3/files/<fileId>" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
```
