# granola-api

This API runs only inside the umbrella mock_stack container.

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir granola-api --port 8125
```

## API shape

Granola publishes no widely documented public REST API, so this mock does not copy one. It serves a plain REST shape of its own under `/v1`: `GET /v1/notes` lists meeting notes newest first with a `start_date` and `end_date` filter, `GET /v1/notes/{note_id}` returns one note with its summary, action items and transcript, and `GET /v1/notes/search?q=` searches titles, summaries, action items and transcripts. The route names, fields, scopes (`notes:read`, `notes:search`) and the error body (`{"error": {"code", "message", "param"}}`) are this mock's own.
