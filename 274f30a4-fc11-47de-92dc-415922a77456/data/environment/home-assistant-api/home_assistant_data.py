"""Data access module for the Home Assistant mock service.

Serves the five operations the connector needs -- read the configuration, list
every entity's state, get one entity's state, call a service on entities (turn
a light on, set a thermostat, lock a door, recall a scene), and read entities'
history for a period -- in the shape of the Home Assistant REST API (/api).
Every read and write is scoped to the home the presented token's connected
account owns.

States are rows keyed by entity id; history is one row per recorded state, so a
service call that changes an entity also appends to its history. Service calls
follow Home Assistant's semantics: the body is the service data, entities
outside the service's domain or unknown to the home are skipped, and the answer
lists the states that changed. Mock simplifications (also stated in
api_test_results.md): a fixed catalog of services, no templates, events,
automations editing, area or device targets, or service response data.
"""

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

_API = "home-assistant-api"
_store = get_store(_API)

SIGNIFICANT_DOMAINS = {"climate", "device_tracker", "humidifier", "water_heater"}


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


for _table, _file, _pk in (("config", "config.json", "id"), ("states", "states.json", "entity_id"),
                           ("history", "history.json", "id"), ("scenes", "scenes.json", "scene_entity_id")):
    _store.register(_table, primary_key=_pk,
                    initial_loader=(lambda f=_file, t=_table: [_strip_ctx(r) for r in _load(f, t)]))

auth = ConnectorAuth(_API, store=_store, data_dir=DATA_DIR)


class HassError:
    """A Home Assistant REST error body (``{"message"}``) and its HTTP status."""

    def __init__(self, status, message):
        self.status = status
        self.body = {"message": message}


def bad(message):
    return HassError(400, message)


def _now():
    return _mock_clock.now(timezone.utc)


def _iso(moment):
    return moment.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _context():
    return "".join(secrets.choice(string.digits + string.ascii_uppercase) for _ in range(26))


def state_view(row):
    return {"entity_id": row["entity_id"], "state": row["state"], "attributes": row["attributes"],
            "last_changed": row["last_changed"], "last_reported": row.get("last_reported", row["last_updated"]),
            "last_updated": row["last_updated"],
            "context": {"id": row["context_id"], "parent_id": None, "user_id": None}}


def _owned(account_id):
    return _store.table("states").find(lambda r: r.get("owner_account_id") == account_id)


# --- reads --------------------------------------------------------------------------------------

def get_config(account_id):
    row = _store.table("config").find_one(lambda r: r.get("owner_account_id") == account_id)
    if row is None:
        return HassError(404, "Not found.")
    return {k: v for k, v in row.items() if k not in ("id", "owner_account_id")}


def list_states(account_id):
    return [state_view(r) for r in sorted(_owned(account_id), key=lambda r: r["entity_id"])]


def get_state(entity_id, account_id):
    row = _store.table("states").get(entity_id)
    if row is None or row.get("owner_account_id") != account_id:
        return HassError(404, "Entity not found.")
    return state_view(row)


