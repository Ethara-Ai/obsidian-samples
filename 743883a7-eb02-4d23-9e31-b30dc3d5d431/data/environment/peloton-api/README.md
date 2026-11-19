# peloton-api

This API runs only inside the umbrella mock_stack container.

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir peloton-api --port 8134
```

## API shape

Peloton publishes no official public API. The routes here follow the member API that Peloton's own apps call and that open-source clients document (`/api/me`, `/api/user/{user_id}/workouts`, `/api/workout/{workout_id}`, `/api/workout/{workout_id}/performance_graph` and `/api/v2/ride/archived`), so they are modelled on an unpublished interface rather than copied from a vendor reference. The workout list's `start_date` and `end_date` filters are this mock's own addition to Peloton's `limit`, `page` and `joins`, the scopes (`profile.read`, `workouts.read`, `classes.read`) stand in for Peloton's session login, and the `error_code` values in the `{"status", "error_code", "subcode", "message", "details"}` error body are this mock's own. The performance graph's per-sample values are synthesized from each workout's stored summary, the same samples every time.
