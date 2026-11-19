"""FastAPI server wrapping google_contacts_data as REST endpoints.

Mirrors the Google People API v1 (people.googleapis.com/v1) for the six
operations the connector needs: list contacts, get a contact, search contacts
by name, email or phone, create a contact, update a contact, and delete a
contact. Every operation needs a bearer token from POST /oauth/token, and each
one checks its own scope, so a connected account is not by itself permission
to edit. Errors use Google's own envelope, including request validation
failures and query parameters the method does not take, which Google refuses
rather than ignores.
"""

import json
import re
from typing import List, Literal, Optional

from fastapi import Depends, FastAPI, Query, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

import google_contacts_data
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
auth = google_contacts_data.auth
GoogleError = google_contacts_data.GoogleError

app = FastAPI(title="Google Contacts API (Mock)", version="v1")
install_tracker(app)
install_admin_plane(app, store=google_contacts_data._store)
auth.install(app)

SHARED_PLANES = ("/admin", "/audit")
ENUM_TYPES = {"sortOrder": "ListConnectionsRequest.SortOrder"}
SCALAR_TYPES = (("int", "TYPE_INT32"), ("bool", "TYPE_BOOL"), ("string", "TYPE_STRING"), ("float", "TYPE_DOUBLE"))


class GoogleApiError(Exception):
    def __init__(self, error: GoogleError):
        super().__init__(error.body["error"]["message"])
        self.error = error


def _render(error: GoogleError) -> JSONResponse:
    return JSONResponse(status_code=error.status, content=error.body)


def _google_path(parts) -> str:
    out = ""
    for part in parts:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += ("." if out else "") + re.sub(r"(?<!^)(?=[A-Z])", "_", str(part)).lower()
    return out


def _validation_error(exc: RequestValidationError) -> GoogleError:
    err = exc.errors()[0]
    loc = list(err.get("loc") or [])
    where, parts = (loc[0], loc[1:]) if loc else ("body", [])
    kind, value = err.get("type", ""), err.get("input")
    if kind == "json_invalid":
        return GoogleError(400, "Invalid JSON payload received. Unexpected token.", field="")
    if kind == "extra_forbidden" and parts:
        name, parent = str(parts[-1]), parts[:-1]
        path = _google_path(parent)
        message = (f'Invalid JSON payload received. Unknown name "{name}"'
                   + (f" at '{path}'" if path else "") + ": Cannot find field.")
        return GoogleError(400, message, field=path)
    path = _google_path(parts)
    shown = json.dumps(value, default=str)
    if where == "query" and parts and parts[0] in ENUM_TYPES:
        return GoogleError(400, f"Invalid value at '{path}' (type.googleapis.com/google.people.v1."
                                f"{ENUM_TYPES[parts[0]]}), {shown}", field=path)
    scalar = next((name for prefix, name in SCALAR_TYPES if kind.startswith(prefix)), None)
    if scalar:
        return GoogleError(400, f"Invalid value at '{path}' ({scalar}), {shown}", field=path)
    return GoogleError(400, f"Invalid value at '{path}', {shown}", field=path)


@app.exception_handler(GoogleApiError)
async def _google_api_error(_request: Request, exc: GoogleApiError):
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
    return _render(GoogleError(404, "Requested entity was not found."))


def known_query(request: Request):
    """Refuse a query parameter the method does not declare, as Google does, instead of ignoring it."""
    route = request.scope.get("route")
    allowed = {p.alias for p in route.dependant.query_params} if route is not None else set()
    for name in request.query_params.keys():
        if name not in allowed:
            message = (f'Invalid JSON payload received. Unknown name "{name}": Cannot bind query parameter. '
                       f"Field '{name}' could not be found in request message.")
            raise GoogleApiError(GoogleError(400, message, field=""))


STRICT = Depends(known_query)


@app.get("/health")
def health():
    return {"status": "ok"}


def _reply(result):
    if isinstance(result, GoogleError):
        return _render(result)
    return result


def _account(request: Request) -> str:
    return request.state.oauth["account_id"]


# --- request bodies: a Person and the field types the connector writes -------------------

class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Optional[str] = None
    id: Optional[str] = None
    etag: Optional[str] = None
    updateTime: Optional[str] = None


class FieldMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary: Optional[bool] = None
    sourcePrimary: Optional[bool] = None
    verified: Optional[bool] = None
    source: Optional[Source] = None


class PersonMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources: Optional[List[Source]] = None
    objectType: Optional[str] = None


