# Withings API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$WITHINGS_API_URL`.** Every operation needs `Authorization: Bearer $TOKEN`, where `$TOKEN` comes from `POST /oauth/token` and carries only the scopes it was issued with (see SKILL.md, Authentication). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `WITHINGS_API_URL` | Base URL for all requests |
| `WITHINGS_CLIENT_ID` | OAuth client id of the connected account |
| `WITHINGS_CLIENT_SECRET` | OAuth client secret of the connected account |

## Token

```bash
TOKEN=$(curl -s -X POST "$WITHINGS_API_URL/oauth/token" -d grant_type=client_credentials -d client_id="$WITHINGS_CLIENT_ID" -d client_secret="$WITHINGS_CLIENT_SECRET" -d scope="<space-separated scopes>" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$WITHINGS_API_URL/oauth/tokeninfo" -H "Authorization: Bearer $TOKEN"
```

## Request shape

Every webservice is a `POST` whose form fields (`curl -d`, `application/x-www-form-urlencoded`) carry `action` and that action's parameters; a JSON body or a query parameter is refused. The answer is `{"status": 0, "body": {...}}`. A nonzero `status` (`503` invalid parameters, `2554` wrong action or webservice) is an error even though the HTTP status is 200. When `more` is set, send `offset` with the value the body returned to get the next page.

## Measure

```bash
curl -s -X POST "$WITHINGS_API_URL/measure" -H "Authorization: Bearer $TOKEN" -d action=getmeas -d meastypes=1,6,8 -d category=1 -d startdate=1788238800 -d enddate=1790830799
curl -s -X POST "$WITHINGS_API_URL/measure" -H "Authorization: Bearer $TOKEN" -d action=getmeas -d meastypes=9,10,11 -d lastupdate=1790830800
curl -s -X POST "$WITHINGS_API_URL/v2/measure" -H "Authorization: Bearer $TOKEN" -d action=getactivity -d startdateymd=2026-09-28 -d enddateymd=2026-10-04 -d data_fields=steps,calories
```

`getmeas` takes `meastype` or `meastypes` (1 weight, 5 fat-free mass, 6 fat ratio, 8 fat mass, 9 diastolic, 10 systolic, 11 heart pulse, 4 height, 76 muscle mass, 77 hydration, 88 bone mass), `category` (1 measures, 2 goals), `startdate` and `enddate` or `lastupdate` (Unix seconds), and `offset`. A measure's value is `value` x 10^`unit`.

## Sleep

```bash
curl -s -X POST "$WITHINGS_API_URL/v2/sleep" -H "Authorization: Bearer $TOKEN" -d action=getsummary -d startdateymd=2026-09-28 -d enddateymd=2026-10-05 -d data_fields=sleep_score,total_sleep_time
```

## User

```bash
curl -s -X POST "$WITHINGS_API_URL/v2/user" -H "Authorization: Bearer $TOKEN" -d action=getdevice
```
