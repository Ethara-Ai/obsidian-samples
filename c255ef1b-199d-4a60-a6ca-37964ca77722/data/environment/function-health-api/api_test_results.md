<!-- api-test-results:begin -->
# Function Health API (Mock) - Test Results

GENERATED SECTION. DO NOT HAND-EDIT. `python3 script/gen_api_test_results.py --only function-health-api` writes everything between the api-test-results markers by sending the requests below to the service in-process; the text after the end marker is kept as written.

Base URL: `http://localhost:8136` (docker-compose: `http://function-health-api:8136`)

## Authentication

Every operation needs `Authorization: Bearer <token>` from `POST /oauth/token` with client credentials. The connected client `function-health-connector-app` (account `acct-dana-whitfield`) is granted `visits.read`, `results.read`, `recommendations.read`; a token requested without `scope` carries `visits.read`, `results.read`, `recommendations.read`. A request without a live token answers `401 invalid_token`, and a live token without the route's scope answers `403 insufficient_scope`.

## Endpoints

Each row is one request the generator sent. **Status** is the answer to the request as shown, sent with a token carrying every granted scope. **No token** is the same request with no `Authorization` header, and **Scope removed** the same request with a token carrying every granted scope except the route's own. The shared `/audit` and `/admin` planes every mock serves are described in `environment/API_DOCUMENTATION.md` and not listed.

| Method | Path | Scope | Request sent | Status | No token | Scope removed |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/oauth/token` | client credentials | `/oauth/token (form body)` | 200 | - | - |
| GET | `/health` | none | `/health` | 200 | - | - |
| GET | `/oauth/tokeninfo` | any live token | `/oauth/tokeninfo` | 200 | 401 | - |
| GET | `/v1/visits` | `visits.read` | `/v1/visits` | 200 | 401 | 403 |
| GET | `/v1/visits` | `visits.read` | `/v1/visits?status=completed&limit=2` | 200 | 401 | 403 |
| GET | `/v1/visits/{visit_id}/results` | `results.read` | `/v1/visits/<latest completed visit id>/results?status=out_of_range` | 200 | 401 | 403 |
| GET | `/v1/visits/{visit_id}/results` | `results.read` | `/v1/visits/<latest completed visit id>/results?category=Heart&limit=3` | 200 | 401 | 403 |
| GET | `/v1/visits/{visit_id}/results` | `results.read` | `/v1/visits/<latest completed visit id>/results?category=Heart&limit=3&cursor=<next cursor>` | 200 | 401 | 403 |
| GET | `/v1/biomarkers/{biomarker_id}/history` | `results.read` | `/v1/biomarkers/ldl-cholesterol/history?start_date=2025-01-01&end_date=2026-10-05` | 200 | 401 | 403 |
| GET | `/v1/recommendations` | `recommendations.read` | `/v1/recommendations?status=active` | 200 | 401 | 403 |
| GET | `/v1/recommendations` | `recommendations.read` | `/v1/recommendations?visit_id=<latest completed visit id>&category=follow_up` | 200 | 401 | 403 |

## Seed files

| File | Records |
| --- | --- |
| `biomarkers.json` | 67 |
| `recommendations.json` | 18 |
| `results.json` | 195 |
| `visits.json` | 5 |
<!-- api-test-results:end -->

## Connector operations covered

List lab visits (`GET /v1/visits`), list a visit's biomarker results with in-range and out-of-range status (`GET /v1/visits/{visit_id}/results`), get one biomarker's history over time (`GET /v1/biomarkers/{biomarker_id}/history`), and list recommendations (`GET /v1/recommendations`). Nothing else is served, and nothing is written.

## API shape

Function Health publishes no public API, so this shape is the mock's own: plain REST under `/v1`, cursor paging, `{"error": {"code", "message", "param"}}` errors and its own scope names. It is not modelled on a vendor reference.

## Mock simplifications

- Errors: `404` `not_found` for a visit or biomarker the member does not have, `409` `results_not_ready` for the results of a visit that is still scheduled, `400` `invalid_parameter` for a bad value or a query parameter the operation does not take; `param` names the parameter.
- Visits list newest first and take `status` (`completed`, `scheduled`), `limit` (1 to 50, default 20) and `cursor` (the `next_cursor` of the page before).
- A visit's results list by category and name and take `status` (`in_range`, `out_of_range`), `category` (Heart, Metabolic, Kidney, Liver, Thyroid, Nutrients, Blood, Electrolytes, Hormones, Immune, Pancreas, Toxins, Urine), `limit` (1 to 200, default 100) and `cursor`. Each result gives the value (or `value_text` for a qualitative result such as Negative), unit, reference range, `status`, and `flag` (`high` or `low`) when out of range.
- A biomarker's history (biomarker ids are slugs such as `ldl-cholesterol` or `vitamin-d`, named on every result) lists the member's results oldest first, with the latest and the change from the one before; `start_date` and `end_date` (inclusive) filter by collection date.
- Recommendations list newest first and take `category` (nutrition, supplements, exercise, sleep, lifestyle, follow_up), `visit_id` and `status` (`active`, `completed`).
- No booking, clinician notes, optimal ranges, biological age, or uploads of outside results.

## Seed data

- Connected account `acct-dana-whitfield`: Dana Whitfield's Function Health membership. All results are invented.
- 5 visits: initial testing on April 22, 2025 (67 biomarkers, 9 out of range: LDL, ApoB, total cholesterol, vitamin D, ferritin, iron saturation, hemoglobin, MCV and the omega-3 index), a mid-year retest on October 21, 2025 (30 biomarkers, 4 out of range), the annual retest on April 14, 2026 (67, 3 out of range: LDL, ApoB and mercury), an at-home mid-year retest at 6:52 on September 8, 2026 (31, 2 out of range: LDL at 109 mg/dL and morning cortisol at 21.4 ug/dL), and the next annual retest scheduled for April 13, 2027. The September draw falls on a morning with no Peloton workout and no drive in peloton-api and tessie-api.
- 195 results across 67 biomarkers in 13 categories: LDL falling from 132 to 109 mg/dL, ApoB back in range at 86, vitamin D and iron recovering after the first visit, and mercury above range in April 2026 and back in range in September.
- 18 recommendations: 9 completed and 9 active, each tied to its visit and biomarkers.
- 1 OAuth client `function-health-connector-app`: `visits.read`, `results.read` and `recommendations.read`, all carried by a token requested without `scope`.
