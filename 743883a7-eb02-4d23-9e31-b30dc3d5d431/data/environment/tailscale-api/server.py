"""FastAPI server wrapping tailscale_data as REST endpoints.

Mirrors the Tailscale API v2 (api.tailscale.com/api/v2) for the six operations
the connector needs: list the tailnet's devices, get a device, authorize a
device, remove a device, read the access policy, and create an auth key, plus
Tailscale's get-key route, served as the read that shows a created key. Every
operation needs a bearer token from POST /oauth/token and checks its own scope,
so a connected account is not by itself permission to admit or remove a
device. Errors use Tailscale's body ({"message"}), request validation failures
included, and a query parameter the operation does not take is a 400 rather
than ignored.
"""

import json
from typing import List, Optional

from fastapi import Depends, FastAPI, Request, Response
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

import tailscale_data
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

V = "/api/v2"
auth = tailscale_data.auth
TailscaleError = tailscale_data.TailscaleError

app = FastAPI(title="Tailscale API (Mock)", version="v2")
install_tracker(app)
install_admin_plane(app, store=tailscale_data._store)
auth.install(app)

SHARED_PLANES = ("/admin", "/audit")
EXPECTED = (("bool", "must be a boolean"), ("int", "must be an integer"), ("string", "must be a string"),
            ("list", "must be an array"), ("model", "must be an object"), ("dict", "must be an object"))


class TailscaleApiError(Exception):
    def __init__(self, error: TailscaleError):
        super().__init__(error.body["message"])
        self.error = error


def _render(error: TailscaleError) -> JSONResponse:
    return JSONResponse(status_code=error.status, content=error.body)


def _validation_error(exc: RequestValidationError) -> TailscaleError:
    err = exc.errors()[0]
    loc = [str(p) for p in (err.get("loc") or ())]
    name = ".".join(loc[1:]) or (loc[0] if loc else "body")
    kind = err.get("type", "")
    if kind == "json_invalid":
        return tailscale_data.invalid("invalid JSON in the request body")
    if kind == "missing":
        return tailscale_data.invalid(f"{name} is required")
    if kind == "extra_forbidden":
        return tailscale_data.invalid(f"json: unknown field \"{loc[-1]}\" in {'.'.join(loc[1:-1]) or 'body'}")
    message = next((text for prefix, text in EXPECTED if kind.startswith(prefix)), "is invalid")
    return tailscale_data.invalid(f"{name} {message}, got {json.dumps(err.get('input'), default=str)}")


@app.exception_handler(TailscaleApiError)
async def _tailscale_api_error(_request: Request, exc: TailscaleApiError):
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
        return _render(TailscaleError(405, "method not allowed"))
    return _render(TailscaleError(404, "not found"))


def known_query(request: Request):
    """Refuse a query parameter the operation does not declare instead of ignoring it."""
    route = request.scope.get("route")
    allowed = {p.alias for p in route.dependant.query_params} if route is not None else set()
    for name in request.query_params.keys():
        if name not in allowed:
            raise TailscaleApiError(tailscale_data.invalid(
                f"unknown query parameter {name!r}; this mock refuses it rather than ignore it, so a misspelt "
                "filter cannot pass for one that worked"))


STRICT = Depends(known_query)


@app.get("/health")
def health():
    return {"status": "ok"}


def _reply(result):
    if isinstance(result, TailscaleError):
        return _render(result)
    if result is None:
        return Response(status_code=200)
    return result


def _account(request: Request) -> str:
    return request.state.oauth["account_id"]


# --- devices ------------------------------------------------------------------------------------

@app.get(V + "/tailnet/{tailnet}/devices", dependencies=[auth.require("devices:core:read"), STRICT])
def list_devices(tailnet: str, request: Request, fields: Optional[str] = None):
    return _reply(tailscale_data.list_devices(tailnet, _account(request), fields=fields))


@app.get(V + "/device/{device_id}", dependencies=[auth.require("devices:core:read"), STRICT])
def get_device(device_id: str, request: Request, fields: Optional[str] = None):
    return _reply(tailscale_data.get_device(device_id, _account(request), fields=fields))


class AuthorizeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authorized: bool


@app.post(V + "/device/{device_id}/authorized", dependencies=[auth.require("devices:core"), STRICT])
def authorize_device(device_id: str, body: AuthorizeBody, request: Request):
    return _reply(tailscale_data.authorize_device(device_id, _account(request), body.authorized))


@app.delete(V + "/device/{device_id}", dependencies=[auth.require("devices:core"), STRICT])
def delete_device(device_id: str, request: Request):
    return _reply(tailscale_data.delete_device(device_id, _account(request)))


# --- policy file --------------------------------------------------------------------------------

@app.get(V + "/tailnet/{tailnet}/acl", dependencies=[auth.require("policy_file:read"), STRICT])
def read_policy(tailnet: str, request: Request):
    result = tailscale_data.read_policy(tailnet, _account(request))
    if isinstance(result, TailscaleError):
        return _render(result)
    document, etag = result
    return JSONResponse(content=document, headers={"ETag": etag})


# --- auth keys ----------------------------------------------------------------------------------

class CreateCapability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reusable: Optional[bool] = None
    ephemeral: Optional[bool] = None
    preauthorized: Optional[bool] = None
    tags: Optional[List[str]] = None


class DeviceCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    create: CreateCapability


class KeyCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    devices: DeviceCapabilities


class CreateKeyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capabilities: KeyCapabilities
    expirySeconds: Optional[int] = None
    description: Optional[str] = None


@app.post(V + "/tailnet/{tailnet}/keys", dependencies=[auth.require("auth_keys"), STRICT])
def create_key(tailnet: str, body: CreateKeyBody, request: Request):
    create = body.capabilities.devices.create.model_dump(exclude_none=True)
    return _reply(tailscale_data.create_key(tailnet, _account(request), create, expiry_seconds=body.expirySeconds,
                                            description=body.description))


@app.get(V + "/tailnet/{tailnet}/keys/{key_id}", dependencies=[auth.require("auth_keys:read"), STRICT])
def get_key(tailnet: str, key_id: str, request: Request):
    return _reply(tailscale_data.get_key(tailnet, key_id, _account(request)))
