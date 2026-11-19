"""Data access module for the Tailscale API mock service.

Serves the six tailnet operations the connector needs -- list the tailnet's
devices, get a device, authorize a device, remove a device, read the access
policy, and create an auth key -- in the shape of the Tailscale API v2
(api.tailscale.com/api/v2), plus the get-key read that shows a created key. Every
read and write is scoped to the tailnet the presented token's connected account
administers; the tailnet is addressed as "-" or by its name.

Devices carry their Tailscale addresses, node and machine keys, owner, OS and
client version, key expiry, authorization, tags and routes. Auth keys keep
their capabilities and expiry; a key's secret is shown once, when it is
created, and only its hash is stored. Mock simplifications (also stated in
api_test_results.md): no de-authorizing, renaming, tagging or route changes,
no key listing or revoking, no policy writes, and no DNS, users or webhooks.
"""

import hashlib
import json
import re
import secrets
import string
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent

sys.path.insert(0, str(DATA_DIR.parent))
import _mock_clock  # noqa: E402
from _mutable_store import get_store, read_seed_with_ctx  # noqa: E402
from _connector_auth import ConnectorAuth  # noqa: E402

_API = "tailscale-api"
_store = get_store(_API)

TAILNET = "lakeshoredesign.example"
DEFAULT_FIELDS = ("addresses", "id", "nodeId", "user", "name", "hostname", "clientVersion", "updateAvailable", "os",
                  "created", "lastSeen", "connectedToControl", "keyExpiryDisabled", "expires", "authorized",
                  "isExternal", "isEphemeral", "machineKey", "nodeKey", "blocksIncomingConnections", "tailnetLockKey",
                  "tailnetLockError", "tags")
EXPIRY_MAX = 90 * 24 * 3600
DESCRIPTION = re.compile(r"^[A-Za-z0-9 _-]{0,50}$")


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


for _table, _file in (("users", "users.json"), ("devices", "devices.json"), ("keys", "keys.json"),
                      ("policy", "policy.json")):
    _store.register(_table, primary_key="id",
                    initial_loader=(lambda f=_file, t=_table: [_strip_ctx(r) for r in _load(f, t)]))

auth = ConnectorAuth(_API, store=_store, data_dir=DATA_DIR)


class TailscaleError:
    """A Tailscale API error body (``{"message"}``) and the HTTP status it is served with."""

    def __init__(self, status, message):
        self.status = status
        self.body = {"message": message}


def invalid(message):
    return TailscaleError(400, message)


def not_found(what="not found"):
    return TailscaleError(404, what)


def _now():
    return _mock_clock.now(timezone.utc).replace(microsecond=0)


