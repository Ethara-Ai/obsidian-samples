"""Data access module for the Tessie mock service.

Follows Tessie's REST API (api.tessie.com) for the operations the connector
needs: list vehicles, get a vehicle's state, get battery and charging status,
get its location, lock and unlock, start and stop climate, start and stop
charging, and list past drives. Every read and write is scoped to the vehicles
the presented token's connected account holds.

A vehicle row carries the Tesla vehicle data blocks Tessie relays
(charge_state, climate_state, drive_state, vehicle_state, ...), so a command
reads back through the state, battery and vehicle-list routes. Drives are the
trips Tessie logged. Mock simplifications (also stated in api_test_results.md):
no charge limit, temperature, seat heater, sentry, trunk or window commands, no
charging sessions, idles or historical states, and the car's battery does not
move while it charges.
"""

import math
import sys
from datetime import timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent

sys.path.insert(0, str(DATA_DIR.parent))
import _mock_clock  # noqa: E402
from _mutable_store import get_store, read_seed_with_ctx  # noqa: E402
from _connector_auth import ConnectorAuth  # noqa: E402

_API = "tessie-api"
_store = get_store(_API)

LOCATION_SCOPE = "vehicle_location"
LOCATION_FIELDS = ("latitude", "longitude", "heading", "native_latitude", "native_longitude")
STATE_BLOCKS = ("charge_state", "climate_state", "drive_state", "gui_settings", "vehicle_config", "vehicle_state")
CHARGING_FIELDS = ("charging_state", "charge_limit_soc", "charger_power", "charger_voltage", "charger_actual_current",
                   "charge_rate", "charge_energy_added", "minutes_to_full_charge", "time_to_full_charge",
                   "conn_charge_cable", "charge_port_door_open", "scheduled_charging_pending")
# home charging per car: kW drawn and rated miles added per hour at the car's pilot current
CHARGER = {48: (11, 241, 44.9), 32: (8, 240, 36.6)}


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


_store.register("vehicles", primary_key="vin",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("vehicles.json", "vehicles")])
_store.register("drives", primary_key="id",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("drives.json", "drives")])

auth = ConnectorAuth(_API, store=_store, data_dir=DATA_DIR)


class TessieError:
    """This mock's rendering of a Tessie error (``{"error"}``) and its HTTP status."""

    def __init__(self, status, message):
        self.status = status
        self.body = {"error": message}


def invalid(message):
    return TessieError(400, message)


def _vehicle(vin, account_id):
    row = _store.table("vehicles").get(vin)
    if row is None or row.get("owner_account_id") != account_id:
        return None
    return row


def _not_found(vin):
    return TessieError(404, f"No vehicle with VIN {vin} in this Tessie account")


def state_view(row, with_location):
    view = {"id": row["id"], "vehicle_id": row["vehicle_id"], "vin": row["vin"], "color": None,
            "access_type": row["access_type"], "display_name": row["display_name"], "state": row["state"],
            "in_service": row["in_service"], "id_s": str(row["id"]), "calendar_enabled": True,
            "api_version": row["api_version"]}
    for block in STATE_BLOCKS:
        view[block] = dict(row[block])
    if not with_location:
        for key in LOCATION_FIELDS:
            view["drive_state"].pop(key, None)
    return view


# --- vehicles -----------------------------------------------------------------------------------

def list_vehicles(account_id, with_location, only_active=False):
    rows = sorted(_store.table("vehicles").find(lambda r: r.get("owner_account_id") == account_id),
                  key=lambda r: (not r["is_active"], r["display_name"]))
    results = []
    for row in rows:
        if only_active and not row["is_active"]:
            continue
        ended = [d["created_at"] for d in _store.table("drives").find(lambda d: d["vin"] == row["vin"])]
        results.append({"vin": row["vin"], "plate": None, "is_active": row["is_active"],
                        "last_drive_created_at": max(ended) if ended else None,
                        "last_state": state_view(row, with_location)})
    return {"results": results}


def vehicle_state(vin, account_id, with_location):
    row = _vehicle(vin, account_id)
    if row is None:
        return _not_found(vin)
    return state_view(row, with_location)


