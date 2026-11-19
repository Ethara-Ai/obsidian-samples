# healthex-api

This API runs only inside the umbrella mock_stack container.

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir healthex-api --port 8137
```

## API shape

This mock is a FHIR R4-style patient records API modelled on what a health records aggregator serves, not copied from a published HealthEx API. Records are FHIR resources under `/fhir/R4`: `Condition` (conditions), `MedicationRequest` (medications), `Observation` (lab results), `Immunization` and `Encounter` (visits). Searching a type (`GET /fhir/R4/{type}`) answers a `searchset` `Bundle` of the connected patient's records, and reading one (`GET /fhir/R4/{type}/{id}`) answers the resource. A search takes `date` (FHIR prefixes `eq`, `gt`, `lt`, `ge`, `le` on `YYYY`, `YYYY-MM` or `YYYY-MM-DD`; repeat it for a range), `provider` (an organization or practitioner id, reference or name, this mock's own parameter), `_count` and `_offset`; any other search parameter is refused rather than ignored. Errors are FHIR `OperationOutcome`s. The scopes are SMART-style patient scopes (`patient/Condition.read` and so on). Codes are standard (SNOMED CT and ICD-10-CM for conditions, LOINC for lab results, CVX for vaccines); medications carry text only. All patient data, clinics and clinicians are invented.
