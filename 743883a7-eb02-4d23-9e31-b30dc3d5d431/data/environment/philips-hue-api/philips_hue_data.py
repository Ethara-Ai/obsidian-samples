"""Data access module for the Philips Hue mock service.

Serves the six operations the connector needs -- list lights, get a light,
change a light's on/off state, brightness and colour, list rooms, list scenes,
and recall a scene -- in the shape of the Hue CLIP API v2
(https://<bridge>/clip/v2/resource/...). Every read and write is scoped to the
bridge the presented token's connected account owns.

Lights keep their on state, brightness (percent), colour temperature (mirek) or
colour (CIE xy) and colour mode; a light's capabilities follow its kind (colour,
white ambiance, or white only). Rooms list their devices and grouped light;
scenes store one action per light and a palette. Recalling a scene applies its
actions and marks it active, and changing a light by hand deactivates the
scenes of its room. Mock simplifications (also stated in api_test_results.md):
no zones, entertainment, effects, timed effects, alerts or identify, no scene
editing, and bearer tokens instead of the bridge's application key.
"""

import sys
from datetime import timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent

sys.path.insert(0, str(DATA_DIR.parent))
import _mock_clock  # noqa: E402
from _mutable_store import get_store, read_seed_with_ctx  # noqa: E402
from _connector_auth import ConnectorAuth  # noqa: E402

_API = "philips-hue-api"
_store = get_store(_API)

GAMUT_C = {"red": {"x": 0.6915, "y": 0.3083}, "green": {"x": 0.17, "y": 0.7}, "blue": {"x": 0.1532, "y": 0.0475}}
MIREK_MIN, MIREK_MAX = 153, 500


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


for _table, _file in (("bridge", "bridge.json"), ("devices", "devices.json"), ("lights", "lights.json"),
                      ("rooms", "rooms.json"), ("grouped_lights", "grouped_lights.json"), ("scenes", "scenes.json")):
    _store.register(_table, primary_key="id",
                    initial_loader=(lambda f=_file, t=_table: [_strip_ctx(r) for r in _load(f, t)]))

auth = ConnectorAuth(_API, store=_store, data_dir=DATA_DIR)


class HueError:
    """A CLIP v2 error envelope (``{"data": [], "errors": [{"description"}]}``) and its HTTP status."""

    def __init__(self, status, description):
        self.status = status
        self.body = {"data": [], "errors": [{"description": description}]}


def invalid(description):
    return HueError(400, description)


def not_found():
    return HueError(404, "Not Found")


def _now():
    return _mock_clock.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _envelope(data):
    return {"errors": [], "data": data}


def _owned(table, account_id):
    return _store.table(table).find(lambda r: r.get("owner_account_id") == account_id)


def _get(table, resource_id, account_id):
    row = _store.table(table).get(resource_id)
    if row is None or row.get("owner_account_id") != account_id:
        return None
    return row


# --- rendering ----------------------------------------------------------------------------------

def light_view(row):
    view = {"id": row["id"], "id_v1": row["id_v1"], "owner": row["owner"], "metadata": row["metadata"],
            "product_data": {"function": row["metadata"].get("function", "mixed")}, "identify": {}, "service_id": 0,
            "on": {"on": row["on"]}, "dimming": {"brightness": row["brightness"], "min_dim_level": 0.2},
            "dimming_delta": {}}
    if row["kind"] in ("color", "ambiance"):
        valid = row["color_mode"] == "color_temperature"
        view["color_temperature"] = {"mirek": row["mirek"] if valid else None, "mirek_valid": valid,
                                     "mirek_schema": {"mirek_minimum": MIREK_MIN, "mirek_maximum": MIREK_MAX}}
        view["color_temperature_delta"] = {}
    if row["kind"] == "color":
        view["color"] = {"xy": row["xy"], "gamut": GAMUT_C, "gamut_type": "C"}
    view.update({"dynamics": {"status": "none", "status_values": ["none", "dynamic_palette"], "speed": 0.0,
                              "speed_valid": False},
                 "alert": {"action_values": ["breathe"]}, "signaling": {"signal_values": ["no_signal", "on_off"]},
                 "mode": "normal",
                 "powerup": {"preset": "safety", "configured": True, "on": {"mode": "on", "on": {"on": True}},
                             "dimming": {"mode": "dimming", "dimming": {"brightness": 100.0}}},
                 "type": "light"})
    return view


def room_view(row):
    return {k: row[k] for k in ("id", "id_v1", "children", "services", "metadata", "type")}


def scene_view(row):
    return {k: row[k] for k in ("id", "id_v1", "actions", "palette", "metadata", "group", "speed", "auto_dynamic",
                                "status", "type")} | {"recall": {}}


