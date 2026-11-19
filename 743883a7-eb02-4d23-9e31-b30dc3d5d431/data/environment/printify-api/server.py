"""FastAPI server wrapping printify_data as REST endpoints.

Mirrors the Printify API v1 (api.printify.com/v1) for the seven operations the
connector needs: list shops, list a shop's products, get a product, create a
product from a catalog blueprint, publish a product, list orders, and get an
order. Every operation needs a bearer token from POST /oauth/token and checks
its own scope, so a connected account is not by itself permission to create or
publish. Errors use Printify's body ({"status": "error", "code", "message",
"errors": {"reason", "code"}}), request validation failures included, and a
query parameter the operation does not take is a 400 rather than ignored.
"""

import json
from typing import List, Optional

from fastapi import Depends, FastAPI, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

import printify_data
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
auth = printify_data.auth
PrintifyError = printify_data.PrintifyError

app = FastAPI(title="Printify API (Mock)", version="v1")
install_tracker(app)
install_admin_plane(app, store=printify_data._store)
auth.install(app)

SHARED_PLANES = ("/admin", "/audit")
EXPECTED = (("bool", "must be true or false"), ("int", "must be an integer"), ("float", "must be a number"),
            ("string", "must be a string"), ("list", "must be an array"), ("dict", "must be an object"),
            ("model", "must be an object"))


class PrintifyApiError(Exception):
    def __init__(self, error: PrintifyError):
        super().__init__(error.body["message"])
        self.error = error


def _render(error: PrintifyError) -> JSONResponse:
    return JSONResponse(status_code=error.status, content=error.body)


def _validation_error(exc: RequestValidationError) -> PrintifyError:
    err = exc.errors()[0]
    loc = [str(p) for p in (err.get("loc") or ())]
    name = ".".join(loc[1:]) or (loc[0] if loc else "body")
    kind = err.get("type", "")
    if kind == "json_invalid":
        return printify_data.invalid("body: The request body must be valid JSON.")
    if kind == "missing":
        return printify_data.invalid(f"{name}: The {name} field is required.")
    if kind == "extra_forbidden":
        return printify_data.invalid(f"{name}: The {name} field is not allowed.")
    message = next((text for prefix, text in EXPECTED if kind.startswith(prefix)), "is invalid")
    return printify_data.invalid(f"{name}: The {name} field {message}, got {json.dumps(err.get('input'), default=str)}.")


@app.exception_handler(PrintifyApiError)
async def _printify_api_error(_request: Request, exc: PrintifyApiError):
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
        return _render(PrintifyError(405, 8151, "Method not allowed.",
                                     f"{request.method} is not allowed on {request.url.path}."))
    return _render(PrintifyError(404, 8203, "Not found.", f"{request.url.path} is not an API endpoint."))


def known_query(request: Request):
    """Refuse a query parameter the operation does not declare instead of ignoring it."""
    route = request.scope.get("route")
    allowed = {p.alias for p in route.dependant.query_params} if route is not None else set()
    for name in request.query_params.keys():
        if name not in allowed:
            raise PrintifyApiError(printify_data.invalid(
                f"{name}: {name} is not a parameter this operation takes; this mock refuses it rather than ignore "
                "it, so a misspelt filter cannot pass for one that worked."))


STRICT = Depends(known_query)


@app.get("/health")
def health():
    return {"status": "ok"}


def _reply(result):
    if isinstance(result, PrintifyError):
        return _render(result)
    return result


def _account(request: Request) -> str:
    return request.state.oauth["account_id"]


# --- shops / products ---------------------------------------------------------------------------

@app.get(V + "/shops.json", dependencies=[auth.require("shops.read"), STRICT])
def list_shops(request: Request):
    return printify_data.list_shops(_account(request))


@app.get(V + "/shops/{shop_id}/products.json", dependencies=[auth.require("products.read"), STRICT])
def list_products(shop_id: str, request: Request, page: int = 1, limit: int = 10):
    return _reply(printify_data.list_products(shop_id, _account(request), page=page, limit=limit))


@app.get(V + "/shops/{shop_id}/products/{product_id}.json", dependencies=[auth.require("products.read"), STRICT])
def get_product(shop_id: str, product_id: str, request: Request):
    return _reply(printify_data.get_product(shop_id, product_id, _account(request)))


class ProductVariant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    price: int
    is_enabled: Optional[bool] = None


class PlacedImage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    x: float
    y: float
    scale: float
    angle: int


class Placeholder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: str
    images: List[PlacedImage]


class PrintArea(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variant_ids: List[int]
    placeholders: List[Placeholder]
    background: Optional[str] = None


class CreateProductBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    description: str
    blueprint_id: int
    print_provider_id: int
    variants: List[ProductVariant]
    print_areas: List[PrintArea]
    tags: Optional[List[str]] = None


@app.post(V + "/shops/{shop_id}/products.json", dependencies=[auth.require("products.write"), STRICT])
def create_product(shop_id: str, body: CreateProductBody, request: Request):
    return _reply(printify_data.create_product(shop_id, _account(request), body.model_dump(exclude_none=True)))


class PublishBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: bool
    description: bool
    images: bool
    variants: bool
    tags: bool
    keyFeatures: bool
    shipping_template: bool


@app.post(V + "/shops/{shop_id}/products/{product_id}/publish.json",
          dependencies=[auth.require("products.write"), STRICT])
def publish_product(shop_id: str, product_id: str, body: PublishBody, request: Request):
    return _reply(printify_data.publish_product(shop_id, product_id, _account(request), body.model_dump()))


# --- orders ---------------------------------------------------------------------------------------

@app.get(V + "/shops/{shop_id}/orders.json", dependencies=[auth.require("orders.read"), STRICT])
def list_orders(shop_id: str, request: Request, page: int = 1, limit: int = 10, status: Optional[str] = None,
                sku: Optional[str] = None):
    return _reply(printify_data.list_orders(shop_id, _account(request), page=page, limit=limit, status=status,
                                            sku=sku))


@app.get(V + "/shops/{shop_id}/orders/{order_id}.json", dependencies=[auth.require("orders.read"), STRICT])
def get_order(shop_id: str, order_id: str, request: Request):
    return _reply(printify_data.get_order(shop_id, order_id, _account(request)))
