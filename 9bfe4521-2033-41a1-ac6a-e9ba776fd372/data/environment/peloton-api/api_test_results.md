<!-- api-test-results:begin -->
# Peloton API (Mock) - Test Results

GENERATED SECTION. DO NOT HAND-EDIT. `python3 script/gen_api_test_results.py --only peloton-api` writes everything between the api-test-results markers by sending the requests below to the service in-process; the text after the end marker is kept as written.

Base URL: `http://localhost:8134` (docker-compose: `http://peloton-api:8134`)

## Authentication

Every operation needs `Authorization: Bearer <token>` from `POST /oauth/token` with client credentials. The connected client `peloton-connector-app` (account `acct-dana-whitfield`) is granted `profile.read`, `workouts.read`, `classes.read`; a token requested without `scope` carries `profile.read`, `workouts.read`, `classes.read`. A request without a live token answers `401 invalid_token`, and a live token without the route's scope answers `403 insufficient_scope`.

## Endpoints

Each row is one request the generator sent. **Status** is the answer to the request as shown, sent with a token carrying every granted scope. **No token** is the same request with no `Authorization` header, and **Scope removed** the same request with a token carrying every granted scope except the route's own. The shared `/audit` and `/admin` planes every mock serves are described in `environment/API_DOCUMENTATION.md` and not listed.

| Method | Path | Scope | Request sent | Status | No token | Scope removed |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/oauth/token` | client credentials | `/oauth/token (form body)` | 200 | - | - |
| GET | `/health` | none | `/health` | 200 | - | - |
| GET | `/oauth/tokeninfo` | any live token | `/oauth/tokeninfo` | 200 | 401 | - |
| GET | `/api/me` | `profile.read` | `/api/me` | 200 | 401 | 403 |
| GET | `/api/user/{user_id}/workouts` | `workouts.read` | `/api/user/<member id>/workouts?joins=ride,ride.instructor&limit=5` | 200 | 401 | 403 |
| GET | `/api/user/{user_id}/workouts` | `workouts.read` | `/api/user/<member id>/workouts?start_date=2026-09-28&end_date=2026-10-04&limit=50&page=0` | 200 | 401 | 403 |
| GET | `/api/workout/{workout_id}` | `workouts.read` | `/api/workout/<FTP test workout id>?joins=ride` | 200 | 401 | 403 |
| GET | `/api/workout/{workout_id}/performance_graph` | `workouts.read` | `/api/workout/<FTP test workout id>/performance_graph?every_n=30` | 200 | 401 | 403 |
| GET | `/api/v2/ride/archived` | `classes.read` | `/api/v2/ride/archived?browse_category=cycling&duration=1200,1800` | 200 | 401 | 403 |
| GET | `/api/v2/ride/archived` | `classes.read` | `/api/v2/ride/archived?instructor_id=<instructor id>&limit=5&page=1` | 200 | 401 | 403 |

## Seed files

| File | Records |
| --- | --- |
| `class_types.json` | 21 |
| `instructors.json` | 8 |
| `rides.json` | 187 |
| `users.json` | 1 |
| `workouts.json` | 133 |
<!-- api-test-results:end -->

## Connector operations covered

Get the profile (`GET /api/me`), list workouts with a date filter (`GET /api/user/{user_id}/workouts`), get one workout (`GET /api/workout/{workout_id}`), get a workout's performance summary (`GET /api/workout/{workout_id}/performance_graph`), and list available classes with discipline and duration filters (`GET /api/v2/ride/archived`). Nothing else is served, and nothing is written.

## API shape

Peloton publishes no official public API. The routes follow the member API Peloton's apps call and open-source clients document, so they are modelled on an unpublished interface, not copied from a vendor reference. The workout list's `start_date` and `end_date` are this mock's additions, the scope names stand in for Peloton's session login, and the `error_code` values are this mock's own.

## Mock simplifications

- Errors use `{"status", "error_code", "subcode", "message", "details"}`: `404` for a member or workout the connected account does not hold, `400` for a bad value or a query parameter the operation does not take (`sort_by` and `desc` among them); `details.param` names the parameter.
- The workout list is newest first and pages with `limit` (1 to 100, default 20) and `page` (from 0), answering `total`, `count`, `page_count`, `show_previous`, `show_next` and a per-discipline `summary` of every matching workout. `start_date` and `end_date` (dates in the member's time zone, America/Chicago, inclusive) filter on the start time. `joins=ride` adds the class and `joins=ride.instructor` the class with its instructor, on the list and on one workout.
- A workout gives its times (Unix seconds), discipline, `total_work` in joules, leaderboard rank, FTP in effect, personal-record flag and heart-rate zone durations with effort points.
- The performance graph gives the average and total summaries (output, cadence, resistance, speed, distance, calories) and per-sample series of output, cadence, resistance, speed and heart rate with its zones, one sample every `every_n` seconds (1 to 300, default 5). The samples are synthesized from the workout's stored averages and maxima, deterministically per workout; stretching and meditation have only calories.
- The class library lists newest first by air time and takes `browse_category` (cycling, strength, yoga, stretching, meditation, running, walking), `duration` (seconds; several separated by commas), `instructor_id`, `limit` (1 to 100, default 18) and `page`; each page names its instructors and class types.
- Read-only: no social, leaderboard, schedule, program, achievement or challenge routes.

## Seed data

- Connected account `acct-dana-whitfield`: Dana Whitfield's Peloton membership (username LarkmoorDana, Evanston, IL) on a Bike+, joined May 28, 2026; FTP 172 from the FTP test ride on July 14, and a 19-week weekly streak.
- 133 workouts from June 1 to October 5, 2026: 48 cycling, 23 meditation, 20 stretching, 18 strength, 17 yoga, 4 running and 3 walking, the last a 30-minute ride at 6:21 this morning. Workouts fall only when tessie-api's drive log has Dana at home: rides before the morning drive, strength and yoga in the evening.
- 187 classes aired April 2 to October 3, 2026 across seven disciplines, from 8 invented instructors, with 21 class types.
- 1 OAuth client `peloton-connector-app`: `profile.read`, `workouts.read` and `classes.read`, all carried by a token requested without `scope`.
