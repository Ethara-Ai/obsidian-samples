# function-health-api

This API runs only inside the umbrella mock_stack container.

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir function-health-api --port 8136
```

## API shape

Function Health publishes no public API, so this mock uses a plain REST shape of its own, not modelled on any vendor reference: `GET /v1/visits`, `GET /v1/visits/{visit_id}/results`, `GET /v1/biomarkers/{biomarker_id}/history` and `GET /v1/recommendations`, cursor paging (`limit`, `cursor`, `next_cursor`), errors as `{"error": {"code", "message", "param"}}`, and this mock's own scopes (`visits.read`, `results.read`, `recommendations.read`). A result's status is `in_range` or `out_of_range` against the reference range the result carries, with `flag` `high` or `low` when it is out of range. All member data is invented.
