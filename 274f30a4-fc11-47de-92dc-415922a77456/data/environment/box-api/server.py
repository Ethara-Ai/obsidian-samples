"""FastAPI server wrapping box_data as REST endpoints.

Mirrors the Box Platform API (api.box.com/2.0, uploads on upload.box.com/api/2.0)
for the six operations the connector needs: list a folder's items, get a file's
details, search by name, create a folder, upload a small file, and create a
shared link for a file. Every operation needs a bearer token from POST
/oauth/token and checks its own scope, so a connected account is not by itself
permission to write. Errors use Box's client error body ({"type": "error",
"status", "code", "context_info", "help_url", "message", "request_id"}),
request validation failures included, and a query parameter the operation does
not take is a 400 rather than ignored. An upload is the multipart body Box
takes (an "attributes" part and a "file" part); a JSON body carrying the same
attributes and the file's text as "content" is accepted too.
"""

import json
from email.parser import BytesParser
from email.policy import HTTP
from typing import Literal, Optional

from fastapi import Depends, FastAPI, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

import box_data
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

V = "/2.0"
U = "/api/2.0"
auth = box_data.auth
BoxError = box_data.BoxError

app = FastAPI(title="Box API (Mock)", version="2.0")
install_tracker(app)
install_admin_plane(app, store=box_data._store)
auth.install(app)

SHARED_PLANES = ("/admin", "/audit")
EXPECTED = (("bool", "must be true or false"), ("int", "must be an integer"), ("string", "must be a string"),
            ("dict", "must be an object"), ("model", "must be an object"), ("list", "must be an array"))


class BoxApiError(Exception):
    def __init__(self, error: BoxError):
        super().__init__(error.body["message"])
        self.error = error


def _render(error: BoxError) -> JSONResponse:
    return JSONResponse(status_code=error.status, content=error.body)


def _box_validation(errors, prefix=()) -> BoxError:
    err = errors[0]
    loc = [str(p) for p in (err.get("loc") or ())]
    kind = err.get("type", "")
    if kind == "json_invalid":
        return box_data.invalid("body", "Could not parse the JSON request body")
    name = ".".join(list(prefix) + (loc[1:] if loc and loc[0] in ("body", "query", "path") else loc)) or "body"
    shown = json.dumps(err.get("input"), default=str)
    if kind == "extra_forbidden":
        return box_data.invalid(name, f"Invalid value {shown}. '{name}' is not a field this operation takes")
    if kind == "missing":
        return box_data.invalid(name, f"'{name}' is required")
    if kind == "literal_error":
        return box_data.invalid(name, f"Invalid value {shown}. {err.get('msg', '')}")
    message = next((text for p, text in EXPECTED if kind.startswith(p)), "is not valid")
    return box_data.invalid(name, f"Invalid value {shown}. '{name}' {message}")


@app.exception_handler(BoxApiError)
async def _box_api_error(_request: Request, exc: BoxApiError):
    return _render(exc.error)


@app.exception_handler(RequestValidationError)
async def _invalid_request(request: Request, exc: RequestValidationError):
    if request.url.path.startswith(SHARED_PLANES):
        return await request_validation_exception_handler(request, exc)
    return _render(_box_validation(exc.errors()))


