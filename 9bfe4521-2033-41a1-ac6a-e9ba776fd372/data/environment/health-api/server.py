"""FastAPI server wrapping health_data as REST endpoints.

Mirrors a normalized health-records REST API (/v1) for the four connector
operations the client ranks: measurements, nutrition, sleep, workouts. Every
operation needs a bearer token from POST /oauth/token, and each one checks its
own scope, so a connected account is not by itself permission to read every
record type. All routes are read-only.
"""

from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

import health_data
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

V = "/v1"
auth = health_data.auth

app = FastAPI(title="Health Records API (Mock)", version="1")
install_tracker(app)
install_admin_plane(app, store=health_data._store)
auth.install(app)


@app.get("/health")
def health():
    return {"status": "ok"}


def _reply(result):
    if isinstance(result, health_data.HealthError):
        return JSONResponse(status_code=result.status, content=result.body)
    return result


def _account(request: Request) -> str:
    return request.state.oauth["account_id"]


# --- .query ---------------------------------------------------------------------------

@app.get(V + "/measurements", dependencies=[auth.require("health.measurements.read")])
def get_measurements(
    request: Request,
    type: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    aggregate: Optional[str] = None,
):
    return _reply(health_data.get_measurements(_account(request), type, start=start, end=end,
                                               aggregate=aggregate))


# --- .nutrition -----------------------------------------------------------------------

@app.get(V + "/nutrition", dependencies=[auth.require("health.nutrition.read")])
def get_nutrition(
    request: Request,
    start: Optional[str] = None,
    end: Optional[str] = None,
    meal: Optional[str] = None,
):
    return _reply(health_data.get_nutrition(_account(request), start=start, end=end, meal=meal))


# --- .sleep ---------------------------------------------------------------------------

@app.get(V + "/sleep", dependencies=[auth.require("health.sleep.read")])
def get_sleep(
    request: Request,
    start: Optional[str] = None,
    end: Optional[str] = None,
):
    return _reply(health_data.get_sleep(_account(request), start=start, end=end))


# --- .workouts ------------------------------------------------------------------------

@app.get(V + "/workouts", dependencies=[auth.require("health.workouts.read")])
def get_workouts(
    request: Request,
    start: Optional[str] = None,
    end: Optional[str] = None,
    type: Optional[str] = None,
):
    return _reply(health_data.get_workouts(_account(request), start=start, end=end, type_=type))
