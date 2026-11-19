# Spotify Web API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$SPOTIFY_API_URL`.** Every operation needs `Authorization: Bearer $TOKEN`, where `$TOKEN` comes from `POST /oauth/token` and carries only the scopes it was issued with (see SKILL.md, Authentication). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `SPOTIFY_API_URL` | Base URL for all requests |
| `SPOTIFY_CLIENT_ID` | OAuth client id of the connected account |
| `SPOTIFY_CLIENT_SECRET` | OAuth client secret of the connected account |

## Token

```bash
TOKEN=$(curl -s -X POST "$SPOTIFY_API_URL/oauth/token" -d grant_type=client_credentials -d client_id="$SPOTIFY_CLIENT_ID" -d client_secret="$SPOTIFY_CLIENT_SECRET" -d scope="<space-separated scopes>" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$SPOTIFY_API_URL/oauth/tokeninfo" -H "Authorization: Bearer $TOKEN"
```

## Me

```bash
curl -s "$SPOTIFY_API_URL/v1/me/tracks" -H "Authorization: Bearer $TOKEN"
curl -s "$SPOTIFY_API_URL/v1/me/playlists" -H "Authorization: Bearer $TOKEN"
curl -s -X POST "$SPOTIFY_API_URL/v1/me/playlists" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s "$SPOTIFY_API_URL/v1/me/player/devices" -H "Authorization: Bearer $TOKEN"
curl -s -X PUT "$SPOTIFY_API_URL/v1/me/player/play" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s "$SPOTIFY_API_URL/v1/me/player/currently-playing" -H "Authorization: Bearer $TOKEN"
curl -s -X PUT "$SPOTIFY_API_URL/v1/me/player" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
```

## Playlists

```bash
curl -s "$SPOTIFY_API_URL/v1/playlists/<playlist_id>/tracks" -H "Authorization: Bearer $TOKEN"
curl -s -X PUT "$SPOTIFY_API_URL/v1/playlists/<playlist_id>" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
curl -s -X POST "$SPOTIFY_API_URL/v1/playlists/<playlist_id>/tracks" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
```

## Search

```bash
curl -s "$SPOTIFY_API_URL/v1/search" -H "Authorization: Bearer $TOKEN"
```
