<!-- api-test-results:begin -->
# Google Tasks API (Mock) - Test Results

GENERATED SECTION. DO NOT HAND-EDIT. `python3 script/gen_api_test_results.py --only google-tasks-api` writes everything between the api-test-results markers by sending the requests below to the service in-process; the text after the end marker is kept as written.

Base URL: `http://localhost:8119` (docker-compose: `http://google-tasks-api:8119`)

## Authentication

Every operation needs `Authorization: Bearer <token>` from `POST /oauth/token` with client credentials. The connected client `gtasks-connector-app` (account `acct-dana-whitfield`) is granted `tasks.readonly`, `tasks`; a token requested without `scope` carries `tasks.readonly`. A request without a live token answers `401 invalid_token`, and a live token without the route's scope answers `403 insufficient_scope`.

## Endpoints

Each row is one request the generator sent. **Status** is the answer to the request as shown, sent with a token carrying every granted scope. **No token** is the same request with no `Authorization` header, and **Scope removed** the same request with a token carrying every granted scope except the route's own. The shared `/audit` and `/admin` planes every mock serves are described in `environment/API_DOCUMENTATION.md` and not listed.

| Method | Path | Scope | Request sent | Status | No token | Scope removed |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/oauth/token` | client credentials | `/oauth/token (form body)` | 200 | - | - |
| GET | `/health` | none | `/health` | 200 | - | - |
| GET | `/oauth/tokeninfo` | any live token | `/oauth/tokeninfo` | 200 | 401 | - |
| GET | `/tasks/v1/users/@me/lists` | `tasks.readonly` or `tasks` | `/tasks/v1/users/@me/lists` | 200 | 401 | - |
| GET | `/tasks/v1/lists/{tasklist}/tasks` | `tasks.readonly` or `tasks` | `/tasks/v1/lists/<Brightwell Lobby list id>/tasks?showCompleted=false&dueMin=2026-10-19T00:00:00Z&dueMax=2026-10-31T00:00:00Z` | 200 | 401 | - |
| GET | `/tasks/v1/lists/{tasklist}/tasks` | `tasks.readonly` or `tasks` | `/tasks/v1/lists/@default/tasks?maxResults=5` | 200 | 401 | - |
| POST | `/tasks/v1/lists/{tasklist}/tasks` | `tasks` | `/tasks/v1/lists/<Brightwell Lobby list id>/tasks (JSON body)` | 200 | 401 | 403 |
| POST | `/tasks/v1/lists/{tasklist}/tasks` | `tasks` | `/tasks/v1/lists/<Brightwell Lobby list id>/tasks?parent=<new task id> (JSON body)` | 200 | 401 | 403 |
| GET | `/tasks/v1/lists/{tasklist}/tasks/{task}` | `tasks.readonly` or `tasks` | `/tasks/v1/lists/<Brightwell Lobby list id>/tasks/<new task id>` | 200 | 401 | - |
| PATCH | `/tasks/v1/lists/{tasklist}/tasks/{task}` | `tasks` | `/tasks/v1/lists/<Brightwell Lobby list id>/tasks/<new task id> (JSON body)` | 200 | 401 | 403 |
| PUT | `/tasks/v1/lists/{tasklist}/tasks/{task}` | `tasks` | `/tasks/v1/lists/<Brightwell Lobby list id>/tasks/<new task id> (JSON body)` | 200 | 401 | 403 |
| DELETE | `/tasks/v1/lists/{tasklist}/tasks/{task}` | `tasks` | `/tasks/v1/lists/<Brightwell Lobby list id>/tasks/<new task id>` | 204 | 401 | 403 |

## Seed files

| File | Records |
| --- | --- |
| `tasklists.json` | 6 |
| `tasks.json` | 157 |
<!-- api-test-results:end -->

## Connector operations covered

List task lists (`GET /tasks/v1/users/@me/lists`), list the tasks in a list (`GET /tasks/v1/lists/{tasklist}/tasks`), get a task (`GET /tasks/v1/lists/{tasklist}/tasks/{task}`), create a task (`POST /tasks/v1/lists/{tasklist}/tasks`), update a task with `tasks.update` (`PUT`, replaces the task) or `tasks.patch` (`PATCH`, changes the fields sent), either of which marks it complete with `"status": "completed"`, and delete a task (`DELETE /tasks/v1/lists/{tasklist}/tasks/{task}`). Nothing else is served.

## Mock simplifications

- `@default` names the first task list. There are no task list writes, no `tasks.move` or `tasks.clear`, no tasks assigned from Docs or Chat, and `links` is always empty.
- A due date keeps only its date and is served at midnight UTC, as on Google. Setting `status` to `completed` stamps `completed` with the current time unless the request gives one; setting it back to `needsAction` clears `completed` and unhides the task.
- Deleting a task marks it `deleted` (and its subtasks with it); it leaves the default listing, `showDeleted=true` lists it, and getting it by id still answers it with `deleted: true`.
- Listing returns each top-level task in position order followed by its subtasks. `showCompleted` (default true), `showDeleted` and `showHidden` (default false), `completedMin`/`completedMax`, `dueMin`/`dueMax` (each upper bound exclusive) and `updatedMin` filter, and `maxResults` (default 20, at most 100) with `pageToken` pages. A new task goes first among its siblings unless `previous` names the sibling to follow; `parent` makes it a subtask, one level deep.
- `tasks.update` needs the task's title because it replaces the task; fields it omits are cleared. Output-only fields read back (`kind`, `etag`, `selfLink`, `position`, `updated`, `links`, `webViewLink`) are accepted and ignored; any other field is a 400. A query parameter the method does not take is a 400.

## Seed data

- Connected account `acct-dana-whitfield` (Dana Whitfield, Lakeshore Design Studio, Chicago), the same account google-drive-api, google-docs-api and google-sheets-api serve
- 6 task lists (`My Tasks`, `Brightwell Lobby`, `Studio Admin`, `Events`, `Personal`, `Reading`) with 157 tasks and subtasks, as of October 2, 2026: 65 completed (4 of them cleared and hidden) and one deleted
- Dates agree with the other Lakeshore seeds: the River North install from October 19 to 30 and the punch list walkthrough with Monica Reyes, material selections locking September 30, the Lakefront concept vote closing September 19, the studio coordinator hire, the payroll cutoffs, the workshop on November 7 and the holiday party on December 11; some tasks due before October 2 are still open
- 1 OAuth client `gtasks-connector-app`: both scopes granted; a token requested without `scope` carries only `tasks.readonly`
