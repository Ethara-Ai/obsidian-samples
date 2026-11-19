<!-- api-test-results:begin -->
# Tessie API (Mock) - Test Results

GENERATED SECTION. DO NOT HAND-EDIT. `python3 script/gen_api_test_results.py --only tessie-api` writes everything between the api-test-results markers by sending the requests below to the service in-process; the text after the end marker is kept as written.

Base URL: `http://localhost:8133` (docker-compose: `http://tessie-api:8133`)

## Authentication

Every operation needs `Authorization: Bearer <token>` from `POST /oauth/token` with client credentials. The connected client `tessie-connector-app` (account `acct-dana-whitfield`) is granted `vehicle_device_data`, `vehicle_location`, `vehicle_cmds`, `vehicle_charging_cmds`; a token requested without `scope` carries `vehicle_device_data`, `vehicle_location`. A request without a live token answers `401 invalid_token`, and a live token without the route's scope answers `403 insufficient_scope`.

## Endpoints

Each row is one request the generator sent. **Status** is the answer to the request as shown, sent with a token carrying every granted scope. **No token** is the same request with no `Authorization` header, and **Scope removed** the same request with a token carrying every granted scope except the route's own. The shared `/audit` and `/admin` planes every mock serves are described in `environment/API_DOCUMENTATION.md` and not listed.

| Method | Path | Scope | Request sent | Status | No token | Scope removed |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/oauth/token` | client credentials | `/oauth/token (form body)` | 200 | - | - |
| GET | `/health` | none | `/health` | 200 | - | - |
| GET | `/oauth/tokeninfo` | any live token | `/oauth/tokeninfo` | 200 | 401 | - |
| GET | `/vehicles` | `vehicle_device_data` | `/vehicles` | 200 | 401 | 403 |
| GET | `/vehicles` | `vehicle_device_data` | `/vehicles?only_active=true` | 200 | 401 | 403 |
| GET | `/{vin}/state` | `vehicle_device_data` | `/<Wren's VIN>/state` | 200 | 401 | 403 |
| GET | `/{vin}/battery` | `vehicle_device_data` | `/<Wren's VIN>/battery` | 200 | 401 | 403 |
| GET | `/{vin}/location` | `vehicle_location` | `/<Moss's VIN>/location` | 200 | 401 | 403 |
| GET | `/{vin}/drives` | `vehicle_location` | `/<Wren's VIN>/drives?from=1788238800&to=1790830799&tag=Business&driver_profile=Dana&minimum_distance=1&limit=20` | 200 | 401 | 403 |
| POST | `/{vin}/command/lock` | `vehicle_cmds` | `/<Moss's VIN>/command/lock` | 200 | 401 | 403 |
| POST | `/{vin}/command/unlock` | `vehicle_cmds` | `/<Moss's VIN>/command/unlock` | 200 | 401 | 403 |
| POST | `/{vin}/command/start_climate` | `vehicle_cmds` | `/<Wren's VIN>/command/start_climate` | 200 | 401 | 403 |
| POST | `/{vin}/command/stop_climate` | `vehicle_cmds` | `/<Wren's VIN>/command/stop_climate` | 200 | 401 | 403 |
| POST | `/{vin}/command/start_charging` | `vehicle_charging_cmds` | `/<Moss's VIN>/command/start_charging` | 200 | 401 | 403 |
| POST | `/{vin}/command/stop_charging` | `vehicle_charging_cmds` | `/<Moss's VIN>/command/stop_charging` | 200 | 401 | 403 |

## Seed files

| File | Records |
| --- | --- |
| `drives.json` | 272 |
| `vehicles.json` | 3 |
<!-- api-test-results:end -->

## Connector operations covered

List vehicles (`GET /vehicles`), get a vehicle's state (`GET /{vin}/state`), get battery and charging status (`GET /{vin}/battery`), get its location (`GET /{vin}/location`), lock and unlock (`POST /{vin}/command/lock`, `/unlock`), start and stop climate (`POST /{vin}/command/start_climate`, `/stop_climate`), start and stop charging (`POST /{vin}/command/start_charging`, `/stop_charging`), and list past drives (`GET /{vin}/drives`). Nothing else is served.

## API shape

The routes follow Tessie's published REST API. A Tessie token carries no per-operation scopes, so the scope names are the Tesla Fleet API's (`vehicle_device_data`, `vehicle_location`, `vehicle_cmds`, `vehicle_charging_cmds`), and a state read without `vehicle_location` leaves out the car's coordinates, as the Fleet API does. The battery route's `charge_state` block is this mock's addition to Tessie's battery fields.

## Mock simplifications

- Errors use `{"error"}`: `404` for a VIN the connected account does not hold, `409` for a command to a vehicle that is no longer active, `400` for a bad value, a request body on a command, or a query parameter the operation does not take (Tessie's `retry_duration`, `wait_for_completion`, `use_cache`, and the drives route's unit, time zone and geofence parameters among them).
- The vehicle list returns each vehicle with `is_active`, `last_drive_created_at` and its `last_state`; `only_active=true` leaves out inactive vehicles.
- A command answers `{"result": true, "woke": ...}`; `woke` is true when the car was asleep, and the car is online afterwards. Lock and unlock set `vehicle_state.locked`; climate sets `climate_state.is_climate_on`, `is_auto_conditioning_on` and `is_preconditioning`; charging sets `charge_state.charging_state` (`Charging` or `Stopped`) with the charger's power, current, rate and time to the charge limit. A command the car declines answers `200` with `"result": false` and a reason: `disconnected` (no cable), `complete` (at the charge limit), `is_charging`, or `not_charging`.
- Drives list newest first: `from` and `to` (Unix seconds, on the drive's start), `tag`, `driver_profile` (both case-insensitive), `minimum_distance` (miles) filter, and `limit` caps. Distances are in miles and temperatures in degrees Celsius.
- The battery level does not move while a car charges, and there are no charge limit, temperature, seat, sentry, trunk or window commands, no charging sessions, idles, historical states, or wake command.

## Seed data

- Connected account `acct-dana-whitfield`: Dana Whitfield's Tessie account, with the household's cars at Larkmoor House (whose garage door and presence history home-assistant-api also shows).
- 3 vehicles: Wren, Dana's 2024 Model Y Long Range (owner; at home, online, locked, charged to its 80 percent limit overnight, `Complete`); Moss, Jordan Ellis's 2021 Model 3 Long Range (driver access; in the driveway, asleep, unlocked, plugged in and `Stopped` at 49 percent); and Pebble, a 2019 Model 3 traded in on March 16, 2024 and no longer active.
- 272 drives from August 1 to October 4, 2026: 162 in Wren (1,610 miles) and 110 in Moss (344 miles), mostly Dana's commute between Home and the Studio and Jordan's to Jordan's office. 19 of Wren's drives are tagged `Business`: the client sites of the meetings granola-api records (Calloway & Finch on August 18, Lumen Coworking on August 20, the two Bluebird lobbies on August 27, North Branch Millwork on September 22, Brightwell River North on September 23, Midway Credit Union on September 24, Harbor Street Cafe on September 28, October 1 and October 3). The two drives to Brightwell for the lounge panel mockup on September 15 are not tagged. Jordan drove Wren on August 22, and Dana drove Wren to Lake Geneva and back on Sunday, October 4. All addresses are invented.
- 1 OAuth client `tessie-connector-app`: all four scopes granted; a token requested without `scope` carries `vehicle_device_data` and `vehicle_location`.
