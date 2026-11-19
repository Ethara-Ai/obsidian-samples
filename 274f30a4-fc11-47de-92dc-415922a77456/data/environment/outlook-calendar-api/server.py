"""FastAPI server wrapping outlook_calendar_data as REST endpoints.

Mirrors Microsoft Graph v1.0 (graph.microsoft.com/v1.0) for the calendar
operations the connector needs: list calendars, list events, a calendar view
for a date range, get, create, update and delete an event, and free/busy for a
list of people (calendar getSchedule). Every operation needs a bearer token
from POST /oauth/token and checks its own scope, Calendars.Read or
Calendars.ReadWrite, so a connected account is not by itself permission to
edit. Errors use Graph's envelope, request validation failures included. OData
options are $-prefixed, and a query parameter the operation does not take is a
400 rather than ignored. The Prefer: outlook.timezone header sets the time zone
event times are returned in.
"""

import re
from typing import List, Optional

from fastapi import Depends, FastAPI, Header, Query, Request, Response
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

import outlook_calendar_data
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
auth = outlook_calendar_data.auth
GraphError = outlook_calendar_data.GraphError

app = FastAPI(title="Outlook Calendar API (Mock)", version="v1.0")
install_tracker(app)
install_admin_plane(app, store=outlook_calendar_data._store)
auth.install(app)

SHARED_PLANES = ("/admin", "/audit")
# Graph type names for the nested objects of a request body, keyed by the property holding them.
TYPES = {"start": "dateTimeTimeZone", "end": "dateTimeTimeZone", "startTime": "dateTimeTimeZone",
         "endTime": "dateTimeTimeZone", "body": "itemBody", "location": "location", "address": "physicalAddress",
         "attendees": "attendee", "emailAddress": "emailAddress", "status": "responseStatus",
         "recurrence": "patternedRecurrence", "pattern": "recurrencePattern", "range": "recurrenceRange"}
EDM = (("bool", "Edm.Boolean"), ("int", "Edm.Int32"), ("string", "Edm.String"), ("list", "Collection"))


class GraphApiError(Exception):
    def __init__(self, error: GraphError):
        super().__init__(error.body["error"]["message"])
        self.error = error


def _render(error: GraphError) -> JSONResponse:
    return JSONResponse(status_code=error.status, content=error.body)


def _validation_error(request: Request, exc: RequestValidationError) -> GraphError:
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
    action = request.url.path.endswith("/getSchedule")
    owner = TYPES.get(names[-2], names[-2]) if len(names) > 1 else ("getSchedule" if action else "event")
    if kind == "extra_forbidden":
        if action and len(names) == 1:
            return GraphError(400, "BadRequest", f"The parameter '{name}' in the request payload is not a valid "
                                                 "parameter for the operation 'getSchedule'.")
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
    return _render(_validation_error(request, exc))


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


def prefer_zone(prefer: Optional[str] = Header(None)) -> str:
    """The time zone a Prefer: outlook.timezone header names, UTC without one."""
    match = re.search(r'outlook\.timezone\s*=\s*"?([^",;]+)"?', prefer or "", flags=re.IGNORECASE)
    zone = match.group(1).strip() if match else "UTC"
    if zone not in outlook_calendar_data.ZONES:
        raise GraphApiError(outlook_calendar_data.zone_error(zone))
    return zone


STRICT = Depends(known_query)
ZONE = Depends(prefer_zone)


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


def _link(request: Request) -> str:
    return str(request.url.replace(query=""))


# --- calendars --------------------------------------------------------------------------------------

@app.get(V + "/me/calendars", dependencies=[auth.require("Calendars.Read"), STRICT])
def list_calendars(request: Request, top: Optional[int] = Query(None, alias="$top"),
                   skip: Optional[int] = Query(None, alias="$skip"),
                   select: Optional[str] = Query(None, alias="$select")):
    return _reply(outlook_calendar_data.list_calendars(_account(request), _link(request), top=top, skip=skip,
                                                       select=select))


