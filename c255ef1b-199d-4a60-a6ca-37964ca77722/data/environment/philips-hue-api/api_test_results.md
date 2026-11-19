<!-- api-test-results:begin -->
# Philips Hue API (Mock) - Test Results

GENERATED SECTION. DO NOT HAND-EDIT. `python3 script/gen_api_test_results.py --only philips-hue-api` writes everything between the api-test-results markers by sending the requests below to the service in-process; the text after the end marker is kept as written.

Base URL: `http://localhost:8131` (docker-compose: `http://philips-hue-api:8131`)

## Authentication

Every operation needs `Authorization: Bearer <token>` from `POST /oauth/token` with client credentials. The connected client `hue-connector-app` (account `acct-dana-whitfield`) is granted `hue.read`, `hue.control`; a token requested without `scope` carries `hue.read`. A request without a live token answers `401 invalid_token`, and a live token without the route's scope answers `403 insufficient_scope`.

## Endpoints

Each row is one request the generator sent. **Status** is the answer to the request as shown, sent with a token carrying every granted scope. **No token** is the same request with no `Authorization` header, and **Scope removed** the same request with a token carrying every granted scope except the route's own. The shared `/audit` and `/admin` planes every mock serves are described in `environment/API_DOCUMENTATION.md` and not listed.

| Method | Path | Scope | Request sent | Status | No token | Scope removed |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/oauth/token` | client credentials | `/oauth/token (form body)` | 200 | - | - |
| GET | `/health` | none | `/health` | 200 | - | - |
| GET | `/oauth/tokeninfo` | any live token | `/oauth/tokeninfo` | 200 | 401 | - |
| GET | `/clip/v2/resource/light` | `hue.read` | `/clip/v2/resource/light` | 200 | 401 | 403 |
| GET | `/clip/v2/resource/light/{light_id}` | `hue.read` | `/clip/v2/resource/light/<Porch light id>` | 200 | 401 | 403 |
| PUT | `/clip/v2/resource/light/{light_id}` | `hue.control` | `/clip/v2/resource/light/<Porch light id> (JSON body)` | 200 | 401 | 403 |
| GET | `/clip/v2/resource/room` | `hue.read` | `/clip/v2/resource/room` | 200 | 401 | 403 |
| GET | `/clip/v2/resource/scene` | `hue.read` | `/clip/v2/resource/scene` | 200 | 401 | 403 |
| PUT | `/clip/v2/resource/scene/{scene_id}` | `hue.control` | `/clip/v2/resource/scene/<Living Room Relax scene id> (JSON body)` | 200 | 401 | 403 |

## Seed files

| File | Records |
| --- | --- |
| `bridge.json` | 1 |
| `devices.json` | 26 |
| `grouped_lights.json` | 9 |
| `lights.json` | 17 |
| `rooms.json` | 8 |
| `scenes.json` | 92 |
<!-- api-test-results:end -->

## Connector operations covered

List lights (`GET /clip/v2/resource/light`), get a light (`GET /clip/v2/resource/light/{id}`), change a light's on/off state, brightness and colour (`PUT /clip/v2/resource/light/{id}`), list rooms (`GET /clip/v2/resource/room`), list scenes (`GET /clip/v2/resource/scene`), and recall a scene (`PUT /clip/v2/resource/scene/{id}` with a `recall` body). Nothing else is served.

## Mock simplifications

- The Hue bridge authenticates with a `hue-application-key` header and has no scopes; this mock takes a bearer token from `POST /oauth/token` instead, with its own scopes `hue.read` and `hue.control`.
- Answers use the CLIP v2 envelope, `{"errors": [], "data": [...]}`, and errors the same envelope with a description: `404 Not Found` for an id the bridge does not have, `400` for invalid JSON, an unknown or missing property, a value out of range, colour or colour temperature sent to a light that cannot show it, a palette recall on a scene without a palette, or a query parameter (none of these routes takes one).
- A light change takes `on.on`, `dimming.brightness` (0 to 100 percent), `color_temperature.mirek` (153 to 500), `color.xy` and `dynamics.duration`; a colour light switches to `xy` mode when given a colour and back to colour temperature when given a mirek. Setting brightness without `on` changes the stored level of a light that stays off. Changing a light by hand marks its room's scenes inactive.
- A scene recall takes `recall.action` (`active`, `static`, or `dynamic_palette` for scenes with a palette), `recall.duration` and `recall.dimming.brightness`, which overrides every light the scene turns on. Recalling applies the scene's action to each of its lights, marks it active (`static` or `dynamic_palette`) with the recall time, and marks the room's other scenes inactive. Scenes cannot be created, renamed or edited.
- No zones, grouped light commands, entertainment areas, effects, timed effects, alerts, identify, devices, sensors or the event stream.

## Seed data

- Connected account `acct-dana-whitfield`: the Hue bridge in Dana Whitfield's home, Larkmoor House, whose 17 lights are the ones home-assistant-api shows by the same names, on and off as Home Assistant has them at the start (the kitchen pendants, the office desk lamp and the first hallway light on).
- 17 lights (colour, white ambiance and white-only bulbs, lamps, lightstrips and an outdoor lantern), 26 devices (the lights, four switches and buttons, three motion sensors and the bridge), 8 rooms with their grouped lights, and 92 scenes: Hue's default scenes in every room, gallery scenes with colour palettes in the rooms with colour lights, and Dana's own (Movie night, Reading corner, Cooking, Late snack, Dinner party, Video call, Drafting, Wind down, Wake up, Night path, Welcome home, Halloween, Workbench). Every scene starts inactive.
- 1 OAuth client `hue-connector-app`: both scopes granted; a token requested without `scope` carries only `hue.read`.
