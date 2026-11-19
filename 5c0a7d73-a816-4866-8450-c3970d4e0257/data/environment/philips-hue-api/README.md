# philips-hue-api

This API runs only inside the umbrella mock_stack container.

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir philips-hue-api --port 8131
```

## Authentication

The Hue bridge's CLIP API v2 authenticates with a `hue-application-key` header and has no scopes. Like the fleet's other connectors, this mock uses a bearer token from `POST /oauth/token` instead, with two scopes of its own: `hue.read` for lights, rooms and scenes, and `hue.control` for changing a light or recalling a scene. Routes, bodies and the error envelope follow CLIP v2.
