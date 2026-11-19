# home-assistant-api

This API runs only inside the umbrella mock_stack container.

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir home-assistant-api --port 8130
```

## Scopes

Home Assistant's long-lived access tokens carry no scopes, so the two scopes here (`homeassistant:read` for the configuration, states and history, `homeassistant:control` for service calls) are this mock's own, keeping reading the house apart from changing it. The routes, bodies and error messages follow the Home Assistant REST API.
