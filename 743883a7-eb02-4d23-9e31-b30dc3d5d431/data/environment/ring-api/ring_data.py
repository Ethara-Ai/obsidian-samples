"""Data access module for the Ring mock service.

Ring publishes no official public API. This mock follows the client API that
Ring's own apps call and that open-source clients document
(api.ring.com/clients_api, plus the location-mode route for the alarm), for the
five operations the connector needs: list devices, get a device's health, list
a device's event history (rings and motion) with a date filter, get a
recording's details, and set the alarm mode. Every read and write is scoped to
the location the presented token's connected account owns.

Devices carry their kind, model, settings and a health snapshot; the alarm base
station carries the location's alarm mode, so a mode change reads back through
the device list. Events are dings, motions and live views, each with its
recording. Mock simplifications (also stated in api_test_results.md): no video
download, live view, siren or floodlight control, no device settings writes, and
no event stream.
"""

import base64
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent

sys.path.insert(0, str(DATA_DIR.parent))
import _mock_clock  # noqa: E402
from _mutable_store import get_store, read_seed_with_ctx  # noqa: E402
from _connector_auth import ConnectorAuth  # noqa: E402

_API = "ring-api"
_store = get_store(_API)

CDT = timezone(timedelta(hours=-5))
CAMERA_KINDS = ("doorbot", "stickup_cam", "floodlight_cam")
EVENT_KINDS = ("ding", "motion", "on_demand")
MODES = ("home", "away", "disarmed")
OWNER = {"id": 41827763, "first_name": "Dana", "last_name": "Whitfield",
         "email": "dana.whitfield@lakeshoredesign.example"}


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


_store.register("locations", primary_key="location_id",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("locations.json", "locations")])
_store.register("devices", primary_key="id",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("devices.json", "devices")])
_store.register("events", primary_key="id",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("events.json", "events")])

auth = ConnectorAuth(_API, store=_store, data_dir=DATA_DIR)


class RingError:
    """This mock's rendering of a Ring error (``{"error"}``) and its HTTP status."""

    def __init__(self, status, message):
        self.status = status
        self.body = {"error": message}


def invalid(message):
    return RingError(400, message)


def not_found(what):
    return RingError(404, f"{what} not found")


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _device(device_id, account_id):
    key = _int(device_id)
    row = _store.table("devices").get(key) if key is not None else None
    if row is None or row.get("owner_account_id") != account_id:
        return None
    return row


def _category(dbm):
    if dbm is None:
        return None
    if dbm >= -50:
        return "very_good"
    if dbm >= -60:
        return "good"
    if dbm >= -70:
        return "fair"
    return "poor"


def _battery_category(level):
    if level is None:
        return None
    return "very_good" if level >= 70 else "good" if level >= 45 else "fair" if level >= 25 else "poor"


def device_view(row):
    view = {"id": row["id"], "description": row["description"], "device_id": row["device_id"], "kind": row["kind"],
            "location_id": row["location_id"], "time_zone": row["time_zone"], "address": row["address"],
            "firmware_version": row["firmware_version"], "battery_life": row["battery_life"],
            "external_connection": False, "subscribed": row["subscribed"],
            "subscribed_motions": row["subscribed_motions"], "features": row["features"],
            "settings": {k: v for k, v in row["settings"].items() if v is not None},
            "alerts": {"connection": "online"}, "owned": True, "owner": OWNER, "metadata": {"model": row["model"]}}
    for key in ("led_status", "siren_status"):
        if key in row:
            view[key] = row[key]
    if "alarm" in row:
        view["alarm"] = row["alarm"]
    return view


# --- devices ------------------------------------------------------------------------------------

def list_devices(account_id):
    rows = sorted(_store.table("devices").find(lambda r: r.get("owner_account_id") == account_id),
                  key=lambda r: r["id"])
    groups = {"doorbots": [], "authorized_doorbots": [], "chimes": [], "stickup_cams": [], "base_stations": [],
              "beams_bridges": [], "other": []}
    for row in rows:
        kind = row["kind"]
        key = ("doorbots" if kind == "doorbot" else "stickup_cams" if kind in ("stickup_cam", "floodlight_cam")
               else "chimes" if kind == "chime" else "base_stations" if kind.startswith("base_station") else "other")
        groups[key].append(device_view(row))
    return groups


