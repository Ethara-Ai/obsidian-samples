# Google Contacts API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$GOOGLE_CONTACTS_API_URL`.** Every operation needs `Authorization: Bearer $TOKEN`, where `$TOKEN` comes from `POST /oauth/token` and carries only the scopes it was issued with (see SKILL.md, Authentication). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `GOOGLE_CONTACTS_API_URL` | Base URL for all requests |
| `GOOGLE_CONTACTS_CLIENT_ID` | OAuth client id of the connected account |
| `GOOGLE_CONTACTS_CLIENT_SECRET` | OAuth client secret of the connected account |

## Token

```bash
TOKEN=$(curl -s -X POST "$GOOGLE_CONTACTS_API_URL/oauth/token" -d grant_type=client_credentials -d client_id="$GOOGLE_CONTACTS_CLIENT_ID" -d client_secret="$GOOGLE_CONTACTS_CLIENT_SECRET" -d scope="<space-separated scopes>" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s "$GOOGLE_CONTACTS_API_URL/oauth/tokeninfo" -H "Authorization: Bearer $TOKEN"
```

## People

```bash
curl -s "$GOOGLE_CONTACTS_API_URL/v1/people/me/connections?personFields=names,emailAddresses,phoneNumbers" -H "Authorization: Bearer $TOKEN"
curl -s "$GOOGLE_CONTACTS_API_URL/v1/people/<personId>?personFields=names,emailAddresses,phoneNumbers" -H "Authorization: Bearer $TOKEN"
curl -s -X PATCH "$GOOGLE_CONTACTS_API_URL/v1/people/<personId>:updateContact?updatePersonFields=phoneNumbers" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"etag": "<etag>", "phoneNumbers": [{"value": "+1 415 555 0199", "type": "mobile"}]}'
curl -s -X DELETE "$GOOGLE_CONTACTS_API_URL/v1/people/<personId>:deleteContact" -H "Authorization: Bearer $TOKEN"
```

## People:Createcontact

```bash
curl -s -X POST "$GOOGLE_CONTACTS_API_URL/v1/people:createContact" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"names": [{"givenName": "Priya", "familyName": "Natarajan"}], "emailAddresses": [{"value": "priya.natarajan@mail.example"}]}'
```

## People:Searchcontacts

```bash
curl -s "$GOOGLE_CONTACTS_API_URL/v1/people:searchContacts?query=reza&readMask=names,emailAddresses,phoneNumbers" -H "Authorization: Bearer $TOKEN"
```

## Searching and writing contacts

- `GET /v1/people:searchContacts` needs `query` (the start of a name, email address or phone number) and `readMask`, the fields to return (for example `names,emailAddresses,phoneNumbers`); without one of them it is a `400`. It answers up to 10 matches (`pageSize`, up to 30), and `{}` when nothing matches.
- `GET /v1/people/me/connections` and `GET /v1/people/{personId}` need `personFields` the same way.
- `POST /v1/people:createContact` takes a person with at least one of `names`, `emailAddresses`, `phoneNumbers` or `organizations`.
- `PATCH /v1/people/{personId}:updateContact` changes only the fields named in `updatePersonFields`, and its body must carry the contact's current `etag` (read it with `GET /v1/people/{personId}`); without it, or with a stale one, it is a `400`.
- A query parameter the method does not take is a `400`. Writes need a token carrying `contacts`.