# --- reads --------------------------------------------------------------------------------------

def list_lights(account_id):
    rows = sorted(_owned("lights", account_id), key=lambda r: int(r["id_v1"].rsplit("/", 1)[1]))
    return _envelope([light_view(r) for r in rows])


def get_light(light_id, account_id):
    row = _get("lights", light_id, account_id)
    if row is None:
        return not_found()
    return _envelope([light_view(row)])


def list_rooms(account_id):
    rows = sorted(_owned("rooms", account_id), key=lambda r: int(r["id_v1"].rsplit("/", 1)[1]))
    return _envelope([room_view(r) for r in rows])


def list_scenes(account_id):
    return _envelope([scene_view(r) for r in _owned("scenes", account_id)])


# --- writes -------------------------------------------------------------------------------------

def _room_of(light_row, account_id):
    for room in _owned("rooms", account_id):
        if any(c["rid"] == light_row["owner"]["rid"] for c in room["children"]):
            return room
    return None


def _deactivate(room_id, account_id, keep=None):
    for scene in _owned("scenes", account_id):
        if scene["group"]["rid"] == room_id and scene["id"] != keep and scene["status"]["active"] != "inactive":
            status = dict(scene["status"], active="inactive")
            _store.table("scenes").patch(scene["id"], {"status": status})


def _changes(row, body):
    """The light fields ``body`` sets, or a HueError."""
    fields = {}
    if "on" in body:
        fields["on"] = body["on"]["on"]
    if "dimming" in body:
        brightness = body["dimming"]["brightness"]
        if not 0 <= brightness <= 100:
            return invalid("invalid body: dimming.brightness must be between 0 and 100")
        fields["brightness"] = round(max(brightness, 0.2) if brightness else 0.2, 2)
    if "color_temperature" in body:
        if row["kind"] == "white":
            return invalid("invalid body: this light does not support color_temperature")
        mirek = body["color_temperature"]["mirek"]
        if not MIREK_MIN <= mirek <= MIREK_MAX:
            return invalid(f"invalid body: color_temperature.mirek must be between {MIREK_MIN} and {MIREK_MAX}")
        fields.update({"mirek": mirek, "color_mode": "color_temperature"})
    if "color" in body:
        if row["kind"] != "color":
            return invalid("invalid body: this light does not support color")
        x, y = body["color"]["xy"]["x"], body["color"]["xy"]["y"]
        if not (0 <= x <= 1 and 0 <= y <= 1):
            return invalid("invalid body: color.xy values must be between 0 and 1")
        fields.update({"xy": {"x": round(x, 4), "y": round(y, 4)}, "color_mode": "xy"})
    return fields


def update_light(light_id, account_id, body):
    row = _get("lights", light_id, account_id)
    if row is None:
        return not_found()
    if not body:
        return invalid("invalid body: no property to change")
    fields = _changes(row, body)
    if isinstance(fields, HueError):
        return fields
    _store.table("lights").patch(light_id, fields)
    room = _room_of(row, account_id)
    if room is not None:
        _deactivate(room["id"], account_id)
    return _envelope([{"rid": light_id, "rtype": "light"}])


def recall_scene(scene_id, account_id, recall):
    scene = _get("scenes", scene_id, account_id)
    if scene is None:
        return not_found()
    action = recall.get("action") or "active"
    has_palette = bool(scene["palette"].get("color"))
    if action == "dynamic_palette" and not has_palette:
        return invalid("invalid body: this scene has no palette to play dynamically")
    override = (recall.get("dimming") or {}).get("brightness")
    if override is not None and not 0 <= override <= 100:
        return invalid("invalid body: recall.dimming.brightness must be between 0 and 100")
    for item in scene["actions"]:
        light = _get("lights", item["target"]["rid"], account_id)
        if light is None:
            continue
        body = {k: v for k, v in item["action"].items() if k in ("on", "dimming", "color_temperature", "color")}
        if override is not None and body.get("on", {}).get("on"):
            body["dimming"] = {"brightness": float(override)}
        if light["kind"] == "white":
            body.pop("color_temperature", None)
            body.pop("color", None)
        elif light["kind"] == "ambiance":
            body.pop("color", None)
        fields = _changes(light, body)
        if isinstance(fields, HueError):
            return fields
        _store.table("lights").patch(light["id"], fields)
    _deactivate(scene["group"]["rid"], account_id, keep=scene_id)
    status = "dynamic_palette" if action == "dynamic_palette" else "static"
    _store.table("scenes").patch(scene_id, {"status": {"active": status, "last_recall": _now()}})
    return _envelope([{"rid": scene_id, "rtype": "scene"}])


_store.eager_load()
