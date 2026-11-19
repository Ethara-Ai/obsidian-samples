<!-- api-test-results:begin -->
# HealthEx API (Mock) - Test Results

GENERATED SECTION. DO NOT HAND-EDIT. `python3 script/gen_api_test_results.py --only healthex-api` writes everything between the api-test-results markers by sending the requests below to the service in-process; the text after the end marker is kept as written.

Base URL: `http://localhost:8137` (docker-compose: `http://healthex-api:8137`)

## Authentication

Every operation needs `Authorization: Bearer <token>` from `POST /oauth/token` with client credentials. The connected client `healthex-connector-app` (account `acct-dana-whitfield`) is granted `patient/Condition.read`, `patient/MedicationRequest.read`, `patient/Observation.read`, `patient/Immunization.read`, `patient/Encounter.read`; a token requested without `scope` carries `patient/Condition.read`, `patient/MedicationRequest.read`, `patient/Observation.read`, `patient/Immunization.read`, `patient/Encounter.read`. A request without a live token answers `401 invalid_token`, and a live token without the route's scope answers `403 insufficient_scope`.

## Endpoints

Each row is one request the generator sent. **Status** is the answer to the request as shown, sent with a token carrying every granted scope. **No token** is the same request with no `Authorization` header, and **Scope removed** the same request with a token carrying every granted scope except the route's own. The shared `/audit` and `/admin` planes every mock serves are described in `environment/API_DOCUMENTATION.md` and not listed.

