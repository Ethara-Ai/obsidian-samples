"""FastAPI server wrapping google_drive_data as REST endpoints.

Mirrors the Google Drive API v3 (www.googleapis.com/drive/v3) for the seven
connector operations the client ranks. Every operation needs a bearer token from
POST /oauth/token, and each one checks its own scope, so a connected account is
not by itself permission to share or modify files. File content is uploaded as
Drive takes it, raw (uploadType=media) or as a multipart body of metadata and
content (uploadType=multipart), or as this mock's JSON body carrying text in
``content``, and downloaded with alt=media.
"""

import base64
import json
import re
from typing import List, Optional

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, ValidationError

import google_drive_data
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

D = "/drive/v3"
U = "/upload/drive/v3"
auth = google_drive_data.auth

app = FastAPI(title="Google Drive API (Mock)", version="v3")
install_tracker(app)
install_admin_plane(app, store=google_drive_data._store)
auth.install(app)


@app.get("/health")
def health():
    return {"status": "ok"}


def _reply(result):
    if isinstance(result, google_drive_data.DriveError):
        return JSONResponse(status_code=result.status, content=result.body)
    return result


def _account(request: Request) -> str:
    return request.state.oauth["account_id"]


# --- .list / .search / .files (read) ----------------------------------------------------

@app.get(D + "/files", dependencies=[auth.require("drive.readonly")])
def list_files(
    request: Request,
    q: Optional[str] = None,
    pageSize: Optional[int] = None,
    pageToken: Optional[str] = None,
    orderBy: Optional[str] = None,
    fields: Optional[str] = None,
):
    return _reply(google_drive_data.list_files(_account(request), q=q, page_size=pageSize,
                                               page_token=pageToken, order_by=orderBy, fields=fields))


@app.get(D + "/files/{fileId}", dependencies=[auth.require("drive.readonly")])
def get_file(fileId: str, request: Request, fields: Optional[str] = None, alt: Optional[str] = None):
    if alt == "media":
        result = google_drive_data.download_file(fileId, _account(request))
        if isinstance(result, tuple):
            return Response(content=result[0], media_type=result[1])
        return _reply(result)
    if alt not in (None, "json"):
        return _reply(google_drive_data.DriveError(
            400, f"Invalid value '{alt}'. Values must be within the range: [json, media]", "invalidParameter", "alt"))
    return _reply(google_drive_data.get_file(fileId, _account(request), fields=fields))


@app.get(D + "/files/{fileId}/export", dependencies=[auth.require("drive.readonly")])
def export_file(fileId: str, request: Request, mimeType: Optional[str] = None):
    result = google_drive_data.export_file(fileId, _account(request), mimeType)
    if isinstance(result, str):
        return Response(content=result, media_type="text/plain; charset=utf-8")
    return _reply(result)


# --- .files (create / update) -------------------------------------------------------------

class FileMetadataBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    mimeType: Optional[str] = None
    parents: Optional[List[str]] = None
    description: Optional[str] = None
    starred: Optional[bool] = None


@app.post(D + "/files", dependencies=[auth.require("drive.file")])
def create_file(body: FileMetadataBody, request: Request):
    return _reply(google_drive_data.create_file(
        _account(request), name=body.name, mime_type=body.mimeType, parents=body.parents,
        description=body.description, starred=body.starred,
    ))


class FileChangesBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    description: Optional[str] = None
    starred: Optional[bool] = None
    trashed: Optional[bool] = None


@app.patch(D + "/files/{fileId}", dependencies=[auth.require("drive.file")])
def update_file(
    fileId: str,
    request: Request,
    body: Optional[FileChangesBody] = None,
    addParents: Optional[str] = None,
    removeParents: Optional[str] = None,
):
    sent = body.model_fields_set if body is not None else set()
    changes = {key: getattr(body, key) for key in sent}
    return _reply(google_drive_data.update_file(fileId, _account(request), changes,
                                                add_parents=addParents, remove_parents=removeParents))


@app.delete(D + "/files/{fileId}", status_code=204, response_class=Response,
            dependencies=[auth.require("drive.file")])
def delete_file(fileId: str, request: Request):
    result = google_drive_data.delete_file(fileId, _account(request))
    return _reply(result) if result is not None else Response(status_code=204)


# --- .upload --------------------------------------------------------------------------------

class UploadBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    mimeType: str
    content: str
    parents: Optional[List[str]] = None
    description: Optional[str] = None


class UploadChangeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str
    name: Optional[str] = None
    mimeType: Optional[str] = None
    description: Optional[str] = None


class UploadMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    mimeType: Optional[str] = None
    parents: Optional[List[str]] = None
    description: Optional[str] = None


def _validated(model, data):
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise RequestValidationError([{**e, "loc": ("body", *e["loc"])} for e in exc.errors(include_url=False)])


def _parts(body: bytes, content_type: str):
    """The (headers, bytes) parts of a multipart body, its delimiting CRLFs removed, or None."""
    found = re.search(r'boundary="?([^";]+)"?', content_type)
    if not found:
        return None
    parts = []
    for chunk in body.split(b"--" + found.group(1).encode("latin-1"))[1:]:
        if chunk.startswith(b"--"):
            break
        chunk = chunk[2:] if chunk.startswith(b"\r\n") else chunk[1:] if chunk.startswith(b"\n") else chunk
        chunk = chunk[:-2] if chunk.endswith(b"\r\n") else chunk[:-1] if chunk.endswith(b"\n") else chunk
        head, sep, payload = chunk.partition(b"\r\n\r\n")
        if not sep:
            head, sep, payload = chunk.partition(b"\n\n")
        headers = {}
        for line in head.decode("latin-1").splitlines():
            key, colon, value = line.partition(":")
            if colon:
                headers[key.strip().lower()] = value.strip()
        if headers.get("content-transfer-encoding", "").lower() == "base64":
            payload = base64.b64decode(payload)
        parts.append((headers, payload))
    return parts


def _bad_upload(message):
    return google_drive_data.DriveError(400, message, "badRequest", "uploadType")


async def _upload(request: Request, upload_type: Optional[str], json_model):
    """(metadata, content, content type) of an upload in any of its forms, or a DriveError.

    uploadType=media: the body is the content. uploadType=multipart: a multipart/related (or form-data)
    body whose first part is the JSON metadata and second part the content. A JSON body carrying text in
    ``content``, with uploadType=multipart or none, is this mock's own form."""
    body = await request.body()
    content_type = request.headers.get("content-type", "")
    base = content_type.split(";", 1)[0].strip().lower()
    if upload_type == "media":
        return {}, body, base or "application/octet-stream"
    if upload_type not in (None, "multipart"):
        return google_drive_data.DriveError(
            400, f"Unsupported uploadType '{upload_type}': this mock accepts media, multipart, or the JSON "
                 "upload body.", "invalid", "uploadType")
    if base in ("multipart/related", "multipart/form-data"):
        if upload_type != "multipart":
            return _bad_upload("A multipart body needs uploadType=multipart.")
        parts = _parts(body, content_type)
        if not parts or len(parts) != 2:
            return _bad_upload("A multipart upload has two parts: the JSON metadata, then the content.")
        (_, raw), (headers, media) = parts
        try:
            metadata = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, ValueError):
            return _bad_upload("The first part of a multipart upload must be the file's JSON metadata.")
        fields = _validated(UploadMetadata, metadata).model_dump(exclude_unset=True)
        media_type = headers.get("content-type", "application/octet-stream").split(";", 1)[0].strip()
        return fields, media, media_type
    if base in ("application/json", ""):
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise RequestValidationError([{"type": "json_invalid", "loc": ("body", 0), "msg": "JSON decode error",
                                           "input": {}, "ctx": {"error": str(exc)}}])
        fields = _validated(json_model, data).model_dump(exclude_unset=True)
        return fields, fields.pop("content"), fields.get("mimeType")
    return _bad_upload("Send the file's bytes with uploadType=media, metadata and content as a multipart body "
                       "with uploadType=multipart, or a JSON body with its text in content.")


@app.post(U + "/files", dependencies=[auth.require("drive.file")])
async def upload_file(request: Request, uploadType: Optional[str] = None):
    upload = await _upload(request, uploadType, UploadBody)
    if isinstance(upload, google_drive_data.DriveError):
        return _reply(upload)
    fields, content, media_type = upload
    return _reply(google_drive_data.upload_file(
        _account(request), fields.get("name"), fields.get("mimeType") or media_type, content,
        parents=fields.get("parents"), description=fields.get("description"), upload_type=uploadType,
    ))


