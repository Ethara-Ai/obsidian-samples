# tessie-api

This API runs only inside the umbrella mock_stack container.

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir tessie-api --port 8133
```

## API shape

The routes follow Tessie's published REST API (`api.tessie.com`): `GET /vehicles`, `GET /{vin}/state`, `GET /{vin}/battery`, `GET /{vin}/location`, `GET /{vin}/drives` and `POST /{vin}/command/{lock,unlock,start_climate,stop_climate,start_charging,stop_charging}`. Where this mock departs from Tessie, it says so here:

- Scopes. A Tessie access token carries no per-operation scopes, so this mock borrows the Tesla Fleet API scope names: `vehicle_device_data` (vehicle list, state, battery), `vehicle_location` (location and drives), `vehicle_cmds` (lock, unlock, climate) and `vehicle_charging_cmds` (start and stop charging). As in the Fleet API, a vehicle's state leaves out its coordinates unless the token also carries `vehicle_location`.
- The battery route adds a `charge_state` block (charging state, limit, power, time to full) to Tessie's battery fields, so one call answers both battery and charging status.
- A command answers `{"result": true, "woke": ...}`. When the car declines a command it answers `200` with `"result": false` and the Tesla reason (`disconnected`, `complete`, `is_charging`, `not_charging`). Commands take no body.
- Tessie's `retry_duration` and `wait_for_completion` (commands), `use_cache` (state), and the unit, time zone and geofence parameters of the drives route are not taken; a query parameter an operation does not take is a `400`. Drives come back in miles and degrees Celsius, Tessie's defaults.
- Errors use `{"error"}`.
