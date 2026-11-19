"""FastAPI server wrapping flightaware_data as REST endpoints.

Mirrors the FlightAware AeroAPI v4 (/aeroapi) for the four operations the
client lists: service reachability, flight status, airport delays, and airport
weather. Every operation needs a bearer token from POST /oauth/token; the ping
admits any live token, and each other operation checks its own scope. All routes
are read-only.
"""

from typing import Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse

import flightaware_data
try:
    from tracking_middleware import install_tracker
    from admin_plane import install_admin_plane
except ModuleNotFoundError as _shared_plane_err:  # standalone run without the shared module on sys.path
    import logging as _logging
    _logging.error("SHARED PLANE MISSING - audit + admin disabled: %s", _shared_plane_err)
    def install_tracker(app):  # no-op fallback: audit endpoints disabled
        return None

    def install_admin_plane(app, store=None, one_shot_registry=None):
        return None

V = "/aeroapi"
auth = flightaware_data.auth

app = FastAPI(title="FlightAware AeroAPI (Mock)", version="4")
install_tracker(app)
install_admin_plane(app, store=flightaware_data._store)
auth.install(app)


@app.get("/health")
def health():
    return {"status": "ok"}


def _reply(result):
    if isinstance(result, flightaware_data.AeroError):
        return JSONResponse(status_code=result.status, content=result.body)
    return result


# --- reachability ---------------------------------------------------------------------

@app.get(V + "/ping", dependencies=[auth.require(None)])
def ping():
    return flightaware_data.ping()


# --- flight status --------------------------------------------------------------------

@app.get(V + "/flights/{ident}", dependencies=[auth.require("flights.read")])
def get_flights(ident: str, start: Optional[str] = None, end: Optional[str] = None):
    return _reply(flightaware_data.get_flights(ident, start=start, end=end))


# --- airport delays and weather ---------------------------------------------------------

@app.get(V + "/airports/{id}/delays", dependencies=[auth.require("airports.read")])
def get_airport_delays(id: str):
    return _reply(flightaware_data.get_airport_delays(id))


@app.get(V + "/airports/{id}/weather/observations", dependencies=[auth.require("airports.read")])
def get_airport_observations(id: str):
    return _reply(flightaware_data.get_observations(id))