def device_health(device_id, account_id):
    row = _device(device_id, account_id)
    if row is None or row["kind"] not in CAMERA_KINDS:
        return not_found("doorbot")
    health = row["health"]
    return {"device_health": {
        "id": row["id"], "wifi_name": health["wifi_name"], "battery_percentage": health["battery_percentage"],
        "battery_percentage_category": _battery_category(health["battery_percentage"]),
        "battery_voltage": health["battery_voltage"], "latest_signal_strength": health["latest_signal_strength"],
        "latest_signal_category": _category(health["latest_signal_strength"]),
        "average_signal_strength": health["average_signal_strength"],
        "average_signal_category": _category(health["average_signal_strength"]), "firmware": health["firmware"],
        "updated_at": health["updated_at"], "wifi_is_ring_network": False,
        "packet_loss_category": health["packet_loss_category"], "packet_loss_strength": health["packet_loss_strength"],
        "ac_power": health["ac_power"], "transformer_voltage": health["transformer_voltage"],
        "tx_rate": health["tx_rate"], "rx_rate": health["rx_rate"], "external_connection": False}}


# --- history ------------------------------------------------------------------------------------

def _bound(text, name, end):
    try:
        day = date.fromisoformat(text)
        return datetime.combine(day, time.max if end else time.min, tzinfo=CDT)
    except ValueError:
        pass
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return invalid(f"{name} must be a date (YYYY-MM-DD) or an ISO 8601 date-time")
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _when(row):
    return datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))


def event_view(row, device):
    return {"id": row["id"], "created_at": row["created_at"], "answered": row["answered"], "events": [],
            "kind": row["kind"], "favorite": row["favorite"],
            "snapshot_url": f"https://snapshots.mock-ring.example/{row['id']}.jpg",
            "recording": {"status": row["recording_status"]}, "duration": row["duration"],
            "cv_properties": {"person_detected": row["person_detected"], "stream_broken": False,
                              "detection_type": row["detection_type"]},
            "doorbot": {"id": device["id"], "description": device["description"], "type": device["kind"]}}


def history(device_id, account_id, limit=20, older_than=None, kind=None, since=None, until=None):
    device = _device(device_id, account_id)
    if device is None or device["kind"] not in CAMERA_KINDS:
        return not_found("doorbot")
    if not 1 <= limit <= 100:
        return invalid("limit must be between 1 and 100")
    if kind is not None and kind not in EVENT_KINDS:
        return invalid("kind must be ding, motion or on_demand")
    low = _bound(since, "since", False) if since is not None else None
    high = _bound(until, "until", True) if until is not None else None
    for bound in (low, high):
        if isinstance(bound, RingError):
            return bound
    ceiling = None
    if older_than is not None:
        ceiling = _int(older_than)
        if ceiling is None:
            return invalid("older_than must be an event id")
    rows = [r for r in _store.table("events").find(lambda e: e["device_id"] == device["id"])
            if (kind is None or r["kind"] == kind) and (ceiling is None or r["id"] < ceiling)
            and (low is None or _when(r) >= low) and (high is None or _when(r) <= high)]
    rows.sort(key=lambda r: r["id"], reverse=True)
    return [event_view(r, device) for r in rows[:limit]]


def recording(ding_id, account_id):
    key = _int(ding_id)
    row = _store.table("events").get(key) if key is not None else None
    device = _device(row["device_id"], account_id) if row else None
    if row is None or device is None:
        return not_found("ding")
    view = {"ding_id": row["id"], "device_id": device["id"], "device_description": device["description"],
            "kind": row["kind"], "created_at": row["created_at"], "duration_seconds": row["duration"],
            "status": row["recording_status"], "content_type": "video/mp4", "size_bytes": row["size_bytes"],
            "snapshot_url": f"https://snapshots.mock-ring.example/{row['id']}.jpg",
            "person_detected": row["person_detected"], "detection_type": row["detection_type"]}
    if row["recording_status"] == "ready":
        token = base64.urlsafe_b64encode(str(row["id"]).encode()).decode().rstrip("=")
        expires = _when(row) + timedelta(days=60)
        view["url"] = f"https://download.mock-ring.example/video/{token}.mp4"
        view["url_expires_at"] = expires.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return view


# --- alarm --------------------------------------------------------------------------------------

def set_mode(location_id, account_id, mode):
    location = _store.table("locations").get(location_id)
    if location is None or location.get("owner_account_id") != account_id:
        return not_found("location")
    if mode not in MODES:
        return invalid("mode must be home, away or disarmed")
    now = _mock_clock.now(timezone.utc)
    base = _store.table("devices").find_one(
        lambda r: r.get("owner_account_id") == account_id and r["kind"].startswith("base_station")
        and r["location_id"] == location_id)
    if base is not None:
        _store.table("devices").patch(base["id"], {"alarm": {"mode": mode, "updated_at": now.strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"), "updated_by": f"{OWNER['first_name']} {OWNER['last_name']}"}})
    millis = int(now.timestamp() * 1000)
    return {"mode": mode, "lastUpdateTimeMS": millis, "securityStatus": {"lu": millis, "md": "none"},
            "readOnly": False, "notYetParticipatingInMode": []}


_store.eager_load()
