---
name: jira-api-connector
description: >
  Jira API (Mock) mock HTTP API. Base URL is provided via the
  `JIRA_API_URL` environment variable. 9 endpoint(s) across GET, POST, PUT.
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# Jira API (Mock)

Mock HTTP API. **All requests go to the base URL in `$JIRA_API_URL`.** Auth headers
are mocked (any token is accepted). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `JIRA_API_URL` | Base URL for all requests (e.g. `http://jira-api:8029`) |

## Endpoints

| Method | Path |
|--------|------|
| GET | `/rest/api/3/project` |
| POST | `/rest/api/3/issue` |
| GET | `/rest/api/3/issue/{issue_key}` |
| PUT | `/rest/api/3/issue/{issue_key}` |
| GET | `/rest/api/3/issue/{issue_key}/transitions` |
| POST | `/rest/api/3/issue/{issue_key}/transitions` |
| GET | `/rest/api/3/search` |
| GET | `/rest/agile/1.0/board` |
| GET | `/rest/agile/1.0/board/{board_id}/sprint` |

## Usage

```bash
# GET example
curl -s "$JIRA_API_URL/rest/api/3/project"
```

## Searching issues (`GET /rest/api/3/search`)

`jql` takes a small part of JQL. These clauses are applied, joined by `AND`:

- `project = <key>`
- `status = <name>`
- `sprint = <id or name>`
- `sprint in (<id or name>, ...)`

Put a value with spaces in quotes, e.g. `sprint = "ENG Sprint 22"`; an `AND` inside quotes is part of the
value. A trailing `ORDER BY ...` is accepted but not applied: issues come back in their stored order. Any
other clause, such as `assignee = ...`, `status != ...` or `sprint in openSprints()`, is not applied
either, so the answer can hold more issues than you asked for. `OR` is not supported.

In each issue's `fields`, `customfield_10020` is the sprint (a list with one
`{id, name, state, boardId, startDate, endDate, goal}`, or `null` when the issue is in no sprint) and
`customfield_10016` is the story points. `GET /rest/agile/1.0/board/{board_id}/sprint` lists a board's
sprint ids and names.

```bash
curl -s -G "$JIRA_API_URL/rest/api/3/search" --data-urlencode 'jql=project = ENG AND sprint = "ENG Sprint 22"'
```

## Paging

- `GET /rest/api/3/search` returns at most 50 by default (`maxResults`, up to 100); there is no next page, so ask for a larger `maxResults`.