# --- events: list, calendar view, get --------------------------------------------------------------

def _list_events(request, calendar_id, filter_text, orderby, select, top, skip, zone):
    return _reply(outlook_calendar_data.list_events(
        _account(request), _link(request), calendar_id=calendar_id, filter_text=filter_text, orderby=orderby,
        select=select, top=top, skip=skip, zone=zone))


@app.get(V + "/me/events", dependencies=[auth.require("Calendars.Read"), STRICT])
def list_events(request: Request, filter_text: Optional[str] = Query(None, alias="$filter"),
                orderby: Optional[str] = Query(None, alias="$orderby"),
                select: Optional[str] = Query(None, alias="$select"), top: Optional[int] = Query(None, alias="$top"),
                skip: Optional[int] = Query(None, alias="$skip"), zone: str = ZONE):
    return _list_events(request, None, filter_text, orderby, select, top, skip, zone)


@app.get(V + "/me/calendars/{calendar_id}/events", dependencies=[auth.require("Calendars.Read"), STRICT])
def list_calendar_events(calendar_id: str, request: Request,
                         filter_text: Optional[str] = Query(None, alias="$filter"),
                         orderby: Optional[str] = Query(None, alias="$orderby"),
                         select: Optional[str] = Query(None, alias="$select"),
                         top: Optional[int] = Query(None, alias="$top"),
                         skip: Optional[int] = Query(None, alias="$skip"), zone: str = ZONE):
    return _list_events(request, calendar_id, filter_text, orderby, select, top, skip, zone)


def _calendar_view(request, calendar_id, start, end, filter_text, orderby, select, top, skip, zone):
    return _reply(outlook_calendar_data.calendar_view(
        _account(request), _link(request), start, end, calendar_id=calendar_id, filter_text=filter_text,
        orderby=orderby, select=select, top=top, skip=skip, zone=zone))


@app.get(V + "/me/calendarView", dependencies=[auth.require("Calendars.Read"), STRICT])
def calendar_view(request: Request, startDateTime: Optional[str] = None, endDateTime: Optional[str] = None,
                  filter_text: Optional[str] = Query(None, alias="$filter"),
                  orderby: Optional[str] = Query(None, alias="$orderby"),
                  select: Optional[str] = Query(None, alias="$select"),
                  top: Optional[int] = Query(None, alias="$top"), skip: Optional[int] = Query(None, alias="$skip"),
                  zone: str = ZONE):
    return _calendar_view(request, None, startDateTime, endDateTime, filter_text, orderby, select, top, skip, zone)


@app.get(V + "/me/calendars/{calendar_id}/calendarView", dependencies=[auth.require("Calendars.Read"), STRICT])
def calendar_view_of_calendar(calendar_id: str, request: Request, startDateTime: Optional[str] = None,
                              endDateTime: Optional[str] = None,
                              filter_text: Optional[str] = Query(None, alias="$filter"),
                              orderby: Optional[str] = Query(None, alias="$orderby"),
                              select: Optional[str] = Query(None, alias="$select"),
                              top: Optional[int] = Query(None, alias="$top"),
                              skip: Optional[int] = Query(None, alias="$skip"), zone: str = ZONE):
    return _calendar_view(request, calendar_id, startDateTime, endDateTime, filter_text, orderby, select, top, skip,
                          zone)


@app.get(V + "/me/events/{event_id}", dependencies=[auth.require("Calendars.Read"), STRICT])
def get_event(event_id: str, request: Request, select: Optional[str] = Query(None, alias="$select"),
              zone: str = ZONE):
    return _reply(outlook_calendar_data.get_event(event_id, _account(request), select=select, zone=zone))


# --- events: create, update, delete ----------------------------------------------------------------

