"""FastAPI server wrapping notion_data as REST endpoints.

Mirrors the Notion API (api.notion.com/v1, Notion-Version 2022-06-28) for the
operations the connector needs: search pages and databases, get a page,
create a page, update page properties, query a database with a filter and
sorts, list a block's children, and append blocks to a page. Every operation
needs a bearer token from POST /oauth/token and checks one capability scope
(read_content, insert_content or update_content), so a connected account is
not by itself permission to edit. Errors use Notion's error object
({"object": "error", "status", "code", "message"}), request validation
failures included, and a query parameter the endpoint does not take is a 400
rather than ignored.
"""

import json
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

import notion_data
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
auth = notion_data.auth
NotionError = notion_data.NotionError

app = FastAPI(title="Notion API (Mock)", version=notion_data.NOTION_VERSION)
install_tracker(app)
install_admin_plane(app, store=notion_data._store)
auth.install(app)

SHARED_PLANES = ("/admin", "/audit")
EXPECTED = (("bool", "a boolean"), ("int", "an integer"), ("float", "a number"), ("string", "a string"),
            ("list", "an array"), ("dict", "an object"), ("model", "an object"))


class NotionApiError(Exception):
    def __init__(self, error: NotionError):
        super().__init__(error.body["message"])
        self.error = error


def _render(error: NotionError) -> JSONResponse:
    return JSONResponse(status_code=error.status, content=error.body)


def _validation_error(exc: RequestValidationError) -> NotionError:
    err = exc.errors()[0]
    loc = [str(p) for p in (err.get("loc") or ())]
    kind, value = err.get("type", ""), err.get("input")
    if kind == "json_invalid":
        return NotionError(400, "invalid_json", "Error parsing JSON body.")
    where = loc[0] if loc else "body"
    path = ".".join([where] + [f"[{p}]" if p.isdigit() else p for p in loc[1:]]).replace(".[", "[")
    if kind == "missing" and len(loc) <= 1:
        return NotionError(400, "validation_error", f"{where} failed validation: {where} should be an object, "
                                                    "instead was `undefined`.")
    if kind == "missing":
        return NotionError(400, "validation_error", f"{where} failed validation: {path} should be defined, instead "
                                                    "was `undefined`.")
    shown = json.dumps(value, default=str)
    if kind == "extra_forbidden":
        return NotionError(400, "validation_error", f"{where} failed validation: {path} should be not present, "
                                                    f"instead was `{shown}`.")
    expected = next((text for prefix, text in EXPECTED if kind.startswith(prefix)), "valid")
    return NotionError(400, "validation_error", f"{where} failed validation: {path} should be {expected}, instead "
                                                f"was `{shown}`.")


@app.exception_handler(NotionApiError)
async def _notion_api_error(_request: Request, exc: NotionApiError):
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
    return _render(NotionError(400, "invalid_request_url", "Invalid request URL."))


def known_query(request: Request):
    """Refuse a query parameter the endpoint does not declare instead of ignoring it."""
    route = request.scope.get("route")
    allowed = {p.alias for p in route.dependant.query_params} if route is not None else set()
    for name in request.query_params.keys():
        if name not in allowed:
            raise NotionApiError(NotionError(
                400, "validation_error", f"query failed validation: query.{name} should be not present. This mock "
                                         "refuses a query parameter the endpoint does not take, so a misspelt one "
                                         "cannot pass for one that worked."))


def notion_version(version: Optional[str] = Header(None, alias="Notion-Version")):
    """Accept the one API version this mock serves; a request without the header is answered in it too."""
    if version is not None and version.strip() != notion_data.NOTION_VERSION:
        raise NotionApiError(NotionError(
            400, "validation_error", f"Notion-Version header failed validation: this mock serves Notion-Version "
                                     f"{notion_data.NOTION_VERSION}, instead was `{version}`."))


STRICT = Depends(known_query)
VERSION = Depends(notion_version)


@app.get("/health")
def health():
    return {"status": "ok"}


def _reply(result):
    if isinstance(result, NotionError):
        return _render(result)
    return result


def _account(request: Request) -> str:
    return request.state.oauth["account_id"]


def _id(name: str, value: str) -> str:
    canonical = notion_data.canonical_id(value)
    if canonical is None:
        raise NotionApiError(notion_data.bad_path_id(name, value))
    return canonical


