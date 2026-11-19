<!-- api-test-results:begin -->
# Tailscale API (Mock) - Test Results

GENERATED SECTION. DO NOT HAND-EDIT. `python3 script/gen_api_test_results.py --only tailscale-api` writes everything between the api-test-results markers by sending the requests below to the service in-process; the text after the end marker is kept as written.

Base URL: `http://localhost:8127` (docker-compose: `http://tailscale-api:8127`)

## Authentication

Every operation needs `Authorization: Bearer <token>` from `POST /oauth/token` with client credentials. The connected client `tailscale-connector-app` (account `acct-dana-whitfield`) is granted `devices:core:read`, `devices:core`, `policy_file:read`, `auth_keys`, `auth_keys:read`; a token requested without `scope` carries `devices:core:read`, `policy_file:read`, `auth_keys:read`. A request without a live token answers `401 invalid_token`, and a live token without the route's scope answers `403 insufficient_scope`.

## Endpoints

Each row is one request the generator sent. **Status** is the answer to the request as shown, sent with a token carrying every granted scope. **No token** is the same request with no `Authorization` header, and **Scope removed** the same request with a token carrying every granted scope except the route's own. The shared `/audit` and `/admin` planes every mock serves are described in `environment/API_DOCUMENTATION.md` and not listed.

| Method | Path | Scope | Request sent | Status | No token | Scope removed |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/oauth/token` | client credentials | `/oauth/token (form body)` | 200 | - | - |
| GET | `/health` | none | `/health` | 200 | - | - |
| GET | `/oauth/tokeninfo` | any live token | `/oauth/tokeninfo` | 200 | 401 | - |
| GET | `/api/v2/tailnet/{tailnet}/devices` | `devices:core:read` | `/api/v2/tailnet/-/devices` | 200 | 401 | 403 |
| GET | `/api/v2/tailnet/{tailnet}/devices` | `devices:core:read` | `/api/v2/tailnet/lakeshoredesign.example/devices?fields=all` | 200 | 401 | 403 |
| GET | `/api/v2/device/{device_id}` | `devices:core:read` | `/api/v2/device/<ben-laptop-new device id>?fields=all` | 200 | 401 | 403 |
| POST | `/api/v2/device/{device_id}/authorized` | `devices:core` | `/api/v2/device/<ben-laptop-new device id>/authorized (JSON body)` | 200 | 401 | 403 |
| DELETE | `/api/v2/device/{device_id}` | `devices:core` | `/api/v2/device/<desktop-7f3k2q device id>` | 200 | 401 | 403 |
| GET | `/api/v2/tailnet/{tailnet}/acl` | `policy_file:read` | `/api/v2/tailnet/-/acl` | 200 | 401 | 403 |
| POST | `/api/v2/tailnet/{tailnet}/keys` | `auth_keys` | `/api/v2/tailnet/-/keys (JSON body)` | 200 | 401 | 403 |
| GET | `/api/v2/tailnet/{tailnet}/keys/{key_id}` | `auth_keys:read` | `/api/v2/tailnet/-/keys/<new key id>` | 200 | 401 | 403 |

## Seed files

| File | Records |
| --- | --- |
| `devices.json` | 81 |
| `keys.json` | 66 |
| `policy.json` | 1 |
| `users.json` | 14 |
<!-- api-test-results:end -->

## Connector operations covered

List the tailnet's devices (`GET /api/v2/tailnet/{tailnet}/devices`), get a device (`GET /api/v2/device/{deviceId}`), authorize a device (`POST /api/v2/device/{deviceId}/authorized`), remove a device (`DELETE /api/v2/device/{deviceId}`), read the access policy (`GET /api/v2/tailnet/{tailnet}/acl`), and create an auth key (`POST /api/v2/tailnet/{tailnet}/keys`). Tailscale's get-key route (`GET /api/v2/tailnet/{tailnet}/keys/{keyId}`) is served too, as the read that shows a key the create operation made, since the operation list names no other way to read one back. Nothing else is served.

## Mock simplifications

- Errors use Tailscale's body, `{"message"}`: `404` for a device, key or tailnet the connected account does not administer, `400` for a bad value, an unknown body field, or a query parameter the operation does not take. The tailnet in a path is `-` or its name, `lakeshoredesign.example`.
- `fields` is `default` or `all`; `all` adds each device's enabled and advertised routes, client connectivity (endpoints, DERP latency, NAT traversal support) and posture identity. Devices are listed by name.
- Authorizing takes `{"authorized": true}` and answers 200 with an empty body; it is idempotent. De-authorizing (`false`) is not one of the connector's operations and answers 400. Removing a device answers 200 with an empty body, after which the device reads as 404 and leaves the list.
- The access policy is returned as JSON (not HuJSON) with an `ETag`; it cannot be changed.
- A new auth key takes `capabilities.devices.create` (`reusable`, `ephemeral`, `preauthorized`, `tags`), `expirySeconds` (1 to 7,776,000, default 90 days) and `description` (up to 50 letters, digits, spaces, hyphens or underscores). Every tag must be in the policy's `tagOwners` and owned by the connected admin. The key's secret (`tskey-auth-...`) is returned once, by the create; the get-key read never shows it, and reports `invalid` when a key has expired or was revoked.
- No de-authorizing, renaming, tagging, route approval or key expiry changes on devices, no key listing or revoking, no policy writes, and no DNS, users, webhooks or device posture writes.

## Seed data

- Connected account `acct-dana-whitfield`: Lakeshore Design Studio's tailnet `lakeshoredesign.example` (`tail4c2f9a.ts.net`), administered by Dana Whitfield and Leah Novak, with 14 users: nine staff, two contractors shared in for the Brightwell install (Lara Dimitrov of Quillfield Construction, Walt Becker of North Branch Millwork), and three former staff suspended in July.
- 81 devices: the studio NAS, render, backup and print servers, a subnet router for 10.20.0.0/24 and a Chicago exit node; staff laptops, phones, tablets and workstations; Dana's home Home Assistant box (`ha-home`, advertising 192.168.40.0/24, not yet approved), home NAS and Mac; the contractors' devices; four devices waiting for approval (`ben-laptop-new`, `sofia-ipad`, `hannah-desktop`, and the unexplained `desktop-7f3k2q`); the former staff's devices with expired node keys; and 30 ephemeral cloud render workers, six still online. Public endpoints use the documentation address ranges.
- 66 auth keys: one-off enrollment keys for the servers and new devices, a reusable ephemeral key for the render workers each month (July's revoked), and older onboarding keys, most long expired. Only a hash of each secret is stored.
- 1 access policy: groups for admins, studio, designers and contractors, tag owners, ACLs that keep contractors on the NAS file share and `tag:home` reachable from Dana alone, route and exit node auto-approvers, SSH rules and policy tests.
- 1 OAuth client `tailscale-connector-app`: `devices:core:read`, `devices:core`, `policy_file:read`, `auth_keys` and `auth_keys:read` granted; a token requested without `scope` carries the three read scopes.
