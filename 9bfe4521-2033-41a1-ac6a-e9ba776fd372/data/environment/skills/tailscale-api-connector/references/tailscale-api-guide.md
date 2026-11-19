# Tailscale API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$TAILSCALE_API_URL`.** Every operation needs `Authorization: Bearer $TOKEN`, where `$TOKEN` comes from `POST /oauth/token` and carries only the scopes it was issued with (see SKILL.md, Authentication). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `TAILSCALE_API_URL` | Base URL for all requests |
| `TAILSCALE_CLIENT_ID` | OAuth client id of the connected account |
| `TAILSCALE_CLIENT_SECRET` | OAuth client secret of the connected account |

## Token

```bash
TOKEN=$(curl -s -X POST "$TAILSCALE_API_URL/oauth/token" -d grant_type=client_credentials -d client_id="$TAILSCALE_CLIENT_ID" -d client_secret="$TAILSCALE_CLIENT_SECRET" -d scope="<space-separated scopes>" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$TAILSCALE_API_URL/oauth/tokeninfo" -H "Authorization: Bearer $TOKEN"
```

## Api

```bash
curl -s "$TAILSCALE_API_URL/api/v2/tailnet/<tailnet>/devices" -H "Authorization: Bearer $TOKEN"
curl -s "$TAILSCALE_API_URL/api/v2/device/<device_id>" -H "Authorization: Bearer $TOKEN"
curl -s -X POST "$TAILSCALE_API_URL/api/v2/device/<device_id>/authorized" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s -X DELETE "$TAILSCALE_API_URL/api/v2/device/<device_id>" -H "Authorization: Bearer $TOKEN"
curl -s "$TAILSCALE_API_URL/api/v2/tailnet/<tailnet>/acl" -H "Authorization: Bearer $TOKEN"
curl -s -X POST "$TAILSCALE_API_URL/api/v2/tailnet/<tailnet>/keys" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s "$TAILSCALE_API_URL/api/v2/tailnet/<tailnet>/keys/<key_id>" -H "Authorization: Bearer $TOKEN"
```
