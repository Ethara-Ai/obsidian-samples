# Google Docs API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$GOOGLE_DOCS_API_URL`.** Every operation needs `Authorization: Bearer $TOKEN`, where `$TOKEN` comes from `POST /oauth/token` and carries only the scopes it was issued with (see SKILL.md, Authentication). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `GOOGLE_DOCS_API_URL` | Base URL for all requests |
| `GOOGLE_DOCS_CLIENT_ID` | OAuth client id of the connected account |
| `GOOGLE_DOCS_CLIENT_SECRET` | OAuth client secret of the connected account |

## Token

```bash
TOKEN=$(curl -s -X POST "$GOOGLE_DOCS_API_URL/oauth/token" -d grant_type=client_credentials -d client_id="$GOOGLE_DOCS_CLIENT_ID" -d client_secret="$GOOGLE_DOCS_CLIENT_SECRET" -d scope="<space-separated scopes>" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$GOOGLE_DOCS_API_URL/oauth/tokeninfo" -H "Authorization: Bearer $TOKEN"
```

## Documents

```bash
curl -s "$GOOGLE_DOCS_API_URL/v1/documents/<documentId>" -H "Authorization: Bearer $TOKEN"
curl -s -X POST "$GOOGLE_DOCS_API_URL/v1/documents" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s -X POST "$GOOGLE_DOCS_API_URL/v1/documents/<documentId>:batchUpdate" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
```
