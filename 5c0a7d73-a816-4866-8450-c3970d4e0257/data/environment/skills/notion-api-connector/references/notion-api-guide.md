# Notion API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$NOTION_API_URL`.** Every operation needs `Authorization: Bearer $TOKEN`, where `$TOKEN` comes from `POST /oauth/token` and carries only the scopes it was issued with (see SKILL.md, Authentication). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `NOTION_API_URL` | Base URL for all requests |
| `NOTION_CLIENT_ID` | OAuth client id of the connected account |
| `NOTION_CLIENT_SECRET` | OAuth client secret of the connected account |

## Token

```bash
TOKEN=$(curl -s -X POST "$NOTION_API_URL/oauth/token" -d grant_type=client_credentials -d client_id="$NOTION_CLIENT_ID" -d client_secret="$NOTION_CLIENT_SECRET" -d scope="<space-separated scopes>" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$NOTION_API_URL/oauth/tokeninfo" -H "Authorization: Bearer $TOKEN"
```

## Blocks

```bash
curl -s "$NOTION_API_URL/v1/blocks/<block_id>/children" -H "Authorization: Bearer $TOKEN"
curl -s -X PATCH "$NOTION_API_URL/v1/blocks/<block_id>/children" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
```

## Databases

```bash
curl -s -X POST "$NOTION_API_URL/v1/databases/<database_id>/query" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
```

## Pages

```bash
curl -s "$NOTION_API_URL/v1/pages/<page_id>" -H "Authorization: Bearer $TOKEN"
curl -s -X POST "$NOTION_API_URL/v1/pages" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s -X PATCH "$NOTION_API_URL/v1/pages/<page_id>" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
```

## Search

```bash
curl -s -X POST "$NOTION_API_URL/v1/search" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
```