@app.exception_handler(StarletteHTTPException)
async def _http_error(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith(SHARED_PLANES) or exc.status_code not in (404, 405):
        return await http_exception_handler(request, exc)
    if exc.status_code == 405:
        return _render(BoxError(405, "method_not_allowed", "Method Not Allowed"))
    return _render(BoxError(404, "not_found", "Not Found"))


def known_query(request: Request):
    """Refuse a query parameter the operation does not declare instead of ignoring it."""
    route = request.scope.get("route")
    allowed = {p.alias for p in route.dependant.query_params} if route is not None else set()
    for name in request.query_params.keys():
        if name not in allowed:
            raise BoxApiError(box_data.invalid(
                name, f"'{name}' is not a parameter this operation takes; this mock refuses it rather than "
                      "ignore it, so a misspelt filter cannot pass for one that worked"))


STRICT = Depends(known_query)


@app.get("/health")
def health():
    return {"status": "ok"}


def _reply(result, status=200):
    if isinstance(result, BoxError):
        return _render(result)
    return JSONResponse(status_code=status, content=result)


def _account(request: Request) -> str:
    return request.state.oauth["account_id"]


# --- folders.items / files.get / search -------------------------------------------------------

@app.get(V + "/folders/{folder_id}/items", dependencies=[auth.require("root_readonly"), STRICT])
def list_folder_items(folder_id: str, request: Request, fields: Optional[str] = None, limit: int = 100,
                      offset: int = 0, sort: Optional[str] = None, direction: Optional[str] = None):
    return _reply(box_data.list_folder_items(folder_id, _account(request), fields=fields, limit=limit, offset=offset,
                                             sort=sort, direction=direction))


@app.get(V + "/files/{file_id}", dependencies=[auth.require("root_readonly"), STRICT])
def get_file(file_id: str, request: Request, fields: Optional[str] = None):
    return _reply(box_data.get_file(file_id, _account(request), fields=fields))


@app.get(V + "/search", dependencies=[auth.require("root_readonly"), STRICT])
def search(request: Request, query: Optional[str] = None, type: Optional[str] = None,
           file_extensions: Optional[str] = None, ancestor_folder_ids: Optional[str] = None,
           content_types: Optional[str] = None, limit: int = 30, offset: int = 0, fields: Optional[str] = None):
    return _reply(box_data.search(_account(request), query, type=type, file_extensions=file_extensions,
                                  ancestor_folder_ids=ancestor_folder_ids, content_types=content_types, limit=limit,
                                  offset=offset, fields=fields))


# --- folders.create ---------------------------------------------------------------------------

class ParentRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str


class CreateFolderBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    parent: ParentRef


@app.post(V + "/folders", status_code=201, dependencies=[auth.require("root_readwrite"), STRICT])
def create_folder(body: CreateFolderBody, request: Request, fields: Optional[str] = None):
    return _reply(box_data.create_folder(_account(request), body.name, body.parent.id, fields=fields), status=201)


# --- files.upload -----------------------------------------------------------------------------

class UploadAttributes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    parent: ParentRef
    content_created_at: Optional[str] = None
    content_modified_at: Optional[str] = None


class JsonUploadBody(BaseModel):
    """The JSON form of an upload: the multipart attributes, and the file's text as ``content``."""

    model_config = ConfigDict(extra="forbid")

    attributes: UploadAttributes
    content: str


def _multipart_parts(content_type: str, raw: bytes):
    """``{part name: bytes}`` of a multipart/form-data body, or a BoxError."""
    try:
        message = BytesParser(policy=HTTP).parsebytes(
            b"Content-Type: " + content_type.encode("latin-1") + b"\r\n\r\n" + raw)
    except (ValueError, UnicodeEncodeError):
        message = None
    if message is None or not message.is_multipart():
        return box_data.invalid("body", "The multipart body could not be read")
    parts = {}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            return box_data.invalid("body", "Every multipart part needs a Content-Disposition name")
        parts[str(name)] = part.get_payload(decode=True) or b""
    return parts


@app.post(U + "/files/content", status_code=201, dependencies=[auth.require("root_readwrite"), STRICT])
async def upload_file(request: Request, fields: Optional[str] = None):
    content_type = request.headers.get("content-type", "")
    raw = await request.body()
    if content_type.lower().startswith("multipart/form-data"):
        parts = _multipart_parts(content_type, raw)
        if isinstance(parts, BoxError):
            return _render(parts)
        extra = sorted(n for n in parts if n not in ("attributes", "file"))
        if extra:
            return _render(box_data.invalid(extra[0], f"'{extra[0]}' is not a part this endpoint takes; "
                                                      "send an attributes part and a file part"))
        for needed in ("attributes", "file"):
            if needed not in parts:
                return _render(box_data.invalid(needed, f"'{needed}' is required"))
        try:
            attributes = UploadAttributes.model_validate_json(parts["attributes"])
        except ValidationError as exc:
            return _render(_box_validation(exc.errors(include_url=False), prefix=("attributes",)))
        content = parts["file"]
    elif "json" in content_type.lower():
        try:
            body = JsonUploadBody.model_validate_json(raw)
        except ValidationError as exc:
            return _render(_box_validation(exc.errors(include_url=False)))
        attributes, content = body.attributes, body.content.encode("utf-8")
    else:
        return _render(box_data.invalid("body", "Send multipart/form-data with an attributes part and a file part, "
                                                "or a JSON body with attributes and content"))
    return _reply(box_data.upload_file(_account(request), attributes.name, attributes.parent.id, content,
                                       content_created_at=attributes.content_created_at,
                                       content_modified_at=attributes.content_modified_at, fields=fields),
                  status=201)


# --- files.update (add a shared link) ---------------------------------------------------------

class LinkPermissions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    can_download: Optional[bool] = None
    can_preview: Optional[bool] = None
    can_edit: Optional[bool] = None


class SharedLinkSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access: Optional[Literal["open", "company", "collaborators"]] = None
    password: Optional[str] = None
    vanity_name: Optional[str] = None
    unshared_at: Optional[str] = None
    permissions: Optional[LinkPermissions] = None


class SharedLinkBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shared_link: SharedLinkSpec


@app.put(V + "/files/{file_id}", dependencies=[auth.require("root_readwrite"), STRICT])
def add_shared_link(file_id: str, body: SharedLinkBody, request: Request, fields: Optional[str] = None):
    spec = body.shared_link.model_dump(exclude_none=True)
    return _reply(box_data.add_shared_link(file_id, _account(request), spec, fields=fields))
