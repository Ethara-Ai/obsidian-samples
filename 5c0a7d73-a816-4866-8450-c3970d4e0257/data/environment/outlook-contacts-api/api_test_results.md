<!-- api-test-results:begin -->
# Outlook Contacts API (Mock) - Test Results

GENERATED SECTION. DO NOT HAND-EDIT. `python3 script/gen_api_test_results.py --only outlook-contacts-api` writes everything between the api-test-results markers by sending the requests below to the service in-process; the text after the end marker is kept as written.

Base URL: `http://localhost:8121` (docker-compose: `http://outlook-contacts-api:8121`)

## Authentication

Every operation needs `Authorization: Bearer <token>` from `POST /oauth/token` with client credentials. The connected client `ocon-connector-app` (account `acct-alex-carter`) is granted `Contacts.Read`, `Contacts.ReadWrite`; a token requested without `scope` carries `Contacts.Read`. A request without a live token answers `401 invalid_token`, and a live token without the route's scope answers `403 insufficient_scope`.

## Endpoints

Each row is one request the generator sent. **Status** is the answer to the request as shown, sent with a token carrying every granted scope. **No token** is the same request with no `Authorization` header, and **Scope removed** the same request with a token carrying every granted scope except the route's own. The shared `/audit` and `/admin` planes every mock serves are described in `environment/API_DOCUMENTATION.md` and not listed.

| Method | Path | Scope | Request sent | Status | No token | Scope removed |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/oauth/token` | client credentials | `/oauth/token (form body)` | 200 | - | - |
| GET | `/health` | none | `/health` | 200 | - | - |
| GET | `/oauth/tokeninfo` | any live token | `/oauth/tokeninfo` | 200 | 401 | - |
| GET | `/v1.0/me/contacts` | `Contacts.Read` | `/v1.0/me/contacts?$filter=startswith(displayName,'Diego')&$select=displayName,emailAddresses,mobilePhone` | 200 | 401 | 403 |
| GET | `/v1.0/me/contacts` | `Contacts.Read` | `/v1.0/me/contacts?$filter=emailAddresses/any(a:a/address eq 'priya.nair@contoso.com')&$select=displayName` | 200 | 401 | 403 |
| GET | `/v1.0/me/contacts/{contact_id}` | `Contacts.Read` | `/v1.0/me/contacts/<Priya Nair's contact id>` | 200 | 401 | 403 |
| POST | `/v1.0/me/contacts` | `Contacts.ReadWrite` | `/v1.0/me/contacts (JSON body)` | 201 | 401 | 403 |
| PATCH | `/v1.0/me/contacts/{contact_id}` | `Contacts.ReadWrite` | `/v1.0/me/contacts/<new contact id> (JSON body)` | 200 | 401 | 403 |
| GET | `/v1.0/me/contacts` | `Contacts.Read` | `/v1.0/me/contacts?$filter=categories/any(c:c eq 'Customer') and companyName eq 'Tailspin Toys'&$orderby=surname&$select=displayName,jobTitle&$top=20` | 200 | 401 | 403 |
| DELETE | `/v1.0/me/contacts/{contact_id}` | `Contacts.ReadWrite` | `/v1.0/me/contacts/<new contact id>` | 204 | 401 | 403 |

## Seed files

| File | Records |
| --- | --- |
| `contacts.json` | 159 |
| `mailboxes.json` | 1 |
<!-- api-test-results:end -->

## Connector operations covered

List contacts (`GET /v1.0/me/contacts`), filtered by name or email with `$filter` (for example `startswith(displayName,'Diego')`, `givenName eq 'Grace' and surname eq 'Lee'`, or `emailAddresses/any(a:a/address eq 'priya.nair@contoso.com')`), get a contact (`GET /v1.0/me/contacts/{contact_id}`), create a contact (`POST /v1.0/me/contacts`), update a contact (`PATCH /v1.0/me/contacts/{contact_id}`), and delete a contact (`DELETE /v1.0/me/contacts/{contact_id}`). Nothing else is served. outlook-api is a separate service and still serves the same mailbox's mail, events and its own seven contacts.

## Mock simplifications

- Contacts live in the default contacts folder only: no contact folders, photos, extensions or delta queries, and a deleted contact is gone rather than moved to Deleted Items.
- `$filter` takes `eq`, `ne`, `gt`, `ge`, `lt`, `le`, `and`, `or`, `not`, parentheses, `startswith`, `endswith`, `contains`, and `any` with `eq` or `ne` over `emailAddresses`, `categories`, `businessPhones` and `homePhones`, on the properties the server names; text comparisons ignore case. `$orderby` takes displayName, givenName, surname, fileAs, companyName, jobTitle, createdDateTime and lastModifiedDateTime, and the default order is displayName. `$select`, `$top` (default 10, at most 1000) and `$skip` work, and `@odata.nextLink` points back at this service. `$search`, `$expand` and `$count` are not served. An unknown `$` option is a 400, as on Graph; an unknown plain query parameter is a 400 too, where Graph would ignore it, so a misspelt option cannot pass for one that worked.
- A contact holds at most three email addresses, two business phones, two home phones and three IM addresses, and each email address must look like one; more, or a malformed address, is a 400 `ErrorInvalidProperty`. A birthday is a date (a time sent with it is dropped) and comes back at midnight UTC. Sending a collection replaces it whole, and sending `null` clears a property.
- `displayName` is filled from the given, middle and surname (else the company, else the first email address) when a contact is created without one, and follows a name change while it still matches the name; once set by hand it stays as set.
- A property the contact type does not have is a 400 `RequestBodyRead`, nested ones included, and errors use Graph's envelope (`{"error": {"code", "message", "innerError"}}`).

## Seed data

- Connected account `acct-alex-carter` (Alex Carter, alex.carter@contoso.com, Contoso), the mailbox outlook-api and outlook-calendar-api serve
- 159 contacts as of October 1, 2026: outlook-api's seven contacts first, unchanged (ids, names, email addresses, titles, companies and mobile numbers); the other colleagues on Alex's calendar and the birthdays on its Birthdays calendar; 60 more Contoso colleagues across the company; 32 customer and 20 vendor contacts at Vandelay Industries, Fabrikam, Northwind Traders and other fictional companies; 12 recruiting candidates; family and friends; and the places on the calendar (Bayview Dental, Green Street Deli, Seacliff Lodge)
- Traps a task can use: two cards named Diego Santos (work and personal), Grace Lee with three email addresses, four contacts with no email address, and company-only cards with no person's name
- Every phone number is in the 555-0100 to 555-0199 range set aside for fiction, and every street address is invented
- 1 OAuth client `ocon-connector-app`: both scopes granted; a token requested without `scope` carries only `Contacts.Read`
