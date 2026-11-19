# Jira API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$JIRA_API_URL`.** Auth headers are mocked (any token is accepted) and responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `JIRA_API_URL` | Base URL for all requests |

## Rest

```bash
curl -s "$JIRA_API_URL/rest/api/3/project"
curl -s -X POST "$JIRA_API_URL/rest/api/3/issue" -H 'Content-Type: application/json' -d '{}'
curl -s "$JIRA_API_URL/rest/api/3/issue/<issue_key>"
curl -s -X PUT "$JIRA_API_URL/rest/api/3/issue/<issue_key>" -H 'Content-Type: application/json' -d '{}'
curl -s "$JIRA_API_URL/rest/api/3/issue/<issue_key>/transitions"
curl -s -X POST "$JIRA_API_URL/rest/api/3/issue/<issue_key>/transitions" -H 'Content-Type: application/json' -d '{}'
curl -s -G "$JIRA_API_URL/rest/api/3/search" --data-urlencode 'jql=project = ENG AND sprint = "ENG Sprint 22"'
curl -s "$JIRA_API_URL/rest/agile/1.0/board"
curl -s "$JIRA_API_URL/rest/agile/1.0/board/<board_id>/sprint"
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