class DateTimeTimeZone(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dateTime: str
    timeZone: Optional[str] = None


class ItemBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contentType: Optional[str] = None
    content: Optional[str] = None


class PhysicalAddress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    countryOrRegion: Optional[str] = None
    postalCode: Optional[str] = None


class Location(BaseModel):
    model_config = ConfigDict(extra="forbid")

    displayName: Optional[str] = None
    locationType: Optional[str] = None
    address: Optional[PhysicalAddress] = None


class EmailAddress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    address: Optional[str] = None


class ResponseStatus(BaseModel):
    """Read-only on Graph: accepted so an attendee list read back can be sent again, and left as it was."""

    model_config = ConfigDict(extra="forbid")

    response: Optional[str] = None
    time: Optional[str] = None


class Attendee(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Optional[str] = None
    emailAddress: EmailAddress
    status: Optional[ResponseStatus] = None


class RecurrencePattern(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    interval: Optional[int] = None
    month: Optional[int] = None
    dayOfMonth: Optional[int] = None
    daysOfWeek: Optional[List[str]] = None
    firstDayOfWeek: Optional[str] = None
    index: Optional[str] = None


class RecurrenceRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    startDate: str
    endDate: Optional[str] = None
    recurrenceTimeZone: Optional[str] = None
    numberOfOccurrences: Optional[int] = None


class PatternedRecurrence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pattern: RecurrencePattern
    range: RecurrenceRange


class EventBody(BaseModel):
    """The writable properties of a Graph event."""

    model_config = ConfigDict(extra="forbid")

    subject: Optional[str] = None
    body: Optional[ItemBody] = None
    start: Optional[DateTimeTimeZone] = None
    end: Optional[DateTimeTimeZone] = None
    isAllDay: Optional[bool] = None
    location: Optional[Location] = None
    attendees: Optional[List[Attendee]] = None
    isOnlineMeeting: Optional[bool] = None
    showAs: Optional[str] = None
    importance: Optional[str] = None
    sensitivity: Optional[str] = None
    categories: Optional[List[str]] = None
    reminderMinutesBeforeStart: Optional[int] = None
    isReminderOn: Optional[bool] = None
    recurrence: Optional[PatternedRecurrence] = None


def _fields(body: BaseModel) -> dict:
    return body.model_dump(exclude_unset=True)


@app.post(V + "/me/events", status_code=201, dependencies=[auth.require("Calendars.ReadWrite"), STRICT])
def create_event(request: Request, body: EventBody, zone: str = ZONE):
    return _reply(outlook_calendar_data.create_event(_account(request), _fields(body), zone=zone))


@app.post(V + "/me/calendars/{calendar_id}/events", status_code=201,
          dependencies=[auth.require("Calendars.ReadWrite"), STRICT])
def create_calendar_event(calendar_id: str, request: Request, body: EventBody, zone: str = ZONE):
    return _reply(outlook_calendar_data.create_event(_account(request), _fields(body), calendar_id=calendar_id,
                                                     zone=zone))


@app.patch(V + "/me/events/{event_id}", dependencies=[auth.require("Calendars.ReadWrite"), STRICT])
def update_event(event_id: str, request: Request, body: EventBody, zone: str = ZONE):
    return _reply(outlook_calendar_data.update_event(event_id, _account(request), _fields(body), zone=zone))


@app.delete(V + "/me/events/{event_id}", status_code=204, dependencies=[auth.require("Calendars.ReadWrite"), STRICT])
def delete_event(event_id: str, request: Request):
    return _reply(outlook_calendar_data.delete_event(event_id, _account(request)))


# --- free/busy ---------------------------------------------------------------------------------------

class ScheduleBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schedules: List[str]
    startTime: DateTimeTimeZone
    endTime: DateTimeTimeZone
    availabilityViewInterval: Optional[int] = None


@app.post(V + "/me/calendar/getSchedule", dependencies=[auth.require("Calendars.Read"), STRICT])
def get_schedule(request: Request, body: ScheduleBody, zone: str = ZONE):
    return _reply(outlook_calendar_data.get_schedule(_account(request), _fields(body), zone=zone))
