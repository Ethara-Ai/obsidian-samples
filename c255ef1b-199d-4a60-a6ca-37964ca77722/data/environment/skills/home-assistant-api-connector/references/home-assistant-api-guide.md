# Home Assistant API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$HOME_ASSISTANT_API_URL`.** Every operation needs `Authorization: Bearer $TOKEN`, where `$TOKEN` comes from `POST /oauth/token` and carries only the scopes it was issued with (see SKILL.md, Authentication). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `HOME_ASSISTANT_API_URL` | Base URL for all requests |
| `HOME_ASSISTANT_CLIENT_ID` | OAuth client id of the connected account |
| `HOME_ASSISTANT_CLIENT_SECRET` | OAuth client secret of the connected account |

## Token

```bash
TOKEN=$(curl -s -X POST "$HOME_ASSISTANT_API_URL/oauth/token" -d grant_type=client_credentials -d client_id="$HOME_ASSISTANT_CLIENT_ID" -d client_secret="$HOME_ASSISTANT_CLIENT_SECRET" -d scope="<space-separated scopes>" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$HOME_ASSISTANT_API_URL/oauth/tokeninfo" -H "Authorization: Bearer $TOKEN"
```

## Api

```bash
curl -s "$HOME_ASSISTANT_API_URL/api/config" -H "Authorization: Bearer $TOKEN"
curl -s "$HOME_ASSISTANT_API_URL/api/states" -H "Authorization: Bearer $TOKEN"
curl -s "$HOME_ASSISTANT_API_URL/api/states/<entity_id>" -H "Authorization: Bearer $TOKEN"
curl -s -X POST "$HOME_ASSISTANT_API_URL/api/services/light/turn_on" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"entity_id": "light.kitchen_pendant_1", "brightness_pct": 40}'
curl -s "$HOME_ASSISTANT_API_URL/api/history/period/<timestamp>" -H "Authorization: Bearer $TOKEN"
```

## Service calls

`POST /api/services/<domain>/<service>` answers `200` with only the devices whose state changed. A device it cannot
change is skipped without an error, as in Home Assistant, so an empty list `[]` can mean the device is already in
that state, or that there is no such device (an unknown `entity_id`, one of another account, or one of another
domain). To tell them apart, read `GET /api/states/<entity_id>`: it answers `404` (`Entity not found.`) for an
unknown device, and otherwise its current `state`.
