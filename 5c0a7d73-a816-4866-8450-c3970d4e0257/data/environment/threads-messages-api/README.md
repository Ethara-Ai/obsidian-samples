# threads-messages-api

This API runs only inside the umbrella mock_stack container.

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir threads-messages-api --port 8128
```

## API shape

Meta publishes no messaging endpoint in the Threads API that this mock could copy, so, as the client asked, it mirrors `instagram-messages-api`: the same Graph messaging shape (`GET /v1.0/me/conversations`, `GET /v1.0/{conversation_id}/messages`, `POST /v1.0/me/messages`) and Graph error envelope, on the Threads Graph version prefix `v1.0`. The scope names (`threads_messages.read`, `threads_messages.send`) are this mock's own, following that service's.
