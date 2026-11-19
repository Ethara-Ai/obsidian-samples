<!-- api-test-results:begin -->
# Ring API (Mock) - Test Results

GENERATED SECTION. DO NOT HAND-EDIT. `python3 script/gen_api_test_results.py --only ring-api` writes everything between the api-test-results markers by sending the requests below to the service in-process; the text after the end marker is kept as written.

Base URL: `http://localhost:8132` (docker-compose: `http://ring-api:8132`)

## Authentication

Every operation needs `Authorization: Bearer <token>` from `POST /oauth/token` with client credentials. The connected client `ring-connector-app` (account `acct-dana-whitfield`) is granted `devices.read`, `history.read`, `alarm.control`; a token requested without `scope` carries `devices.read`, `history.read`. A request without a live token answers `401 invalid_token`, and a live token without the route's scope answers `403 insufficient_scope`.

## Endpoints

Each row is one request the generator sent. **Status** is the answer to the request as shown, sent with a token carrying every granted scope. **No token** is the same request with no `Authorization` header, and **Scope removed** the same request with a token carrying every granted scope except the route's own. The shared `/audit` and `/admin` planes every mock serves are described in `environment/API_DOCUMENTATION.md` and not listed.

| Method | Path | Scope | Request sent | Status | No token | Scope removed |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/oauth/token` | client credentials | `/oauth/token (form body)` | 200 | - | - |
| GET | `/health` | none | `/health` | 200 | - | - |
| GET | `/oauth/tokeninfo` | any live token | `/oauth/tokeninfo` | 200 | 401 | - |
| GET | `/clients_api/ring_devices` | `devices.read` | `/clients_api/ring_devices` | 200 | 401 | 403 |
| GET | `/clients_api/doorbots/{device_id}/health` | `devices.read` | `/clients_api/doorbots/<Front Door doorbot id>/health` | 200 | 401 | 403 |
| GET | `/clients_api/doorbots/{device_id}/history` | `history.read` | `/clients_api/doorbots/<Front Door doorbot id>/history?kind=ding&since=2026-09-28&until=2026-10-04&limit=5` | 200 | 401 | 403 |
| GET | `/clients_api/doorbots/{device_id}/history` | `history.read` | `/clients_api/doorbots/<Front Door doorbot id>/history?limit=5&older_than=<oldest event id on the page>` | 200 | 401 | 403 |
| GET | `/clients_api/dings/{ding_id}/recording` | `history.read` | `/clients_api/dings/<ding id>/recording` | 200 | 401 | 403 |
| PUT | `/api/v1/mode/location/{location_id}` | `alarm.control` | `/api/v1/mode/location/<location id> (JSON body)` | 200 | 401 | 403 |

## Seed files

| File | Records |
| --- | --- |
| `devices.json` | 12 |
| `events.json` | 280 |
| `locations.json` | 1 |
<!-- api-test-results:end -->

## Connector operations covered

List devices (`GET /clients_api/ring_devices`), get a device's health (`GET /clients_api/doorbots/{device_id}/health`), list a device's event history with a date filter (`GET /clients_api/doorbots/{device_id}/history`), get a recording's details (`GET /clients_api/dings/{ding_id}/recording`), and set the alarm mode (`PUT /api/v1/mode/location/{location_id}`). Nothing else is served.

## API shape

Ring publishes no official public API. The routes follow the client API Ring's apps call and open-source clients document, so they are modelled on an unpublished interface, not copied from a vendor reference. The recording route answers with a JSON description of the recording rather than redirecting to the video, the history filters `since`, `until` and `kind` are this mock's additions to Ring's `limit` and `older_than`, and the scope names and the `{"error"}` body are this mock's own.

## Mock simplifications

- Errors use `{"error"}`: `404` for a device, ding or location the connected account does not own (health and history serve cameras and doorbells only), `400` for a bad value, an unknown body field, or a query parameter the operation does not take.
- The device list groups devices as Ring does (`doorbots`, `stickup_cams` with the floodlight camera, `chimes`, `base_stations`, and the alarm's contact sensors, motion detectors and keypad under `other`). The base station carries the location's alarm mode (`alarm.mode`, `updated_at`, `updated_by`), which is how a mode change reads back.
- Health reports Wi-Fi signal (with Ring's categories), battery level and category, power, packet loss and link rates for a camera or doorbell.
- History lists a device's events newest first: `kind` (`ding`, `motion`, `on_demand`), `since` and `until` (a local date, inclusive, or an ISO 8601 instant) filter, `limit` (1 to 100, default 20) caps, and `older_than` (an event id) pages back. Each event names its recording status, duration and person detection.
- A recording's details give its device, kind, time, duration, size and status; a ready recording has a download URL that expires 60 days after the event, the plan's retention.
- The alarm mode is `home`, `away` or `disarmed`. No video download, live view, siren, floodlight or chime control, device settings, or event stream.

## Seed data

- Connected account `acct-dana-whitfield`: the Ring location at Dana Whitfield's home, Larkmoor House, on Ring Protect Plus, whose doorbell, cameras and alarm home-assistant-api also shows.
- 12 devices: the Front Door video doorbell, the Backyard floodlight camera, Garage and Side Gate battery cameras (the Garage camera's battery at 38 percent and its Wi-Fi signal poor), a chime, the alarm base station (disarmed) and six alarm sensors and keypad.
- 280 events from September 5 to October 5, 2026: deliveries and visitors ringing the front door, motion on the walk, raccoons in the backyard at night, a few live views, and a person at the side gate at 2:41 on October 3 whom the garage camera caught 37 seconds later.
- 1 OAuth client `ring-connector-app`: `devices.read`, `history.read` and `alarm.control` granted; a token requested without `scope` carries the two read scopes.
