<!-- api-test-results:begin -->
# Google Contacts API (Mock) - Test Results

GENERATED SECTION. DO NOT HAND-EDIT. `python3 script/gen_api_test_results.py --only google-contacts-api` writes everything between the api-test-results markers by sending the requests below to the service in-process; the text after the end marker is kept as written.

Base URL: `http://localhost:8116` (docker-compose: `http://google-contacts-api:8116`)

## Authentication

Every operation needs `Authorization: Bearer <token>` from `POST /oauth/token` with client credentials. The connected client `gcontacts-connector-app` (account `acct-dana-whitfield`) is granted `contacts.readonly`, `contacts`; a token requested without `scope` carries `contacts.readonly`. A request without a live token answers `401 invalid_token`, and a live token without the route's scope answers `403 insufficient_scope`.

## Endpoints

Each row is one request the generator sent. **Status** is the answer to the request as shown, sent with a token carrying every granted scope. **No token** is the same request with no `Authorization` header, and **Scope removed** the same request with a token carrying every granted scope except the route's own. The shared `/audit` and `/admin` planes every mock serves are described in `environment/API_DOCUMENTATION.md` and not listed.

| Method | Path | Scope | Request sent | Status | No token | Scope removed |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/oauth/token` | client credentials | `/oauth/token (form body)` | 200 | - | - |
| GET | `/health` | none | `/health` | 200 | - | - |
| GET | `/oauth/tokeninfo` | any live token | `/oauth/tokeninfo` | 200 | 401 | - |
| GET | `/v1/people/me/connections` | `contacts.readonly` or `contacts` | `/v1/people/me/connections?personFields=names,emailAddresses,phoneNumbers&pageSize=10` | 200 | 401 | - |
| GET | `/v1/people/me/connections` | `contacts.readonly` or `contacts` | `/v1/people/me/connections?personFields=names&sortOrder=LAST_NAME_ASCENDING&pageSize=5` | 200 | 401 | - |
| GET | `/v1/people:searchContacts` | `contacts.readonly` or `contacts` | `/v1/people:searchContacts?query=brightwell&readMask=names,emailAddresses,organizations` | 200 | 401 | - |
| GET | `/v1/people:searchContacts` | `contacts.readonly` or `contacts` | `/v1/people:searchContacts?query=312-555-0140&readMask=names,phoneNumbers` | 200 | 401 | - |
| GET | `/v1/people/{personId}` | `contacts.readonly` or `contacts` | `/v1/people/<id from the search>?personFields=names,emailAddresses,phoneNumbers,organizations,biographies,memberships` | 200 | 401 | - |
| POST | `/v1/people:createContact` | `contacts` | `/v1/people:createContact?personFields=names,emailAddresses,phoneNumbers (JSON body)` | 200 | 401 | 403 |
| PATCH | `/v1/people/{personId}:updateContact` | `contacts` | `/v1/people/<new contact id>:updateContact?updatePersonFields=phoneNumbers,biographies&personFields=names,phoneNumbers,biographies (JSON body)` | 200 | 401 | 403 |
| DELETE | `/v1/people/{personId}:deleteContact` | `contacts` | `/v1/people/<new contact id>:deleteContact` | 200 | 401 | 403 |

## Seed files

| File | Records |
| --- | --- |
| `contacts.json` | 193 |
<!-- api-test-results:end -->

## Connector operations covered

List contacts (`GET /v1/people/me/connections`), get one contact (`GET /v1/people/{personId}`), search contacts by name, email or phone (`GET /v1/people:searchContacts`), create a contact (`POST /v1/people:createContact`), update a contact (`PATCH /v1/people/{personId}:updateContact`) and delete a contact (`DELETE /v1/people/{personId}:deleteContact`). Nothing else is served.

## Mock simplifications

- Only the CONTACT source exists: there is no profile, domain or other-contacts data, and `people/me` is not served. Memberships cover the `myContacts` and `starred` system groups; contact groups have no routes.
- `personFields` (list and get) and `readMask` (search) are required, as on Google; any People API field name is accepted, and a field the mock does not store is simply absent. `personFields` on create and update is optional and defaults to every field.
- Search matches the start of any word of a contact's names, nicknames, organizations or email addresses (every query word must match), or, for a query of digits and phone punctuation, the start of a phone number in national, E.164 or seven-digit local form. Results are ordered by display name; `pageSize` is 10 by default and at most 30. An empty query answers `{}`.
- `names`, `birthdays` and `biographies` are singletons for a contact. Update needs the contact's current `etag` (top level or in `metadata.sources`); a stale one answers 400 `FAILED_PRECONDITION`. Every field named in `updatePersonFields` is replaced, and a field the body leaves out is cleared; fields not named are untouched even when the body carries them. Each write gives the contact a new `etag` and `updateTime`.
- Phone numbers keep the text they were given; `canonicalForm` is computed for North American and `+`-prefixed numbers.
- A query parameter the method does not take is a 400, as on Google. Sync tokens and `sources` are not served.

## Seed data

- Connected account `acct-dana-whitfield` (Dana Whitfield, Lakeshore Design Studio, Chicago), the same account google-drive-api, google-docs-api and google-sheets-api serve
- 193 contacts: the eight people of the studio, the nine Brightwell Hospitality contacts of the `Brightwell Contact List` sheet, the client and lead contacts of `Client Roster 2026` and `Lead Pipeline`, and the vendors of `Vendor Directory`, each with the email and phone those sheets give; then family, friends, neighbours, local services, architects, builders, suppliers, press and recruiters
- Deliberate look-alikes for disambiguation: two Alicia Brandt cards (the current Brightwell one and an old Harborview Hotels one), Omar and Samira Haddad, Leah and Chris Novak, Raj and Dr. Sam Patel, Ivy and Mia Chen
- 13 starred contacts, 41 birthdays, 26 postal addresses; organisation-only cards for the studio front desk and three vendors
- Phone numbers use the fictional 555-01XX range (and the UK 020 7946 0XXX range); every person, street and email domain is invented
- 1 OAuth client `gcontacts-connector-app`: both scopes granted; a token requested without `scope` carries only `contacts.readonly`
