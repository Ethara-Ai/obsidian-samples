<!-- api-test-results:begin -->
# Home Assistant API (Mock) - Test Results

GENERATED SECTION. DO NOT HAND-EDIT. `python3 script/gen_api_test_results.py --only home-assistant-api` writes everything between the api-test-results markers by sending the requests below to the service in-process; the text after the end marker is kept as written.

Base URL: `http://localhost:8130` (docker-compose: `http://home-assistant-api:8130`)

## Authentication

Every operation needs `Authorization: Bearer <token>` from `POST /oauth/token` with client credentials. The connected client `hass-connector-app` (account `acct-dana-whitfield`) is granted `homeassistant:read`, `homeassistant:control`; a token requested without `scope` carries `homeassistant:read`. A request without a live token answers `401 invalid_token`, and a live token without the route's scope answers `403 insufficient_scope`.

## Endpoints

Each row is one request the generator sent. **Status** is the answer to the request as shown, sent with a token carrying every granted scope. **No token** is the same request with no `Authorization` header, and **Scope removed** the same request with a token carrying every granted scope except the route's own. The shared `/audit` and `/admin` planes every mock serves are described in `environment/API_DOCUMENTATION.md` and not listed.

| Method | Path | Scope | Request sent | Status | No token | Scope removed |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/oauth/token` | client credentials | `/oauth/token (form body)` | 200 | - | - |
| GET | `/health` | none | `/health` | 200 | - | - |
| GET | `/oauth/tokeninfo` | any live token | `/oauth/tokeninfo` | 200 | 401 | - |
| GET | `/api/config` | `homeassistant:read` | `/api/config` | 200 | 401 | 403 |
| GET | `/api/states` | `homeassistant:read` | `/api/states` | 200 | 401 | 403 |
| GET | `/api/states/{entity_id}` | `homeassistant:read` | `/api/states/climate.upstairs` | 200 | 401 | 403 |
| POST | `/api/services/{domain}/{service}` | `homeassistant:control` | `/api/services/light/turn_on (JSON body)` | 200 | 401 | 403 |
| POST | `/api/services/{domain}/{service}` | `homeassistant:control` | `/api/services/climate/set_temperature (JSON body)` | 200 | 401 | 403 |
| GET | `/api/history/period/{timestamp}` | `homeassistant:read` | `/api/history/period/2026-10-03T00:00:00-05:00?filter_entity_id=light.kitchen_pendant_1,climate.main_floor&end_time=2026-10-04T00:00:00-05:00` | 200 | 401 | 403 |
| GET | `/api/history/period/{timestamp}` | `homeassistant:read` | `/api/history/period/2026-10-03T00:00:00-05:00?filter_entity_id=light.kitchen_pendant_1&minimal_response=&no_attributes=&significant_changes_only=` | 200 | 401 | 403 |

## Seed files

| File | Records |
| --- | --- |
| `config.json` | 1 |
| `history.json` | 387 |
| `scenes.json` | 5 |
| `states.json` | 89 |
<!-- api-test-results:end -->

## Connector operations covered

Read the configuration (`GET /api/config`), list all entity states (`GET /api/states`), get one entity's state (`GET /api/states/{entity_id}`), call a service on entities (`POST /api/services/{domain}/{service}`, for example `light.turn_on` or `climate.set_temperature`), and read entities' history for a period (`GET /api/history/period/{timestamp}`). Nothing else is served.

## Mock simplifications

- Errors use Home Assistant's body, `{"message"}`: `404 Entity not found.` for an entity the home does not have, `400 Service not found.` for a service outside the catalog below, `400 Data should be valid JSON.` for a body that is not a JSON object, voluptuous-style messages for bad service data (`extra keys not allowed @ data['colour']`, `required key not provided @ data['position']`, `value must be at most 100 for dictionary value @ data['brightness_pct']`), and `400` for a query parameter the operation does not take. Home Assistant's long-lived tokens carry no scopes, so `homeassistant:read` and `homeassistant:control` are this mock's own.
- Services served: `light.turn_on` (`brightness`, `brightness_pct`, `color_temp_kelvin`, `rgb_color`, `transition`), `light.turn_off`, `light.toggle`, `switch` and `input_boolean` `turn_on`, `turn_off`, `toggle`, `fan.turn_on`, `fan.turn_off`, `fan.set_percentage`, `cover.open_cover`, `cover.close_cover`, `cover.set_cover_position`, `lock.lock`, `lock.unlock`, `climate.set_temperature`, `climate.set_hvac_mode`, `climate.turn_on`, `climate.turn_off`, `media_player.turn_on`, `turn_off`, `media_play`, `media_pause`, `volume_set`, `scene.turn_on`, `vacuum.start` and `vacuum.return_to_base`. Targets are given as `entity_id` (one id, a comma list or a list); area and device targets are not served.
- As in Home Assistant, entities outside the service's domain or unknown to the home are skipped rather than refused, and the answer lists only the states that changed, so a call that changes nothing answers `[]`. A recalled scene sets every entity it stores and stamps the scene's own state with the time.
- History: `filter_entity_id` (required, a comma list) and `end_time` (default one day after the path's timestamp) select the window; each entity's list starts with its state at the start of the window. `minimal_response` keeps only `state` and `last_changed` for all but the first and last entries, `no_attributes` drops attributes, and `significant_changes_only` drops attribute-only changes except for climate and device trackers. Every service call that changes an entity records it in history.
- No templates, events, automation or script editing, calendar, camera images, logbook, or service response data.

## Seed data

- Connected account `acct-dana-whitfield`: Dana Whitfield's home, Larkmoor House, near Evanston (time zone America/Chicago, imperial units, coordinates rounded to about a kilometre), on Home Assistant 2026.9.3.
- 89 entities: the 17 Hue lights philips-hue-api also serves, by the same names, and the Ring floodlight; switches, fans, shades and the garage door; three door locks; two thermostats; temperature, humidity, energy and air quality sensors; door, window, leak and motion sensors; the Ring doorbell, cameras and alarm the ring-api devices also appear as; three speakers and the TV; Dana and Jordan Ellis as people with their phones; five scenes (Good Morning, Movie Night, Dinner, Bedtime, Away), six automations, a script, two zones, the weather and the sun.
- 387 history rows from October 2 to October 5, 2026: evening light cycles, thermostat schedules, door and garage events, temperature readings and comings and goings; every entity's newest row is its current state.
- 1 OAuth client `hass-connector-app`: both scopes granted; a token requested without `scope` carries only `homeassistant:read`.
