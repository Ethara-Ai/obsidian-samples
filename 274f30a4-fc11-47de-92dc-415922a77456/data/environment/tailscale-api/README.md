# tailscale-api

This API runs only inside the umbrella mock_stack container.

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir tailscale-api --port 8127
```

## Operations

The connector's six operations follow the Tailscale API v2: list the tailnet's devices, get a device, authorize a device, remove a device, read the access policy, and create an auth key. Tailscale's get-key route (`GET /api/v2/tailnet/{tailnet}/keys/{keyId}`) is served as well, as the read that shows a key the create operation made, since the operation list names no other way to read one back; it never returns the key's secret.
