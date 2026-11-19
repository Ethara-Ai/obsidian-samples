<!-- api-test-results:begin -->
# Spotify Web API (Mock) - Test Results

GENERATED SECTION. DO NOT HAND-EDIT. `python3 script/gen_api_test_results.py --only spotify-api` writes everything between the api-test-results markers by sending the requests below to the service in-process; the text after the end marker is kept as written.

Base URL: `http://localhost:8108` (docker-compose: `http://spotify-api:8108`)

## Authentication

Every operation needs `Authorization: Bearer <token>` from `POST /oauth/token` with client credentials. The connected client `spotify-connector-app` (account `acct-caleb-rourke`) is granted `user-library-read`, `playlist-read-private`, `playlist-modify-private`, `user-read-playback-state`, `user-modify-playback-state`, `user-read-currently-playing`; a token requested without `scope` carries no scope. A request without a live token answers `401 invalid_token`, and a live token without the route's scope answers `403 insufficient_scope`.

## Endpoints

Each row is one request the generator sent. **Status** is the answer to the request as shown, sent with a token carrying every granted scope. **No token** is the same request with no `Authorization` header, and **Scope removed** the same request with a token carrying every granted scope except the route's own. The shared `/audit` and `/admin` planes every mock serves are described in `environment/API_DOCUMENTATION.md` and not listed.

| Method | Path | Scope | Request sent | Status | No token | Scope removed |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/oauth/token` | client credentials | `/oauth/token (form body)` | 200 | - | - |
| GET | `/health` | none | `/health` | 200 | - | - |
| GET | `/oauth/tokeninfo` | any live token | `/oauth/tokeninfo` | 200 | 401 | - |
| GET | `/v1/search` | any live token | `/v1/search?q=jazz&type=track,playlist,show&limit=5` | 200 | 401 | - |
| GET | `/v1/me/tracks` | `user-library-read` | `/v1/me/tracks?limit=20` | 200 | 401 | 403 |
| GET | `/v1/me/playlists` | `playlist-read-private` | `/v1/me/playlists?limit=20` | 200 | 401 | 403 |
| GET | `/v1/playlists/{playlist_id}/tracks` | `playlist-read-private` | `/v1/playlists/PQFTlu92qul1qdGDtU7HIY/tracks` | 200 | 401 | 403 |
| POST | `/v1/me/playlists` | `playlist-modify-private` | `/v1/me/playlists (JSON body)` | 201 | 401 | 403 |
| PUT | `/v1/playlists/{playlist_id}` | `playlist-modify-private` | `/v1/playlists/gKxmiq5eaFUrO1Gx2ODSac (JSON body)` | 200 | 401 | 403 |
| POST | `/v1/playlists/{playlist_id}/tracks` | `playlist-modify-private` | `/v1/playlists/EZpfgh0vGPrU0MZuaPlQKX/tracks (JSON body)` | 201 | 401 | 403 |
| GET | `/v1/me/player/devices` | `user-read-playback-state` | `/v1/me/player/devices` | 200 | 401 | 403 |
| PUT | `/v1/me/player/play` | `user-modify-playback-state` | `/v1/me/player/play?device_id=c79154e6b2c76baec8e644b85d33668b510ab772 (JSON body)` | 204 | 401 | 403 |
| GET | `/v1/me/player/currently-playing` | `user-read-currently-playing` | `/v1/me/player/currently-playing` | 200 | 401 | 403 |
| PUT | `/v1/me/player` | `user-modify-playback-state` | `/v1/me/player (JSON body)` | 204 | 401 | 403 |

## Seed files

| File | Records |
| --- | --- |
| `accounts.json` | 1 |
| `albums.json` | 30 |
| `artists.json` | 25 |
| `devices.json` | 4 |
| `episodes.json` | 60 |
| `playback.json` | 1 |
| `playlist_follows.json` | 4 |
| `playlist_items.json` | 381 |
| `playlists.json` | 29 |
| `saved_tracks.json` | 60 |
| `shows.json` | 15 |
| `tracks.json` | 120 |
| `users.json` | 8 |
<!-- api-test-results:end -->

## Connector operations covered

`.search`, `.library` (saved tracks and playlists), `.add-to-collection`, `.create-collection`, `.update-collection`, `.devices`, `.play`, `.now-playing`, `.transfer`, `.playlist-tracks`. Nothing else is served: no saving tracks to the library, no queue, no skip.

## Mock simplifications

- `q` on search is matched as free text (every word must appear in the item's name, artist names, album name, publisher or description as applicable); `artist:`-style field filters are not interpreted. Search lists public playlists only. `type` is required; `limit` is 1-50 (default 20) and `offset` 0-1000.
- Playback progress is stored when a command changes it; it does not advance with the clock.
- `PUT /v1/me/player/play` with no body resumes the stored item on the active device (or on `device_id`); with no active device and no `device_id` it is `404 NO_ACTIVE_DEVICE`. `context_uri` is an album, artist (top tracks), playlist or show (newest episode first); `offset` applies to albums, playlists and `uris` only. `context_uri` together with `uris`, an `offset` with neither, or a `position_ms` past the item's end is a 400. A restricted device answers `403`.
- `PUT /v1/me/player` takes exactly one device id; `play: true` needs something to play, otherwise the current play state is kept.
- `PUT /v1/playlists/{id}` changes only the owner's playlists and answers 200 with no body; an empty body is a 400, and `collaborative` on a public playlist is a 400. `POST /v1/me/playlists` defaults `public` to true.
- `POST /v1/playlists/{id}/tracks` accepts `spotify:track:` and `spotify:episode:` uris that exist in the catalog (up to 100), validates all of them before writing, inserts at `position` (default: end) and returns a new `snapshot_id`. Allowed on playlists the account owns and on collaborative playlists it follows.

## Seed data

- Catalog: 25 artists, 30 albums, 120 tracks (4 per album, 6 with a featured artist), 15 shows with 60 episodes, 20 public playlists by 7 curators
- 1 connected listener `acct-caleb-rourke` (high-school music teacher, Portland, Oregon): 60 saved tracks (2026-01 to 2026-09), 8 owned playlists with tracks (one with episodes), follows 4 playlists (one collaborative, owned by a colleague)
- 4 devices (Classroom Laptop active; Kitchen Echo is restricted); initial playback: playing the Classroom Background playlist at 84,213 ms
- 1 OAuth client `spotify-connector-app`: every scope granted; a token requested without `scope` carries no scope (enough for search)