@app.patch(U + "/files/{fileId}", dependencies=[auth.require("drive.file")])
async def update_content(fileId: str, request: Request, uploadType: Optional[str] = None):
    upload = await _upload(request, uploadType, UploadChangeBody)
    if isinstance(upload, google_drive_data.DriveError):
        return _reply(upload)
    fields, content, media_type = upload
    return _reply(google_drive_data.update_content(
        fileId, _account(request), content, name=fields.get("name"), mime_type=fields.get("mimeType"),
        description=fields.get("description"),
    ))


# --- .permissions --------------------------------------------------------------------------------

@app.get(D + "/files/{fileId}/permissions", dependencies=[auth.require("drive.readonly")])
def list_permissions(
    fileId: str,
    request: Request,
    pageSize: Optional[int] = None,
    pageToken: Optional[str] = None,
    fields: Optional[str] = None,
):
    return _reply(google_drive_data.list_permissions(fileId, _account(request), page_size=pageSize,
                                                     page_token=pageToken, fields=fields))


class PermissionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    role: str
    emailAddress: Optional[str] = None
    domain: Optional[str] = None
    allowFileDiscovery: Optional[bool] = None


@app.post(D + "/files/{fileId}/permissions", dependencies=[auth.require("drive.sharing")])
def create_permission(fileId: str, body: PermissionBody, request: Request):
    return _reply(google_drive_data.create_permission(
        fileId, _account(request), body.type, body.role, email_address=body.emailAddress,
        domain=body.domain, allow_file_discovery=body.allowFileDiscovery,
    ))


@app.delete(D + "/files/{fileId}/permissions/{permissionId}", status_code=204,
            response_class=Response, dependencies=[auth.require("drive.sharing")])
def delete_permission(fileId: str, permissionId: str, request: Request):
    result = google_drive_data.delete_permission(fileId, permissionId, _account(request))
    return _reply(result) if result is not None else Response(status_code=204)


# --- .comments -----------------------------------------------------------------------------------

@app.get(D + "/files/{fileId}/comments", dependencies=[auth.require("drive.readonly")])
def list_comments(
    fileId: str,
    request: Request,
    pageSize: Optional[int] = None,
    pageToken: Optional[str] = None,
    fields: Optional[str] = None,
):
    return _reply(google_drive_data.list_comments(fileId, _account(request), page_size=pageSize,
                                                  page_token=pageToken, fields=fields))


class QuotedFileContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mimeType: Optional[str] = None
    value: str


class CommentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str
    quotedFileContent: Optional[QuotedFileContent] = None


@app.post(D + "/files/{fileId}/comments", dependencies=[auth.require("drive.file")])
def create_comment(fileId: str, body: CommentBody, request: Request):
    quoted = body.quotedFileContent
    return _reply(google_drive_data.create_comment(
        fileId, _account(request), body.content,
        quoted_value=quoted.value if quoted else None,
        quoted_mime_type=quoted.mimeType if quoted else None,
    ))


# --- .revisions ----------------------------------------------------------------------------------

@app.get(D + "/files/{fileId}/revisions", dependencies=[auth.require("drive.readonly")])
def list_revisions(
    fileId: str,
    request: Request,
    pageSize: Optional[int] = None,
    pageToken: Optional[str] = None,
    fields: Optional[str] = None,
):
    return _reply(google_drive_data.list_revisions(fileId, _account(request), page_size=pageSize,
                                                   page_token=pageToken, fields=fields))


@app.get(D + "/files/{fileId}/revisions/{revisionId}", dependencies=[auth.require("drive.readonly")])
def get_revision(fileId: str, revisionId: str, request: Request, fields: Optional[str] = None):
    return _reply(google_drive_data.get_revision(fileId, revisionId, _account(request), fields=fields))


class RevisionPatchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keepForever: Optional[bool] = None
    published: Optional[bool] = None


@app.patch(D + "/files/{fileId}/revisions/{revisionId}", dependencies=[auth.require("drive.file")])
def update_revision(fileId: str, revisionId: str, body: RevisionPatchBody, request: Request):
    changes = {key: getattr(body, key) for key in body.model_fields_set}
    return _reply(google_drive_data.update_revision(fileId, revisionId, _account(request), changes))