| Method | Path | Scope | Request sent | Status | No token | Scope removed |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/oauth/token` | client credentials | `/oauth/token (form body)` | 200 | - | - |
| GET | `/health` | none | `/health` | 200 | - | - |
| GET | `/oauth/tokeninfo` | any live token | `/oauth/tokeninfo` | 200 | 401 | - |
| GET | `/fhir/R4/Condition` | `patient/Condition.read` | `/fhir/R4/Condition?_count=5` | 200 | 401 | 403 |
| GET | `/fhir/R4/Condition/{record_id}` | `patient/Condition.read` | `/fhir/R4/Condition/<newest Condition id>` | 200 | 401 | 403 |
| GET | `/fhir/R4/MedicationRequest` | `patient/MedicationRequest.read` | `/fhir/R4/MedicationRequest?_count=5` | 200 | 401 | 403 |
| GET | `/fhir/R4/MedicationRequest/{record_id}` | `patient/MedicationRequest.read` | `/fhir/R4/MedicationRequest/<newest MedicationRequest id>` | 200 | 401 | 403 |
| GET | `/fhir/R4/Observation` | `patient/Observation.read` | `/fhir/R4/Observation?_count=5` | 200 | 401 | 403 |
| GET | `/fhir/R4/Observation/{record_id}` | `patient/Observation.read` | `/fhir/R4/Observation/<newest Observation id>` | 200 | 401 | 403 |
| GET | `/fhir/R4/Immunization` | `patient/Immunization.read` | `/fhir/R4/Immunization?_count=5` | 200 | 401 | 403 |
| GET | `/fhir/R4/Immunization/{record_id}` | `patient/Immunization.read` | `/fhir/R4/Immunization/<newest Immunization id>` | 200 | 401 | 403 |
| GET | `/fhir/R4/Encounter` | `patient/Encounter.read` | `/fhir/R4/Encounter?_count=5` | 200 | 401 | 403 |
| GET | `/fhir/R4/Encounter/{record_id}` | `patient/Encounter.read` | `/fhir/R4/Encounter/<newest Encounter id>` | 200 | 401 | 403 |
| GET | `/fhir/R4/Observation` | `patient/Observation.read` | `/fhir/R4/Observation?date=ge2026-01-01&_count=10&_offset=10` | 200 | 401 | 403 |
| GET | `/fhir/R4/Encounter` | `patient/Encounter.read` | `/fhir/R4/Encounter?provider=Halsted Orthopedic Group` | 200 | 401 | 403 |
| GET | `/fhir/R4/MedicationRequest` | `patient/MedicationRequest.read` | `/fhir/R4/MedicationRequest?provider=prac-okonkwo&date=ge2025` | 200 | 401 | 403 |

## Seed files

| File | Records |
| --- | --- |
| `organizations.json` | 6 |
| `patients.json` | 1 |
| `practitioners.json` | 8 |
| `records.json` | 154 |
<!-- api-test-results:end -->

## Connector operations covered

List the patient's records by type, filtered by date and by provider (`GET /fhir/R4/Condition`, `/MedicationRequest`, `/Observation`, `/Immunization`, `/Encounter`), and get one record (`GET /fhir/R4/{type}/{id}` for each type). Nothing else is served, and nothing is written.

## API shape

A FHIR R4-style API modelled on what a health records aggregator serves, not copied from a published HealthEx API: searchset `Bundle`s, FHIR resources, `OperationOutcome` errors and SMART-style patient scopes. The `provider` search parameter is this mock's own.

## Mock simplifications

- Errors are `OperationOutcome`s: `404` `not-found` for a record that is not this patient's or a path the mock does not serve, `405` `not-supported` for anything but `GET`, `400` `invalid` for a bad value or a search parameter the operation does not take.
- A search returns the connected patient's records of that type, newest first, as a `searchset` `Bundle` with `total`, `self`, `next` and `previous` links, and `entry` items with `fullUrl` and `search.mode` `match`. It takes `date` (repeatable; prefixes `eq`, `gt`, `lt`, `ge`, `le` on `YYYY`, `YYYY-MM` or `YYYY-MM-DD`), `provider` (an organization or practitioner id such as `org-lakefront` or `prac-okonkwo`, a reference such as `Organization/org-lakefront`, or a name; a provider that matches nothing is a `400` naming the organizations), `_count` (1 to 100, default 20) and `_offset`.
- The date a search filters on is the condition's `recordedDate`, the medication's `authoredOn`, the lab result's `effectiveDateTime`, the vaccine's `occurrenceDateTime` and the visit's `period.start`.
- Lab results are `Observation`s with category `laboratory`, LOINC codes, a value, a reference range and an interpretation (`L`, `H`, `N`); conditions carry SNOMED CT and ICD-10-CM codes; vaccines CVX codes; medications text only.
- No Patient, Practitioner, Organization, DiagnosticReport, AllergyIntolerance or DocumentReference resources, no `_include`, `_sort` or chained search.

## Seed data

- Connected account `acct-dana-whitfield`: Dana Whitfield's records gathered from six invented sources (Lakefront Family Medicine, Linden Dermatology Associates, Sheridan Walk-In Clinic, Halsted Orthopedic Group, Clearview Eye Care and Ridgeline Pharmacy) and eight invented clinicians. All records are invented.
- 16 visits from May 2022 to July 2026: four annual physicals, the May 6, 2025 visit that reviewed the Function Health results of April 22, a November 2025 recheck, two skin checks, a sinus visit, a video visit for migraines, the December 13, 2025 urgent care visit for a right ankle sprain, an orthopedic follow-up and three physical therapy visits, and an eye exam.
- 7 conditions: seasonal allergic rhinitis, migraine without aura and hyperlipidemia (diagnosed April 28, 2026) active; acute sinusitis, iron deficiency anemia, vitamin D deficiency and the ankle sprain resolved.
- 7 medication requests: cetirizine, fluticasone, sumatriptan and vitamin D3 active; amoxicillin, ferrous sulfate and ibuprofen completed.
- 111 lab results: full panels at the 2022, 2023, 2024 and 2026 physicals (LDL 126, 129, 128 and 121 mg/dL, all high) and the iron and vitamin D checks of May and November 2025, which agree with function-health-api's results.
- 13 immunizations from 2021 to September 30, 2026, the last a flu shot at the pharmacy near the Studio at lunchtime, while tessie-api has the car parked at the Studio.
- 1 OAuth client `healthex-connector-app`: the five `patient/<type>.read` scopes, all carried by a token requested without `scope`.
