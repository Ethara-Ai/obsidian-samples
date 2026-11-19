<!-- api-test-results:begin -->
# Health Records API (Mock) - Test Results

GENERATED SECTION. DO NOT HAND-EDIT. `python3 script/gen_api_test_results.py --only health-api` writes everything between the api-test-results markers by sending the requests below to the service in-process; the text after the end marker is kept as written.

Base URL: `http://localhost:8104` (docker-compose: `http://health-api:8104`)

## Authentication

Every operation needs `Authorization: Bearer <token>` from `POST /oauth/token` with client credentials. The connected client `health-connector-app` (account `acct-marcus-hale`) is granted `health.measurements.read`, `health.nutrition.read`, `health.sleep.read`, `health.workouts.read`; a token requested without `scope` carries `health.measurements.read`. A request without a live token answers `401 invalid_token`, and a live token without the route's scope answers `403 insufficient_scope`.

## Endpoints

Each row is one request the generator sent. **Status** is the answer to the request as shown, sent with a token carrying every granted scope. **No token** is the same request with no `Authorization` header, and **Scope removed** the same request with a token carrying every granted scope except the route's own. The shared `/audit` and `/admin` planes every mock serves are described in `environment/API_DOCUMENTATION.md` and not listed.

| Method | Path | Scope | Request sent | Status | No token | Scope removed |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/oauth/token` | client credentials | `/oauth/token (form body)` | 200 | - | - |
| GET | `/health` | none | `/health` | 200 | - | - |
| GET | `/oauth/tokeninfo` | any live token | `/oauth/tokeninfo` | 200 | 401 | - |
| GET | `/v1/measurements` | `health.measurements.read` | `/v1/measurements?type=steps` | 200 | 401 | 403 |
| GET | `/v1/measurements` | `health.measurements.read` | `/v1/measurements?type=steps&start=2026-08-03&end=2026-09-27&aggregate=week` | 200 | 401 | 403 |
| GET | `/v1/measurements` | `health.measurements.read` | `/v1/measurements?type=blood_pressure&start=2026-09-01&end=2026-09-30` | 200 | 401 | 403 |
| GET | `/v1/nutrition` | `health.nutrition.read` | `/v1/nutrition?start=2026-09-01&end=2026-09-30&meal=dinner` | 200 | 401 | 403 |
| GET | `/v1/sleep` | `health.sleep.read` | `/v1/sleep?start=2026-09-24&end=2026-09-30` | 200 | 401 | 403 |
| GET | `/v1/workouts` | `health.workouts.read` | `/v1/workouts?start=2026-08-02&end=2026-09-30&type=running` | 200 | 401 | 403 |

## Seed files

| File | Records |
| --- | --- |
| `measurements.json` | 403 |
| `nutrition.json` | 115 |
| `people.json` | 1 |
| `sleep.json` | 60 |
| `workouts.json` | 26 |
<!-- api-test-results:end -->

## Connector operations covered

`.query` (`/v1/measurements`), `.nutrition`, `.sleep`, `.workouts`. All read-only; nothing else is served.

Query rules: `start`/`end` are inclusive `YYYY-MM-DD` dates; when omitted the window is the 7 days ending at the newest record of that kind. Sleep is selected by the wake date, workouts by the start date, nutrition by the logged date. `aggregate=day|week` on `/v1/measurements` sums additive types (steps, distance_km, active_energy_kcal) and averages the rest; the response states it as `aggregation` (`none`, `sum`, `mean`) next to `interval` (`none`, `day`, `week`). Weeks start on Monday and are keyed by that date. Nutrition responses carry `daily_totals`, the exact sum of the returned entries per day.

## Seed data

- 1 person (34-year-old training for a half marathon in Denver, CO), linked to connected account `acct-marcus-hale`
- 403 measurements over 2026-08-02 to 2026-09-30: daily steps, distance, active energy, resting heart rate and HRV (60 days each), nightly blood oxygen (60), weight and body fat twice a week (17 each), blood pressure weekly (9)
- 60 sleep sessions (one per wake date); light + deep + REM equals `duration_min`, plus awake equals `time_in_bed_min`
- 26 workouts (14 runs building to an 18.5 km long run, 4 strength, 3 cycling, 2 yoga, 2 walking, 1 swim)
- 115 nutrition entries over the last 30 days (3 to 5 per day); calories follow 4/4/9 kcal per gram of protein/carbs/fat
- 1 OAuth client `health-connector-app`: every scope granted; a token requested without `scope` carries only `health.measurements.read`