def _z(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _tailnet(tailnet, account_id):
    """The account's tailnet name for a path's ``{tailnet}`` ("-" or the name), or None."""
    owned = _store.table("policy").find_one(lambda r: r.get("owner_account_id") == account_id)
    if owned is None or tailnet not in ("-", owned["tailnet"]):
        return None
    return owned["tailnet"]


def _device(device_id, account_id):
    row = _store.table("devices").get(device_id)
    if row is None or row.get("owner_account_id") != account_id:
        return None
    return row


def _latency(row):
    seed = int(hashlib.sha1(row["id"].encode()).hexdigest()[:6], 16)
    regions = {"Chicago": 4 + seed % 9, "New York City": 21 + seed % 11, "Dallas": 27 + seed % 13}
    preferred = {"ord": "Chicago", "chi": "Chicago", "nyc": "New York City"}.get(row.get("derp"), "Chicago")
    return {name: ({"latencyMs": ms, "preferred": True} if name == preferred else {"latencyMs": ms})
            for name, ms in regions.items()}


def device_view(row, fields="default"):
    view = {k: row[k] for k in DEFAULT_FIELDS}
    if fields == "all":
        view["enabledRoutes"] = list(row["enabledRoutes"])
        view["advertisedRoutes"] = list(row["advertisedRoutes"])
        view["clientConnectivity"] = {
            "endpoints": list(row["endpoints"]), "mappingVariesByDestIP": False, "latency": _latency(row),
            "clientSupports": {"hairPinning": False, "ipv6": row["os"] in ("macOS", "iOS"), "pcp": False,
                               "pmp": False, "udp": True, "upnp": False}}
        view["postureIdentity"] = {"serialNumbers": list(row.get("serialNumbers") or []), "disabled": False}
    return view


def _check_fields(fields):
    if fields not in (None, "default", "all"):
        return invalid(f"invalid fields value {fields!r}: use \"default\" or \"all\"")
    return None


# --- devices ------------------------------------------------------------------------------------

def list_devices(tailnet, account_id, fields=None):
    if _tailnet(tailnet, account_id) is None:
        return not_found("tailnet not found")
    problem = _check_fields(fields)
    if problem:
        return problem
    rows = _store.table("devices").find(lambda r: r.get("owner_account_id") == account_id)
    rows.sort(key=lambda r: r["name"])
    return {"devices": [device_view(r, fields or "default") for r in rows]}


def get_device(device_id, account_id, fields=None):
    row = _device(device_id, account_id)
    if row is None:
        return not_found()
    problem = _check_fields(fields)
    if problem:
        return problem
    return device_view(row, fields or "default")


def authorize_device(device_id, account_id, authorized):
    row = _device(device_id, account_id)
    if row is None:
        return not_found()
    if authorized is not True:
        return invalid("this mock serves authorizing a device; de-authorizing is not one of its operations")
    if not row["authorized"]:
        _store.table("devices").patch(device_id, {"authorized": True})
    return None


def delete_device(device_id, account_id):
    if _device(device_id, account_id) is None:
        return not_found()
    _store.table("devices").delete(device_id)
    return None


# --- policy -------------------------------------------------------------------------------------

def read_policy(tailnet, account_id):
    """``(policy document, etag)`` or a TailscaleError."""
    name = _tailnet(tailnet, account_id)
    if name is None:
        return not_found("tailnet not found")
    row = _store.table("policy").find_one(lambda r: r.get("owner_account_id") == account_id)
    document = row["document"]
    etag = '"' + hashlib.sha256(json.dumps(document, sort_keys=True).encode()).hexdigest()[:16] + '"'
    return document, etag


# --- auth keys ----------------------------------------------------------------------------------

def _key_view(row, secret=None):
    now = _now()
    expired = datetime.fromisoformat(row["expires"].replace("Z", "+00:00")) <= now
    view = {"id": row["id"], "keyType": row["keyType"]}
    if secret is not None:
        view["key"] = secret
    view.update({"created": row["created"], "expires": row["expires"]})
    if row.get("revoked"):
        view["revoked"] = row["revoked"]
    view["invalid"] = bool(row.get("revoked")) or expired
    view["capabilities"] = row["capabilities"]
    view["description"] = row.get("description") or ""
    return view


def _login(account_id):
    """The user the connected account, and so the calling token, belongs to: the account's user row
    marked ``is_owner`` (as box-api marks it), else the account's first admin."""
    users = _store.table("users").find(lambda u: u.get("owner_account_id") == account_id)
    owner = (next((u for u in users if u.get("is_owner")), None)
             or next((u for u in users if u["role"] == "admin"), None))
    return owner["loginName"] if owner else ""


def create_key(tailnet, account_id, create, expiry_seconds=None, description=None):
    name = _tailnet(tailnet, account_id)
    if name is None:
        return not_found("tailnet not found")
    expiry = EXPIRY_MAX if expiry_seconds is None else expiry_seconds
    if not 1 <= expiry <= EXPIRY_MAX:
        return invalid(f"expirySeconds must be between 1 and {EXPIRY_MAX} (90 days)")
    if description is not None and not DESCRIPTION.match(description):
        return invalid("description must be at most 50 letters, digits, spaces, hyphens or underscores")
    login = _login(account_id)
    policy = read_policy(tailnet, account_id)[0]
    groups = {g for g, members in policy.get("groups", {}).items() if login in members}
    tags = list(create.get("tags") or [])
    for tag in tags:
        if not tag.startswith("tag:") or tag not in policy.get("tagOwners", {}):
            return invalid(f"requested tags [{tag}] are invalid or not permitted")
        owners = policy["tagOwners"][tag]
        if login not in owners and not groups & set(owners):
            return invalid(f"requested tags [{tag}] are invalid or not permitted")
    now = _now()
    kid = "k" + "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(10)) + "CNTRL"
    secret = f"tskey-auth-{kid}-" + "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))
    row = {"id": kid, "tailnet": name, "owner_account_id": account_id, "keyType": "auth", "created": _z(now),
           "expires": _z(now + timedelta(seconds=expiry)), "revoked": None, "user_login": login,
           "description": description or "",
           "capabilities": {"devices": {"create": {"reusable": bool(create.get("reusable")),
                                                   "ephemeral": bool(create.get("ephemeral")),
                                                   "preauthorized": bool(create.get("preauthorized")),
                                                   "tags": tags}}},
           "secret_sha256": hashlib.sha256(secret.encode()).hexdigest()}
    _store.table("keys").upsert(row)
    return _key_view(row, secret=secret)


def get_key(tailnet, key_id, account_id):
    if _tailnet(tailnet, account_id) is None:
        return not_found("tailnet not found")
    row = _store.table("keys").get(key_id)
    if row is None or row.get("owner_account_id") != account_id:
        return not_found("key not found")
    return _key_view(row)


_store.eager_load()
