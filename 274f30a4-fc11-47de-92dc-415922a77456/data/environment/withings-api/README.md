# withings-api

This API runs only inside the umbrella mock_stack container.

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir withings-api --port 8135
```

## API shape

The routes follow the Withings public API's action-style requests (`wbsapi.withings.net`): each webservice is one `POST` whose `application/x-www-form-urlencoded` form fields carry `action` and that action's parameters, and every answer is `{"status", "body"}`. `/measure` takes `action=getmeas`, `/v2/measure` `action=getactivity`, `/v2/sleep` `action=getsummary` and `/v2/user` `action=getdevice`. The scopes are Withings' own OAuth scopes (`user.metrics`, `user.activity`, `user.info`). As Withings does, an error answers HTTP 200 with a nonzero `status` (`503` for invalid parameters, `2554` for a wrong action or webservice) and an `error` message; only the shared token checks answer `401` and `403`. A query parameter, a form field the action does not take, or a JSON body is refused rather than ignored. Page sizes are fixed by this mock (100 measure groups, 50 activity days, 50 nights), and `offset` pages.