class Name(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: Optional[FieldMetadata] = None
    givenName: Optional[str] = None
    middleName: Optional[str] = None
    familyName: Optional[str] = None
    honorificPrefix: Optional[str] = None
    displayName: Optional[str] = None
    displayNameLastFirst: Optional[str] = None
    unstructuredName: Optional[str] = None


class Nickname(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: Optional[FieldMetadata] = None
    value: Optional[str] = None
    type: Optional[str] = None


class EmailAddress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: Optional[FieldMetadata] = None
    value: Optional[str] = None
    type: Optional[str] = None
    formattedType: Optional[str] = None
    displayName: Optional[str] = None


class PhoneNumber(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: Optional[FieldMetadata] = None
    value: Optional[str] = None
    canonicalForm: Optional[str] = None
    type: Optional[str] = None
    formattedType: Optional[str] = None


class Organization(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: Optional[FieldMetadata] = None
    name: Optional[str] = None
    title: Optional[str] = None
    department: Optional[str] = None
    type: Optional[str] = None
    formattedType: Optional[str] = None


class Address(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: Optional[FieldMetadata] = None
    formattedValue: Optional[str] = None
    type: Optional[str] = None
    formattedType: Optional[str] = None
    streetAddress: Optional[str] = None
    extendedAddress: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    postalCode: Optional[str] = None
    country: Optional[str] = None
    countryCode: Optional[str] = None


class Date(BaseModel):
    model_config = ConfigDict(extra="forbid")

    year: Optional[int] = None
    month: Optional[int] = None
    day: Optional[int] = None


class Birthday(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: Optional[FieldMetadata] = None
    date: Optional[Date] = None


class Biography(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: Optional[FieldMetadata] = None
    value: Optional[str] = None
    contentType: Optional[Literal["TEXT_PLAIN", "CONTENT_TYPE_UNSPECIFIED"]] = None


class Url(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: Optional[FieldMetadata] = None
    value: Optional[str] = None
    type: Optional[str] = None
    formattedType: Optional[str] = None


class ContactGroupMembership(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contactGroupId: Optional[str] = None
    contactGroupResourceName: Optional[str] = None


class Membership(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: Optional[FieldMetadata] = None
    contactGroupMembership: Optional[ContactGroupMembership] = None


class Person(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resourceName: Optional[str] = None
    etag: Optional[str] = None
    metadata: Optional[PersonMetadata] = None
    names: Optional[List[Name]] = None
    nicknames: Optional[List[Nickname]] = None
    emailAddresses: Optional[List[EmailAddress]] = None
    phoneNumbers: Optional[List[PhoneNumber]] = None
    organizations: Optional[List[Organization]] = None
    addresses: Optional[List[Address]] = None
    birthdays: Optional[List[Birthday]] = None
    biographies: Optional[List[Biography]] = None
    urls: Optional[List[Url]] = None
    memberships: Optional[List[Membership]] = None


def _person(body: Optional[Person]) -> dict:
    return body.model_dump(exclude_none=True) if body else {}


# --- people.connections.list ---------------------------------------------------------------

@app.get(V + "/people/me/connections", dependencies=[auth.require("contacts.readonly", implied_by=("contacts",)), STRICT])
def list_connections(
    request: Request,
    personFields: Optional[str] = None,
    pageSize: int = 100,
    pageToken: Optional[str] = None,
    sortOrder: Literal["LAST_MODIFIED_ASCENDING", "LAST_MODIFIED_DESCENDING", "FIRST_NAME_ASCENDING",
                       "LAST_NAME_ASCENDING"] = Query("LAST_MODIFIED_ASCENDING"),
):
    return _reply(google_contacts_data.list_connections(_account(request), personFields, page_size=pageSize,
                                                        page_token=pageToken, sort_order=sortOrder))


# --- people.searchContacts -------------------------------------------------------------------

@app.get(V + "/people:searchContacts", dependencies=[auth.require("contacts.readonly", implied_by=("contacts",)), STRICT])
def search_contacts(request: Request, query: Optional[str] = None, readMask: Optional[str] = None,
                    pageSize: int = 10):
    if query is None:
        return _render(GoogleError(400, "query is required.", field="query"))
    return _reply(google_contacts_data.search_contacts(_account(request), query, readMask, page_size=pageSize))


# --- people.get --------------------------------------------------------------------------------

@app.get(V + "/people/{personId}", dependencies=[auth.require("contacts.readonly", implied_by=("contacts",)), STRICT])
def get_person(personId: str, request: Request, personFields: Optional[str] = None):
    return _reply(google_contacts_data.get_person(personId, _account(request), personFields))


# --- people.createContact ----------------------------------------------------------------------

@app.post(V + "/people:createContact", dependencies=[auth.require("contacts"), STRICT])
def create_contact(request: Request, body: Optional[Person] = None, personFields: Optional[str] = None):
    return _reply(google_contacts_data.create_contact(_account(request), _person(body), personFields))


# --- people.updateContact ----------------------------------------------------------------------

@app.patch(V + "/people/{personId}:updateContact", dependencies=[auth.require("contacts"), STRICT])
def update_contact(personId: str, request: Request, body: Optional[Person] = None,
                   updatePersonFields: Optional[str] = None, personFields: Optional[str] = None):
    return _reply(google_contacts_data.update_contact(personId, _account(request), _person(body),
                                                      updatePersonFields, personFields))


# --- people.deleteContact ----------------------------------------------------------------------

@app.delete(V + "/people/{personId}:deleteContact", dependencies=[auth.require("contacts"), STRICT])
def delete_contact(personId: str, request: Request):
    return _reply(google_contacts_data.delete_contact(personId, _account(request)))