def _parse(text):
    try:
        moment = datetime.fromisoformat(str(text).replace("Z", "+00:00").replace(" ", "+"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def history(account_id, timestamp, filter_entity_id=None, end_time=None, minimal_response=False,
            no_attributes=False, significant_changes_only=False):
    start = _parse(timestamp)
    if start is None:
        return bad("Invalid datetime")
    end = start + timedelta(days=1)
    if end_time is not None:
        end = _parse(end_time)
        if end is None:
            return bad("Invalid end_time")
    if not filter_entity_id:
        return bad("filter_entity_id is missing")
    ids = [e.strip().lower() for e in filter_entity_id.split(",") if e.strip()]
    if not ids or any("." not in e or e.startswith(".") or e.endswith(".") for e in ids):
        return bad("Invalid filter_entity_id")
    out = []
    for entity_id in ids:
        rows = sorted(_store.table("history").find(
            lambda h: h["entity_id"] == entity_id and h.get("owner_account_id") == account_id),
            key=lambda h: h["last_changed"])
        before = [h for h in rows if _parse(h["last_changed"]) <= start]
        inside = [h for h in rows if start < _parse(h["last_changed"]) <= end]
        entries = ([before[-1]] if before else []) + inside
        if not entries:
            continue
        if significant_changes_only and entity_id.split(".")[0] not in SIGNIFICANT_DOMAINS:
            kept = [entries[0]]
            for h in entries[1:]:
                if h["state"] != kept[-1]["state"]:
                    kept.append(h)
            entries = kept
        views = []
        for i, h in enumerate(entries):
            if minimal_response and 0 < i < len(entries) - 1:
                views.append({"state": h["state"], "last_changed": h["last_changed"]})
                continue
            view = {"entity_id": entity_id, "state": h["state"], "attributes": h["attributes"],
                    "last_changed": h["last_changed"], "last_updated": h["last_updated"]}
            if no_attributes:
                view.pop("attributes")
            views.append(view)
        out.append(views)
    return out


# --- service calls ------------------------------------------------------------------------------

def _require(data, key):
    if key not in data:
        return bad(f"required key not provided @ data['{key}']")
    return None


def _number(data, key, low, high, kind=int):
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or (kind is int and not float(value).is_integer()):
        return bad(f"expected {'int' if kind is int else 'float'} for dictionary value @ data['{key}']")
    if value < low:
        return bad(f"value must be at least {low} for dictionary value @ data['{key}']")
    if value > high:
        return bad(f"value must be at most {high} for dictionary value @ data['{key}']")
    return None


SERVICES = {
    ("light", "turn_on"): {"entity_id", "brightness", "brightness_pct", "color_temp_kelvin", "rgb_color", "transition"},
    ("light", "turn_off"): {"entity_id", "transition"},
    ("light", "toggle"): {"entity_id", "transition"},
    ("switch", "turn_on"): {"entity_id"}, ("switch", "turn_off"): {"entity_id"}, ("switch", "toggle"): {"entity_id"},
    ("fan", "turn_on"): {"entity_id", "percentage"}, ("fan", "turn_off"): {"entity_id"},
    ("fan", "set_percentage"): {"entity_id", "percentage"},
    ("cover", "open_cover"): {"entity_id"}, ("cover", "close_cover"): {"entity_id"},
    ("cover", "set_cover_position"): {"entity_id", "position"},
    ("lock", "lock"): {"entity_id"}, ("lock", "unlock"): {"entity_id"},
    ("climate", "set_temperature"): {"entity_id", "temperature", "target_temp_high", "target_temp_low", "hvac_mode"},
    ("climate", "set_hvac_mode"): {"entity_id", "hvac_mode"},
    ("climate", "turn_on"): {"entity_id"}, ("climate", "turn_off"): {"entity_id"},
    ("media_player", "turn_on"): {"entity_id"}, ("media_player", "turn_off"): {"entity_id"},
    ("media_player", "media_play"): {"entity_id"}, ("media_player", "media_pause"): {"entity_id"},
    ("media_player", "volume_set"): {"entity_id", "volume_level"},
    ("scene", "turn_on"): {"entity_id", "transition"},
    ("input_boolean", "turn_on"): {"entity_id"}, ("input_boolean", "turn_off"): {"entity_id"},
    ("input_boolean", "toggle"): {"entity_id"},
    ("vacuum", "start"): {"entity_id"}, ("vacuum", "return_to_base"): {"entity_id"},
}
REQUIRED = {("fan", "set_percentage"): "percentage", ("cover", "set_cover_position"): "position",
            ("climate", "set_hvac_mode"): "hvac_mode", ("media_player", "volume_set"): "volume_level"}


def _check(domain, service, data):
    allowed = SERVICES[(domain, service)]
    extra = [k for k in data if k not in allowed]
    if extra:
        return bad(f"extra keys not allowed @ data['{extra[0]}']")
    missing = _require(data, "entity_id") or (_require(data, REQUIRED[(domain, service)])
                                              if (domain, service) in REQUIRED else None)
    if missing:
        return missing
    if not isinstance(data["entity_id"], (str, list)) or (
            isinstance(data["entity_id"], list) and not all(isinstance(e, str) for e in data["entity_id"])):
        return bad("Entity IDs must be a string or a list of strings @ data['entity_id']")
    checks = {"brightness": (0, 255, int), "brightness_pct": (0, 100, float), "color_temp_kelvin": (2000, 6535, int),
              "transition": (0, 6553, float), "percentage": (0, 100, int), "position": (0, 100, int),
              "volume_level": (0, 1, float), "temperature": (45, 92, float), "target_temp_high": (45, 92, float),
              "target_temp_low": (45, 92, float)}
    for key, (low, high, kind) in checks.items():
        if key in data:
            problem = _number(data, key, low, high, kind)
            if problem:
                return problem
    if "rgb_color" in data:
        value = data["rgb_color"]
        if not (isinstance(value, list) and len(value) == 3 and all(
                isinstance(c, int) and not isinstance(c, bool) and 0 <= c <= 255 for c in value)):
            return bad("value should be a list of three integers from 0 to 255 for dictionary value @ data['rgb_color']")
    return None


def _targets(data):
    raw = data["entity_id"]
    ids = raw if isinstance(raw, list) else raw.split(",")
    return [e.strip().lower() for e in ids if e.strip()]


def _apply(domain, service, data, row, scene_targets=None):
    """The new ``(state, attributes)`` for ``row`` under the call, or None when it does not change."""
    state, attrs = row["state"], dict(row["attributes"])
    if domain == "light":
        turn_on = service == "turn_on" or (service == "toggle" and state != "on")
        if not turn_on:
            if state == "off":
                return None
            attrs.update({"brightness": None, "color_mode": None})
            if "color_temp_kelvin" in attrs:
                attrs["color_temp_kelvin"] = None
            if "rgb_color" in attrs:
                attrs["rgb_color"] = None
            return "off", attrs
        modes = attrs.get("supported_color_modes") or ["brightness"]
        brightness = attrs.get("brightness") or 254
        if "brightness" in data:
            brightness = data["brightness"]
        if "brightness_pct" in data:
            brightness = round(255 * data["brightness_pct"] / 100)
        if brightness == 0:
            return _apply(domain, "turn_off", data, row)
        attrs["brightness"] = brightness
        if "rgb_color" in data and "xy" in modes:
            attrs.update({"color_mode": "xy", "rgb_color": list(data["rgb_color"])})
            if "color_temp_kelvin" in attrs:
                attrs["color_temp_kelvin"] = None
        elif "color_temp_kelvin" in data and "color_temp" in modes:
            low, high = attrs.get("min_color_temp_kelvin", 2202), attrs.get("max_color_temp_kelvin", 6535)
            attrs.update({"color_mode": "color_temp", "color_temp_kelvin": max(low, min(high, data["color_temp_kelvin"]))})
            if "rgb_color" in attrs:
                attrs["rgb_color"] = None
        else:
            attrs["color_mode"] = attrs.get("color_mode") or modes[0]
            if "color_temp_kelvin" in attrs and attrs["color_mode"] == "color_temp" and not attrs.get("color_temp_kelvin"):
                attrs["color_temp_kelvin"] = 2700
        return "on", attrs
    if domain in ("switch", "input_boolean"):
        on = service == "turn_on" or (service == "toggle" and state != "on")
        return ("on" if on else "off"), attrs
    if domain == "fan":
        if service == "turn_off":
            attrs["percentage"] = 0
            return "off", attrs
        percentage = data.get("percentage", attrs.get("percentage") or 33)
        attrs["percentage"] = percentage
        return ("on" if percentage else "off"), attrs
    if domain == "cover":
        if service == "set_cover_position":
            position = data["position"]
        else:
            position = 100 if service == "open_cover" else 0
        if "current_position" in attrs:
            attrs["current_position"] = position
        return ("open" if position else "closed"), attrs
    if domain == "lock":
        return ("locked" if service == "lock" else "unlocked"), attrs
    if domain == "climate":
        modes = attrs.get("hvac_modes", [])
        mode = state
        if service == "turn_off":
            mode = "off"
        elif service == "turn_on":
            mode = "heat" if state == "off" else state
        elif "hvac_mode" in data:
            if data["hvac_mode"] not in modes:
                return bad(f"value must be one of {sorted(modes)} for dictionary value @ data['hvac_mode']")
            mode = data["hvac_mode"]
        if "temperature" in data:
            attrs.update({"temperature": data["temperature"], "target_temp_high": None, "target_temp_low": None})
        if "target_temp_high" in data or "target_temp_low" in data:
            attrs.update({"temperature": None, "target_temp_high": data.get("target_temp_high"),
                          "target_temp_low": data.get("target_temp_low")})
        current, target = attrs.get("current_temperature"), attrs.get("temperature")
        if mode == "off":
            attrs["hvac_action"] = "off"
        elif mode == "heat" and target is not None and current is not None:
            attrs["hvac_action"] = "heating" if current < target else "idle"
        elif mode == "cool" and target is not None and current is not None:
            attrs["hvac_action"] = "cooling" if current > target else "idle"
        return mode, attrs
    if domain == "media_player":
        if service == "turn_off":
            return "off", attrs
        if service == "turn_on":
            return ("on" if state == "off" else state), attrs
        if service == "media_play":
            return "playing", attrs
        if service == "media_pause":
            return "paused", attrs
        attrs["volume_level"] = data["volume_level"]
        return state, attrs
    if domain == "vacuum":
        return ("cleaning" if service == "start" else "returning"), attrs
    return None


def _write(row, state, attrs, now, context):
    changed = state != row["state"]
    if not changed and attrs == row["attributes"]:
        return None
    stamp = _iso(now)
    fields = {"state": state, "attributes": attrs, "last_updated": stamp, "last_reported": stamp,
              "context_id": context}
    if changed:
        fields["last_changed"] = stamp
    _store.table("states").patch(row["entity_id"], fields)
    _store.table("history").upsert({"id": "h" + secrets.token_hex(6), "entity_id": row["entity_id"],
                                    "owner_account_id": row["owner_account_id"], "state": state, "attributes": attrs,
                                    "last_changed": stamp, "last_updated": stamp})
    return state_view(_store.table("states").get(row["entity_id"]))


def call_service(domain, service, account_id, data):
    if (domain, service) not in SERVICES:
        return bad("Service not found.")
    problem = _check(domain, service, data)
    if problem:
        return problem
    now, context = _now(), _context()
    changed = []
    for entity_id in _targets(data):
        if entity_id.split(".")[0] != domain:
            continue
        row = _store.table("states").get(entity_id)
        if row is None or row.get("owner_account_id") != account_id:
            continue
        if domain == "scene":
            scene = _store.table("scenes").get(entity_id)
            for target_id, target in sorted((scene or {}).get("targets", {}).items()):
                target_row = _store.table("states").get(target_id)
                if target_row is None:
                    continue
                attrs = dict(target_row["attributes"])
                attrs.update(target["attributes"])
                if target_id.startswith("light.") and target["state"] == "off":
                    result = _apply("light", "turn_off", {"entity_id": target_id}, target_row)
                    if result is None:
                        continue
                    new_state, attrs = result
                else:
                    new_state = target["state"]
                    if target_id.startswith("light.") and "color_temp_kelvin" in target["attributes"]:
                        attrs["color_mode"] = "color_temp"
                view = _write(target_row, new_state, attrs, now, context)
                if view:
                    changed.append(view)
            view = _write(row, _iso(now), row["attributes"], now, context)
            if view:
                changed.append(view)
            continue
        result = _apply(domain, service, data, row)
        if isinstance(result, HassError):
            return result
        if result is None:
            continue
        view = _write(row, result[0], result[1], now, context)
        if view:
            changed.append(view)
    return changed


_store.eager_load()
