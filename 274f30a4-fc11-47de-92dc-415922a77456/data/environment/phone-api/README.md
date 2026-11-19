# phone-api

This API runs only inside the umbrella mock_stack container.

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir phone-api --port 8129
```

## Operation set and API shape

The client's connector list names a Phone connector without describing it, so the operation set here is an assumption: list recent calls, list text conversations, list the messages in a conversation, send a text message, and place a call, which records an outgoing call because a mock cannot connect one. No vendor publishes this API, so the routes (`/v1/calls`, `/v1/conversations`, `/v1/messages`), fields, scopes (`calls.read`, `calls.write`, `messages.read`, `messages.send`) and error body (`{"error": {"code", "message", "param"}}`) are a plain REST shape of this mock's own.