def battery(vin, account_id):
    row = _vehicle(vin, account_id)
    if row is None:
        return _not_found(vin)
    charge, pack = row["charge_state"], row["battery"]
    level = charge["battery_level"]
    return {"timestamp": charge["timestamp"] // 1000, "battery_level": level, "battery_range": charge["battery_range"],
            "ideal_battery_range": charge["ideal_battery_range"], "phantom_drain_percent": pack["phantom_drain_percent"],
            "energy_remaining": round(level / 100 * pack["usable_kwh"], 1),
            "lifetime_energy_used": pack["lifetime_energy_used"],
            "pack_current": pack["charge_pack_current"] if charge["charging_state"] == "Charging" else
            pack["pack_current"], "pack_voltage": pack["pack_voltage"], "module_temp_min": pack["module_temp_min"],
            "module_temp_max": pack["module_temp_max"],
            "charge_state": {key: charge[key] for key in CHARGING_FIELDS}}


def location(vin, account_id):
    row = _vehicle(vin, account_id)
    if row is None:
        return _not_found(vin)
    drive = row["drive_state"]
    return {"latitude": drive["latitude"], "longitude": drive["longitude"], "address": row["location"]["address"],
            "saved_location": row["location"]["saved_location"]}


# --- drives -------------------------------------------------------------------------------------

def drive_view(row):
    return {k: v for k, v in row.items() if k not in ("vin", "owner_account_id")}


def drives(vin, account_id, start=None, end=None, tag=None, driver_profile=None, minimum_distance=None, limit=None):
    row = _vehicle(vin, account_id)
    if row is None:
        return _not_found(vin)
    if start is not None and end is not None and start > end:
        return invalid("from must not be later than to")
    if minimum_distance is not None and minimum_distance < 0:
        return invalid("minimum_distance must not be negative")
    if limit is not None and limit < 1:
        return invalid("limit must be at least 1")
    wanted_tag = tag.lower() if tag is not None else None
    wanted_driver = driver_profile.lower() if driver_profile is not None else None
    rows = [d for d in _store.table("drives").find(lambda d: d["vin"] == vin)
            if (start is None or d["started_at"] >= start) and (end is None or d["started_at"] <= end)
            and (wanted_tag is None or (d["tag"] or "").lower() == wanted_tag)
            and (wanted_driver is None or (d["driver_profile"] or "").lower() == wanted_driver)
            and (minimum_distance is None or d["odometer_distance"] >= minimum_distance)]
    rows.sort(key=lambda d: d["started_at"], reverse=True)
    if limit is not None:
        rows = rows[:limit]
    return {"results": [drive_view(d) for d in rows]}


# --- commands -----------------------------------------------------------------------------------

def command(vin, account_id, name):
    row = _vehicle(vin, account_id)
    if row is None:
        return _not_found(vin)
    if not row["is_active"]:
        return TessieError(409, f"Vehicle {vin} is no longer active in this Tessie account")
    now = _mock_clock.now(timezone.utc)
    stamp = int(now.timestamp() * 1000)
    woke = row["state"] != "online"
    patch = {"state": "online"}
    reason = None
    if name in ("lock", "unlock"):
        block = dict(row["vehicle_state"], locked=name == "lock", timestamp=stamp)
        patch["vehicle_state"] = block
    elif name in ("start_climate", "stop_climate"):
        on = name == "start_climate"
        block = dict(row["climate_state"], is_climate_on=on, is_auto_conditioning_on=on, is_preconditioning=on,
                     fan_status=4 if on else 0, timestamp=stamp)
        patch["climate_state"] = block
    else:
        charge = dict(row["charge_state"])
        if name == "start_charging":
            if charge["conn_charge_cable"] == "<invalid>":
                reason = "disconnected"
            elif charge["charging_state"] == "Charging":
                reason = "is_charging"
            elif charge["battery_level"] >= charge["charge_limit_soc"]:
                reason = "complete"
            else:
                power, volts, rate = CHARGER[charge["charger_pilot_current"]]
                needed = (charge["charge_limit_soc"] - charge["battery_level"]) / 100 * row["battery"]["usable_kwh"]
                minutes = math.ceil(needed / power * 60)
                charge.update(charging_state="Charging", charger_power=power, charger_voltage=volts,
                              charger_actual_current=charge["charger_pilot_current"], charge_rate=rate,
                              minutes_to_full_charge=minutes, time_to_full_charge=round(minutes / 60, 2),
                              timestamp=stamp)
        elif charge["charging_state"] != "Charging":
            reason = "not_charging"
        else:
            charge.update(charging_state="Stopped", charger_power=0, charger_voltage=0, charger_actual_current=0,
                          charge_rate=0.0, minutes_to_full_charge=0, time_to_full_charge=0.0, timestamp=stamp)
        if reason is None:
            patch["charge_state"] = charge
    _store.table("vehicles").patch(vin, patch)
    if reason is not None:
        return {"result": False, "woke": woke, "reason": reason}
    return {"result": True, "woke": woke}


_store.eager_load()
