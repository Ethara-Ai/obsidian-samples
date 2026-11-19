"""FastAPI server wrapping outlook_contacts_data as REST endpoints.

Mirrors Microsoft Graph v1.0 (graph.microsoft.com/v1.0) for the contact
operations the connector needs: list contacts (filtered by name or email with
OData $filter), get, create, update and delete a contact. Every operation
needs a bearer token from POST /oauth/token and checks its own scope,
Contacts.Read or Contacts.ReadWrite, so a connected account is not by itself
permission to edit. Errors use Graph's envelope, request validation failures
included, and a query parameter the operation does not take is a 400 rather
than ignored.
"""

from typing import List, Optional

from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

import outlook_contacts_data
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

V = "/v1.0"
auth = outlook_contacts_data.auth
GraphError = outlook_contacts_data.GraphError

app = FastAPI(title="Outlook Contacts API (Mock)", version="v1.0")
install_tracker(app)
install_admin_plane(app, store=outlook_contacts_data._store)
auth.install(app)

SHARED_PLANES = ("/admin", "/audit")
# Graph type names for the nested objects of a request body, keyed by the property holding them.
TYPES = {"emailAddresses": "emailAddress", "homeAddress": "physicalAddress", "businessAddress": "physicalAddress",
         "otherAddress": "physicalAddress"}
EDM = (("bool", "Edm.Boolean"), ("int", "Edm.Int32"), ("string", "Edm.String"), ("list", "Collection"))


class GraphApiError(Exception):
    def __init__(self, error: GraphError):
        super().__init__(error.body["error"]["message"])
        self.error = error


def _render(error: GraphError) -> JSONResponse:
    return JSONResponse(status_code=error.status, content=error.body)


def _validation_error(exc: RequestValidationError) -> GraphError:
    err = exc.errors()[0]
    loc = list(err.get("loc") or ())
    where, parts = (loc[0], loc[1:]) if loc else ("body", [])
    kind, value = err.get("type", ""), err.get("input")
    if where == "query":
        name = str(parts[0]) if parts else ""
        if name in ("$top", "$skip"):
            return GraphError(400, "BadRequest", f"Invalid value '{value}' for {name} query option found. The {name} "
                                                 "query option requires a non-negative integer value.")
        return GraphError(400, "BadRequest", f"The value '{value}' of query parameter '{name}' is not valid.")
    if kind == "json_invalid":
        return GraphError(400, "BadRequest", "Unable to read JSON request payload. Please ensure Content-Type header "
                                             "is set and payload is of valid JSON format.")
    names = [str(p) for p in parts if not isinstance(p, int)]
    if not names:
        if kind == "missing":
            return GraphError(400, "BadRequest", "Empty Payload. JSON content expected.")
        return GraphError(400, "BadRequest", "The request body must be a JSON object.")
    name = names[-1]
    owner = TYPES.get(names[-2], names[-2]) if len(names) > 1 else "contact"
    if kind == "extra_forbidden":
        return GraphError(400, "RequestBodyRead", f"The property '{name}' does not exist on type "
                                                  f"'microsoft.graph.{owner}'. Make sure to only use property names "
                                                  "that are defined by the type or mark the type as open type.")
    if kind == "missing":
        return GraphError(400, "BadRequest", f"The property '{name}' is required on type 'microsoft.graph.{owner}'.")
    expected = next((edm for prefix, edm in EDM if kind.startswith(prefix)), f"microsoft.graph.{TYPES.get(name, name)}")
    return GraphError(400, "RequestBodyRead", f"Cannot convert the literal '{value}' to the expected type '{expected}'.")


@app.exception_handler(GraphApiError)
async def _graph_api_error(_request: Request, exc: GraphApiError):
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
        return _render(GraphError(405, "BadRequest", f"The HTTP method '{request.method}' is not supported for this "
                                                     "resource."))
    segment = request.url.path.rstrip("/").rsplit("/", 1)[-1]
    return _render(GraphError(400, "BadRequest", f"Resource not found for the segment '{segment}'."))


