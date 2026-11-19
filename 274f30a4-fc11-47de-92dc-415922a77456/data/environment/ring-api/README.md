# ring-api

This API runs only inside the umbrella mock_stack container.

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir ring-api --port 8132
```

## API shape

Ring publishes no official public API. The routes here follow the client API that Ring's own apps call and that open-source clients document (`/clients_api/ring_devices`, `/clients_api/doorbots/{id}/health`, `/clients_api/doorbots/{id}/history`, and the location-mode route `/api/v1/mode/location/{location_id}` for the alarm), so they are modelled on an unpublished interface rather than copied from a vendor reference. The recording details route (`/clients_api/dings/{ding_id}/recording`, which in Ring's apps redirects to the video) answers with a JSON description of the recording instead, the history `since`, `until` and `kind` filters are this mock's own additions to `limit` and `older_than`, and the scopes (`devices.read`, `history.read`, `alarm.control`) and `{"error"}` body are this mock's own.
