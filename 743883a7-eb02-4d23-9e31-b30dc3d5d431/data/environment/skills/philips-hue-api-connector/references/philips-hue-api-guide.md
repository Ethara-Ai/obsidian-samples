# Philips Hue API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$PHILIPS_HUE_API_URL`.** Every operation needs `Authorization: Bearer $TOKEN`, where `$TOKEN` comes from `POST /oauth/token` and carries only the scopes it was issued with (see SKILL.md, Authentication). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `PHILIPS_HUE_API_URL` | Base URL for all requests |
| `PHILIPS_HUE_CLIENT_ID` | OAuth client id of the connected account |
| `PHILIPS_HUE_CLIENT_SECRET` | OAuth client secret of the connected account |

## Token

```bash
TOKEN=$(curl -s -X POST "$PHILIPS_HUE_API_URL/oauth/token" -d grant_type=client_credentials -d client_id="$PHILIPS_HUE_CLIENT_ID" -d client_secret="$PHILIPS_HUE_CLIENT_SECRET" -d scope="<space-separated scopes>" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$PHILIPS_HUE_API_URL/oauth/tokeninfo" -H "Authorization: Bearer $TOKEN"
```

## Clip

```bash
curl -s "$PHILIPS_HUE_API_URL/clip/v2/resource/light" -H "Authorization: Bearer $TOKEN"
curl -s "$PHILIPS_HUE_API_URL/clip/v2/resource/light/<light_id>" -H "Authorization: Bearer $TOKEN"
curl -s -X PUT "$PHILIPS_HUE_API_URL/clip/v2/resource/light/<light_id>" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s "$PHILIPS_HUE_API_URL/clip/v2/resource/room" -H "Authorization: Bearer $TOKEN"
curl -s "$PHILIPS_HUE_API_URL/clip/v2/resource/scene" -H "Authorization: Bearer $TOKEN"
curl -s -X PUT "$PHILIPS_HUE_API_URL/clip/v2/resource/scene/<scene_id>" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
```