def known_query(request: Request):
    """Refuse a query parameter the operation does not declare instead of ignoring it."""
    route = request.scope.get("route")
    allowed = {p.alias for p in route.dependant.query_params} if route is not None else set()
    for name in request.query_params.keys():
        if name in allowed:
            continue
        if name.startswith("$"):
            message = f"The query parameter '{name}' is not supported."
        else:
            message = (f"The query parameter '{name}' is not supported by this operation. Microsoft Graph ignores a "
                       "parameter it does not know; this mock refuses it, so a misspelt option cannot pass for one "
                       "that worked.")
        raise GraphApiError(GraphError(400, "BadRequest", message))


STRICT = Depends(known_query)


@app.get("/health")
def health():
    return {"status": "ok"}


def _reply(result):
    if isinstance(result, GraphError):
        return _render(result)
    if result is None:
        return Response(status_code=204)
    return result


def _account(request: Request) -> str:
    return request.state.oauth["account_id"]


# --- contacts: list and get -------------------------------------------------------------------

@app.get(V + "/me/contacts", dependencies=[auth.require("Contacts.Read"), STRICT])
def list_contacts(request: Request, filter_text: Optional[str] = Query(None, alias="$filter"),
                  orderby: Optional[str] = Query(None, alias="$orderby"),
                  select: Optional[str] = Query(None, alias="$select"),
                  top: Optional[int] = Query(None, alias="$top"), skip: Optional[int] = Query(None, alias="$skip")):
    return _reply(outlook_contacts_data.list_contacts(
        _account(request), str(request.url.replace(query="")), filter_text=filter_text, orderby=orderby,
        select=select, top=top, skip=skip))


@app.get(V + "/me/contacts/{contact_id}", dependencies=[auth.require("Contacts.Read"), STRICT])
def get_contact(contact_id: str, request: Request, select: Optional[str] = Query(None, alias="$select")):
    return _reply(outlook_contacts_data.get_contact(contact_id, _account(request), select=select))


# --- contacts: create, update, delete ----------------------------------------------------------

class EmailAddress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    address: Optional[str] = None


class PhysicalAddress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    countryOrRegion: Optional[str] = None
    postalCode: Optional[str] = None


class ContactBody(BaseModel):
    """The writable properties of a Graph contact."""

    model_config = ConfigDict(extra="forbid")

    categories: Optional[List[str]] = None
    birthday: Optional[str] = None
    fileAs: Optional[str] = None
    displayName: Optional[str] = None
    givenName: Optional[str] = None
    initials: Optional[str] = None
    middleName: Optional[str] = None
    nickName: Optional[str] = None
    surname: Optional[str] = None
    title: Optional[str] = None
    yomiGivenName: Optional[str] = None
    yomiSurname: Optional[str] = None
    yomiCompanyName: Optional[str] = None
    generation: Optional[str] = None
    imAddresses: Optional[List[str]] = None
    jobTitle: Optional[str] = None
    companyName: Optional[str] = None
    department: Optional[str] = None
    officeLocation: Optional[str] = None
    profession: Optional[str] = None
    businessHomePage: Optional[str] = None
    assistantName: Optional[str] = None
    manager: Optional[str] = None
    homePhones: Optional[List[str]] = None
    mobilePhone: Optional[str] = None
    businessPhones: Optional[List[str]] = None
    spouseName: Optional[str] = None
    personalNotes: Optional[str] = None
    children: Optional[List[str]] = None
    emailAddresses: Optional[List[EmailAddress]] = None
    homeAddress: Optional[PhysicalAddress] = None
    businessAddress: Optional[PhysicalAddress] = None
    otherAddress: Optional[PhysicalAddress] = None


@app.post(V + "/me/contacts", status_code=201, dependencies=[auth.require("Contacts.ReadWrite"), STRICT])
def create_contact(request: Request, body: ContactBody):
    return _reply(outlook_contacts_data.create_contact(_account(request), body.model_dump(exclude_unset=True)))


@app.patch(V + "/me/contacts/{contact_id}", dependencies=[auth.require("Contacts.ReadWrite"), STRICT])
def update_contact(contact_id: str, request: Request, body: ContactBody):
    return _reply(outlook_contacts_data.update_contact(contact_id, _account(request),
                                                       body.model_dump(exclude_unset=True)))


@app.delete(V + "/me/contacts/{contact_id}", status_code=204,
            dependencies=[auth.require("Contacts.ReadWrite"), STRICT])
def delete_contact(contact_id: str, request: Request):
    return _reply(outlook_contacts_data.delete_contact(contact_id, _account(request)))
