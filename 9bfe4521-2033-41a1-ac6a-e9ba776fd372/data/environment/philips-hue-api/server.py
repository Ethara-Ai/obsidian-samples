"""FastAPI server wrapping philips_hue_data as REST endpoints.

Mirrors the Philips Hue CLIP API v2 (/clip/v2/resource) for the six operations
the connector needs: list lights, get a light, change a light's on/off state,
brightness and colour, list rooms, list scenes, and recall a scene. Every
operation needs a bearer token from POST /oauth/token in place of the bridge's
application key, and checks its own scope, so seeing the lights is not by
itself permission to change them. Errors use the CLIP v2 envelope ({"data": [],
"errors": [{"description"}]}), request validation failures included, and a
query parameter the operation does not take is a 400 rather than ignored.
"""

from typing import Literal, Optional

from fastapi import Depends, FastAPI, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

import philips_hue_data
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

V = "/clip/v2/resource"
auth = philips_hue_data.auth
HueError = philips_hue_data.HueError

app = FastAPI(title="Philips Hue API (Mock)", version="v2")
install_tracker(app)
install_admin_plane(app, store=philips_hue_data._store)
auth.install(app)

SHARED_PLANES = ("/admin", "/audit")


class HueApiError(Exception):
    def __init__(self, error: HueError):
        super().__init__(error.body["errors"][0]["description"])
        self.error = error


def _render(error: HueError) -> JSONResponse:
    return JSONResponse(status_code=error.status, content=error.body)


def _validation_error(exc: RequestValidationError) -> HueError:
    errors = exc.errors()
    err = next((e for e in errors if e.get("type") == "extra_forbidden"), errors[0])
    loc = [str(p) for p in (err.get("loc") or ())]
    name = ".".join(loc[1:]) or "body"
    kind = err.get("type", "")
    if kind == "json_invalid":
        return philips_hue_data.invalid("body (invalid json)")
    if kind == "extra_forbidden":
        return philips_hue_data.invalid(f"invalid body: unknown property {name}")
    if kind == "missing":
        return philips_hue_data.invalid(f"invalid body: missing property {name}")
    return philips_hue_data.invalid(f"invalid body: {name} {err.get('msg', 'is invalid').lower()}")


@app.exception_handler(HueApiError)
async def _hue_api_error(_request: Request, exc: HueApiError):
    return _render(exc.error)


@app.exception_handler(RequestValidationError)
async def _invalid_request(request: Request, exc: RequestValidationError):
    if request.url.path.startswith(SHARED_PLANES):
        return await request_validation_exception_handler(request, exc)
    return _render(_validation_error(exc))


@app.exception_handler(StarletteHTTPException)
async def _http_error(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith(SHARED_PLANES) or exc.status_code not in (404, 405):
        return await http_exception_handler(request, exc)
    if exc.status_code == 405:
        return _render(HueError(405, "method not available for resource"))
    return _render(philips_hue_data.not_found())


def known_query(request: Request):
    """Refuse a query parameter the operation does not declare instead of ignoring it."""
    route = request.scope.get("route")
    allowed = {p.alias for p in route.dependant.query_params} if route is not None else set()
    for name in request.query_params.keys():
        if name not in allowed:
            raise HueApiError(philips_hue_data.invalid(
                f"unknown query parameter {name}; this mock refuses it rather than ignore it"))


STRICT = Depends(known_query)


@app.get("/health")
def health():
    return {"status": "ok"}


def _reply(result):
    if isinstance(result, HueError):
        return _render(result)
    return result


def _account(request: Request) -> str:
    return request.state.oauth["account_id"]


# --- lights -------------------------------------------------------------------------------------

@app.get(V + "/light", dependencies=[auth.require("hue.read"), STRICT])
def list_lights(request: Request):
    return philips_hue_data.list_lights(_account(request))


@app.get(V + "/light/{light_id}", dependencies=[auth.require("hue.read"), STRICT])
def get_light(light_id: str, request: Request):
    return _reply(philips_hue_data.get_light(light_id, _account(request)))


class On(BaseModel):
    model_config = ConfigDict(extra="forbid")

    on: bool


class Dimming(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brightness: float


class ColorTemperature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mirek: int


class XY(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float
    y: float


class Color(BaseModel):
    model_config = ConfigDict(extra="forbid")

    xy: XY


class Dynamics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    duration: Optional[int] = None


class LightUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    on: Optional[On] = None
    dimming: Optional[Dimming] = None
    color_temperature: Optional[ColorTemperature] = None
    color: Optional[Color] = None
    dynamics: Optional[Dynamics] = None


@app.put(V + "/light/{light_id}", dependencies=[auth.require("hue.control"), STRICT])
def update_light(light_id: str, body: LightUpdate, request: Request):
    changes = body.model_dump(exclude_none=True)
    changes.pop("dynamics", None)
    return _reply(philips_hue_data.update_light(light_id, _account(request), changes))


# --- rooms and scenes ---------------------------------------------------------------------------

@app.get(V + "/room", dependencies=[auth.require("hue.read"), STRICT])
def list_rooms(request: Request):
    return philips_hue_data.list_rooms(_account(request))


@app.get(V + "/scene", dependencies=[auth.require("hue.read"), STRICT])
def list_scenes(request: Request):
    return philips_hue_data.list_scenes(_account(request))


class RecallDimming(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brightness: float


class Recall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Optional[Literal["active", "dynamic_palette", "static"]] = None
    duration: Optional[int] = None
    dimming: Optional[RecallDimming] = None


class SceneUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recall: Recall


@app.put(V + "/scene/{scene_id}", dependencies=[auth.require("hue.control"), STRICT])
def recall_scene(scene_id: str, body: SceneUpdate, request: Request):
    return _reply(philips_hue_data.recall_scene(scene_id, _account(request), body.recall.model_dump(exclude_none=True)))