# --- search --------------------------------------------------------------------------------------

class SearchFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    property: str
    value: str


class SearchSort(BaseModel):
    model_config = ConfigDict(extra="forbid")

    direction: str
    timestamp: str


class SearchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: Optional[str] = None
    filter: Optional[SearchFilter] = None
    sort: Optional[SearchSort] = None
    start_cursor: Optional[str] = None
    page_size: Optional[int] = None


@app.post(V + "/search", dependencies=[auth.require("read_content"), STRICT, VERSION])
def search(request: Request, body: Optional[SearchBody] = None):
    fields = body.model_dump(exclude_none=True) if body else {}
    return _reply(notion_data.search(_account(request), fields))


# --- pages ---------------------------------------------------------------------------------------

class Parent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Optional[str] = None
    database_id: Optional[str] = None
    page_id: Optional[str] = None


class CreatePageBody(BaseModel):
    """properties, children, icon and cover are checked key by key against the database schema and block types."""

    model_config = ConfigDict(extra="forbid")

    parent: Parent
    properties: Optional[Dict[str, Any]] = None
    children: Optional[List[Any]] = None
    icon: Optional[Dict[str, Any]] = None
    cover: Optional[Dict[str, Any]] = None


class UpdatePageBody(BaseModel):
    """properties, icon and cover are checked key by key against the page's schema."""

    model_config = ConfigDict(extra="forbid")

    properties: Optional[Dict[str, Any]] = None
    archived: Optional[bool] = None
    icon: Optional[Dict[str, Any]] = None
    cover: Optional[Dict[str, Any]] = None


@app.get(V + "/pages/{page_id}", dependencies=[auth.require("read_content"), STRICT, VERSION])
def get_page(page_id: str, request: Request):
    return _reply(notion_data.get_page(_id("page_id", page_id), _account(request)))


@app.post(V + "/pages", dependencies=[auth.require("insert_content"), STRICT, VERSION])
def create_page(request: Request, body: CreatePageBody):
    fields = body.model_dump(exclude_unset=True)
    fields["parent"] = body.parent.model_dump(exclude_none=True)
    return _reply(notion_data.create_page(_account(request), fields))


@app.patch(V + "/pages/{page_id}", dependencies=[auth.require("update_content"), STRICT, VERSION])
def update_page(page_id: str, request: Request, body: UpdatePageBody):
    return _reply(notion_data.update_page(_id("page_id", page_id), _account(request),
                                          body.model_dump(exclude_unset=True)))


# --- databases -----------------------------------------------------------------------------------

class QueryBody(BaseModel):
    """filter and sorts are checked key by key against the database schema."""

    model_config = ConfigDict(extra="forbid")

    filter: Optional[Dict[str, Any]] = None
    sorts: Optional[List[Any]] = None
    start_cursor: Optional[str] = None
    page_size: Optional[int] = None


@app.post(V + "/databases/{database_id}/query", dependencies=[auth.require("read_content"), STRICT, VERSION])
def query_database(database_id: str, request: Request, body: Optional[QueryBody] = None):
    fields = body.model_dump(exclude_none=True) if body else {}
    return _reply(notion_data.query_database(_id("database_id", database_id), _account(request), fields))


# --- blocks --------------------------------------------------------------------------------------

class AppendBody(BaseModel):
    """children are checked key by key against the block types this mock writes."""

    model_config = ConfigDict(extra="forbid")

    children: List[Any]
    after: Optional[str] = None


@app.get(V + "/blocks/{block_id}/children", dependencies=[auth.require("read_content"), STRICT, VERSION])
def list_children(block_id: str, request: Request, start_cursor: Optional[str] = None,
                  page_size: Optional[int] = None):
    return _reply(notion_data.list_children(_id("block_id", block_id), _account(request), start_cursor=start_cursor,
                                            page_size=page_size))


@app.patch(V + "/blocks/{block_id}/children", dependencies=[auth.require("insert_content"), STRICT, VERSION])
def append_children(block_id: str, request: Request, body: AppendBody):
    return _reply(notion_data.append_children(_id("block_id", block_id), _account(request),
                                              body.model_dump(exclude_unset=True)))
