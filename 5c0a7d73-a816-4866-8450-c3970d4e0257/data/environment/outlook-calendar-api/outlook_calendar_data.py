"""Data access module for the Outlook Calendar (Microsoft Graph) mock service.

Serves exactly the calendar operations the connector needs -- list calendars,
list events, a calendar view for a date range, get an event, create an event,
update an event, delete an event, and check free/busy for a list of people --
in the shape of Microsoft Graph v1.0 (graph.microsoft.com/v1.0/me/...). Every
read and write is scoped to the mailbox the presented token's connected
account owns: Alex Carter's at Contoso, the same mailbox outlook-api serves.

Events are rows in UTC with the time zone they were created in; a daily or
weekly series is one row with its recurrence, expanded into occurrences by the
calendar view and by free/busy. Colleagues' schedules for free/busy are seeded
busy blocks. Mock simplifications (also stated in api_test_results.md): UTC
and the US time zones only, daily and weekly series without exceptions, no
attachments, rooms or meeting responses, and a subset of OData $filter.
"""

import base64
import hashlib
import json
import operator
import re
import secrets
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlencode

DATA_DIR = Path(__file__).parent

sys.path.insert(0, str(DATA_DIR.parent))
import _mock_clock  # noqa: E402
from _mutable_store import get_store, opt_bool, opt_int, read_seed_with_ctx  # noqa: E402
from _connector_auth import ConnectorAuth  # noqa: E402

_API = "outlook-calendar-api"
_store = get_store(_API)

GRAPH = "https://graph.microsoft.com/v1.0"
DEFAULT_TOP, MAX_TOP = 10, 1000
# Monday first, so DAYS.index(name) == date.weekday().
DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
SHOW_AS = ("free", "tentative", "busy", "oof", "workingElsewhere", "unknown")
IMPORTANCE = ("low", "normal", "high")
SENSITIVITY = ("normal", "personal", "private", "confidential")
BODY_TYPES = ("text", "html")
ATTENDEE_TYPES = ("required", "optional", "resource")
LOCATION_TYPES = ("default", "conferenceRoom", "homeAddress", "businessAddress", "geoCoordinates", "streetAddress",
                  "hotel", "restaurant", "localBusiness", "postalAddress")
PATTERN_TYPES = ("daily", "weekly", "absoluteMonthly", "relativeMonthly", "absoluteYearly", "relativeYearly")
RANGE_TYPES = ("endDate", "noEnd", "numbered")
WEEK_INDEXES = ("first", "second", "third", "fourth", "last")
# Time zones the mock converts: (standard UTC offset in hours, observes US daylight saving time).
ZONES = {"UTC": (0, False), "Etc/UTC": (0, False), "Pacific Standard Time": (-8, True),
         "America/Los_Angeles": (-8, True), "Mountain Standard Time": (-7, True), "America/Denver": (-7, True),
         "US Mountain Standard Time": (-7, False), "America/Phoenix": (-7, False),
         "Central Standard Time": (-6, True), "America/Chicago": (-6, True),
         "Eastern Standard Time": (-5, True), "America/New_York": (-5, True)}


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _parsed(value, empty):
    """A JSON-encoded cell (as a CSV overlay carries it) decoded; ``empty`` for a blank one."""
    if isinstance(value, str) and value.strip()[:1] in ("[", "{"):
        try:
            return json.loads(value)
        except ValueError:
            return empty
    if value is None or value == "":
        return empty
    return value


def _list(value):
    value = _parsed(value, [])
    if isinstance(value, str):
        return [part.strip() for part in value.split(";") if part.strip()]
    return list(value) if isinstance(value, (list, tuple)) else []


def _coerce_calendar_row(r):
    out = _strip_ctx(r)
    out["is_default"] = opt_bool(out, "is_default")
    out["can_edit"] = opt_bool(out, "can_edit", default=True)
    return out


def _coerce_event_row(r):
    out = _strip_ctx(r)
    out["attendees"] = [a if isinstance(a, dict) else {"name": str(a), "address": str(a)}
                        for a in _list(out.get("attendees"))]
    out["categories"] = [str(c) for c in _list(out.get("categories"))]
    out["recurrence"] = _parsed(out.get("recurrence"), None) or None
    address = _parsed(out.get("location_address"), {})
    out["location_address"] = address if isinstance(address, dict) else {}
    for key in ("is_all_day", "is_online", "is_cancelled"):
        out[key] = opt_bool(out, key)
    out["is_reminder_on"] = opt_bool(out, "is_reminder_on", default=True)
    out["reminder_minutes"] = opt_int(out, "reminder_minutes", 15)
    for key in ("subject", "body", "location", "online_url"):
        out[key] = out.get(key) or ""
    return out


def _coerce_person_row(r):
    out = _strip_ctx(r)
    out["address"] = str(out.get("address") or "").lower()
    out["work_days"] = [str(d) for d in _list(out.get("work_days"))] or list(DAYS[:5])
    return out


_store.register("calendars", primary_key="id",
                initial_loader=lambda: [_coerce_calendar_row(r) for r in _load("calendars.json", "calendars")],
                row_coercer=_coerce_calendar_row)
_store.register("events", primary_key="id",
                initial_loader=lambda: [_coerce_event_row(r) for r in _load("events.json", "events")],
                row_coercer=_coerce_event_row)
_store.register("people", primary_key="address",
                initial_loader=lambda: [_coerce_person_row(r) for r in _load("people.json", "people")],
                row_coercer=_coerce_person_row)
_store.register("schedule_items", primary_key="id",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("schedule_items.json", "schedule_items")])

auth = ConnectorAuth(_API, store=_store, data_dir=DATA_DIR)


class GraphError:
    """A Microsoft Graph error envelope and the HTTP status it is served with."""

    def __init__(self, status, code, message):
        self.status = status
        request_id = str(uuid.uuid4())
        self.body = {"error": {"code": code, "message": message, "innerError": {
            "date": _mock_clock.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            "request-id": request_id, "client-request-id": request_id}}}


def bad_request(message, code="ErrorInvalidRequest"):
    return GraphError(400, code, message)


def _not_found():
    return GraphError(404, "ErrorItemNotFound", "The specified object was not found in the store.")


def _no_mailbox():
    return GraphError(404, "MailboxNotEnabledForRESTAPI",
                      "The mailbox is either inactive, soft-deleted, or is hosted on-premise.")


def _access_denied():
    return GraphError(403, "ErrorAccessDenied", "Access is denied. Check credentials and try again.")


def zone_error(zone):
    return bad_request(f"A valid TimeZone value must be specified. The following TimeZone value is not supported: "
                       f"'{zone}'. This mock converts UTC and the US time zones, by Windows or IANA name (for "
                       "example Pacific Standard Time or America/Los_Angeles).", code="TimeZoneNotSupportedException")


def _enum(value, allowed):
    """The canonical spelling of ``value`` among ``allowed`` (Graph enums ignore case), or a GraphError."""
    for option in allowed:
        if isinstance(value, str) and value.lower() == option.lower():
            return option
    return GraphError(400, "RequestBodyRead", f"Requested value '{value}' was not found.")


# --- time ------------------------------------------------------------------------------------

def _nth_sunday(year, month, n):
    first = date(year, month, 1)
    return first + timedelta(days=(6 - first.weekday()) % 7 + 7 * (n - 1))


def _offset_hours(zone, utc_moment=None, local_moment=None):
    """The zone's UTC offset at a UTC moment or at a local wall-clock moment, under the US daylight saving rule."""
    std, dst = ZONES[zone]
    if not dst:
        return std
    moment = utc_moment if utc_moment is not None else local_moment
    start = datetime.combine(_nth_sunday(moment.year, 3, 2), datetime.min.time()) + timedelta(hours=2)
    end = datetime.combine(_nth_sunday(moment.year, 11, 1), datetime.min.time()) + timedelta(hours=2)
    if utc_moment is not None:
        start, end = start - timedelta(hours=std), end - timedelta(hours=std + 1)
    else:
        end -= timedelta(hours=1)  # the hour repeated when the clocks fall back counts as standard time
    return std + 1 if start <= moment < end else std


def to_utc(local, zone):
    return local - timedelta(hours=_offset_hours(zone, local_moment=local))


def from_utc(utc, zone):
    return utc + timedelta(hours=_offset_hours(zone, utc_moment=utc))


def _zone_of(row):
    return row.get("original_tz") if row.get("original_tz") in ZONES else "UTC"


def graph_time(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%S.0000000")


def _utc(text):
    """A naive UTC datetime from an ISO 8601 string; one without an offset is already UTC."""
    moment = datetime.fromisoformat(str(text).strip().replace("Z", "+00:00"))
    return moment.astimezone(timezone.utc).replace(tzinfo=None) if moment.tzinfo else moment


def _iso_z(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _now():
    return _mock_clock.now(timezone.utc).replace(microsecond=0, tzinfo=None)


def _date(text):
    try:
        return date.fromisoformat(str(text))
    except (TypeError, ValueError):
        return None


def parse_graph_datetime(text):
    """A naive datetime from Graph's dateTime string (fractional seconds allowed), or None."""
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?)(?:\.\d{1,7})?", (text or "").strip())
    if not match:
        return None
    value = match.group(1)
    try:
        return datetime.fromisoformat(value if value.count(":") == 2 else value + ":00")
    except ValueError:
        return None


def parse_window_bound(text, name):
    """A calendarView bound (ISO 8601; UTC when it carries no offset) as naive UTC, or a GraphError."""
    try:
        return _utc(text)
    except ValueError:
        return bad_request(f"The value '{text}' of parameter '{name}' is not a valid date and time.",
                           code="ErrorInvalidParameter")


def _time_input(value, name):
    """(naive UTC datetime, zone) from a dateTimeTimeZone body value, or a GraphError."""
    zone = value.get("timeZone") or "UTC"
    if zone not in ZONES:
        return zone_error(zone)
    text = (value.get("dateTime") or "").strip()
    if text.endswith("Z"):
        if ZONES[zone] != (0, False):
            return bad_request(f"{name}.dateTime '{text}' is marked UTC with 'Z' but its timeZone is '{zone}'; send "
                               "the local time without 'Z', or use timeZone UTC.", code="ErrorInvalidRequest")
        text = text[:-1]
    local = parse_graph_datetime(text)
    if local is None:
        return GraphError(400, "RequestBodyRead", f"Cannot convert the literal '{value.get('dateTime')}' to the "
                                                  "expected type 'Edm.DateTimeOffset'.")
    return to_utc(local, zone), zone


# --- OData $filter, a subset -------------------------------------------------------------------

_TOKEN = re.compile(r"\s*(?:(\()|(\))|(,)|('(?:[^']|'')*')|(-?\d+(?:\.\d+)?(?![\w:-]))|"
                    r"(\d{4}-\d{2}-\d{2}(?:T[\d:.]+(?:Z|[+-]\d{2}:\d{2})?)?)|"
                    r"([A-Za-z_][\w/]*(?::\s*[A-Za-z_][\w/]*)?))")
_FUNCTIONS = ("startswith", "endswith", "contains")
_OPS = {"eq": operator.eq, "ne": operator.ne, "gt": operator.gt, "ge": operator.ge, "lt": operator.lt,
        "le": operator.le}
_STAMP = re.compile(r"\d{4}-\d{2}-\d{2}")


class FilterError(ValueError):
    pass


def _tokens(text):
    out, pos = [], 0
    while text[pos:].strip():
        match = _TOKEN.match(text, pos)
        if not match:
            raise FilterError(f"Syntax error at position {pos} in '{text}'.")
        lp, rp, comma, string, number, stamp, word = match.groups()
        if lp or rp or comma:
            out.append((lp or rp or comma, None))
        elif string is not None:
            out.append(("str", string[1:-1].replace("''", "'")))
        elif number is not None:
            out.append(("num", float(number) if "." in number else int(number)))
        elif stamp is not None:
            out.append(("str", stamp))
        else:
            out.append(("word", word))
        pos = match.end()
    return out


class _Parser:
    """Recursive-descent parser for the OData boolean expressions this mock evaluates."""

    def __init__(self, text, fields, type_name):
        self.items, self.i, self.fields, self.type_name = _tokens(text), 0, fields, type_name

    def peek(self, offset=0):
        j = self.i + offset
        return self.items[j] if j < len(self.items) else (None, None)

    def keyword(self, word):
        kind, value = self.peek()
        if kind == "word" and value.lower() == word:
            self.i += 1
            return True
        return False

    def take(self, kind):
        found, value = self.peek()
        if found != kind:
            raise FilterError(f"Expected {kind} in the filter expression.")
        self.i += 1
        return value

    def parse(self):
        node = self.or_expr()
        if self.peek()[0] is not None:
            kind, value = self.peek()
            raise FilterError(f"Unexpected '{value if value is not None else kind}' in the filter expression.")
        return node

    def or_expr(self):
        node = self.and_expr()
        while self.keyword("or"):
            node = ("or", node, self.and_expr())
        return node

    def and_expr(self):
        node = self.unary()
        while self.keyword("and"):
            node = ("and", node, self.unary())
        return node

    def unary(self):
        if self.keyword("not"):
            return ("not", self.unary())
        return self.primary()

    def primary(self):
        kind, value = self.peek()
        if kind == "(":
            self.i += 1
            node = self.or_expr()
            self.take(")")
            return node
        if kind == "word" and value.lower() in _FUNCTIONS and self.peek(1)[0] == "(":
            self.i += 2
            field = self.property()
            self.take(",")
            text = self.take("str")
            self.take(")")
            return (value.lower(), field, text)
        if kind == "word" and value.endswith("/any") and self.peek(1)[0] == "(":
            return self.any_expr()
        field = self.property()
        op = self.take("word").lower()
        if op not in _OPS:
            raise FilterError(f"Unsupported operator '{op}' in the filter expression.")
        return ("cmp", op, field, self.literal())

    def any_expr(self):
        collection = self.take("word")[:-len("/any")]
        if collection not in self.fields:
            raise FilterError(self.unknown(collection))
        self.take("(")
        variable, _, path = self.take("word").partition(":")
        path = path.strip()
        if path != variable and not path.startswith(variable + "/"):
            raise FilterError("Expected a lambda such as c:c eq 'Blue category' inside any().")
        op = self.take("word").lower()
        if op not in ("eq", "ne"):
            raise FilterError(f"Unsupported operator '{op}' inside any().")
        literal = self.literal()
        self.take(")")
        return ("any", collection, path[len(variable) + 1:], op, literal)

    def property(self):
        kind, value = self.peek()
        if kind != "word":
            raise FilterError("Expected a property name in the filter expression.")
        if value not in self.fields:
            raise FilterError(self.unknown(value))
        self.i += 1
        return value

    def literal(self):
        kind, value = self.peek()
        if kind == "word" and value.lower() in ("true", "false", "null"):
            self.i += 1
            return {"true": True, "false": False, "null": None}[value.lower()]
        if kind in ("str", "num"):
            self.i += 1
            return value
        raise FilterError("Expected a literal after the comparison operator.")

    def unknown(self, name):
        return f"Could not find a property named '{name}' on type 'microsoft.graph.{self.type_name}'."


def _value_of(view, path):
    node = view
    for part in path.split("/") if path else ():
        node = node.get(part) if isinstance(node, dict) else None
    return node


def _compare(op, left, right):
    if isinstance(left, str) and isinstance(right, str):
        left, right = left.casefold(), right.casefold()
        if _STAMP.match(left) and _STAMP.match(right):
            left, right = left[:19], right.rstrip("z")[:19]
    try:
        return _OPS[op](left, right)
    except TypeError:
        return False


def _evaluate(node, view):
    kind = node[0]
    if kind == "and":
        return _evaluate(node[1], view) and _evaluate(node[2], view)
    if kind == "or":
        return _evaluate(node[1], view) or _evaluate(node[2], view)
    if kind == "not":
        return not _evaluate(node[1], view)
    if kind in _FUNCTIONS:
        text = _value_of(view, node[1])
        if not isinstance(text, str):
            return False
        test = {"startswith": str.startswith, "endswith": str.endswith, "contains": str.__contains__}[kind]
        return test(text.casefold(), node[2].casefold())
    if kind == "any":
        _any, collection, path, op, literal = node
        return any(_compare(op, _value_of(item, path) if path else item, literal)
                   for item in _value_of(view, collection) or [])
    _cmp, op, field, literal = node
    return _compare(op, _value_of(view, field), literal)


def compile_filter(text, fields, type_name="event"):
    """A predicate over a view dict for an OData ``$filter`` string, or a GraphError."""
    try:
        tree = _Parser(text, fields, type_name).parse()
    except FilterError as exc:
        return bad_request(f"Invalid filter clause: {exc}", code="BadRequest")
    return lambda view: _evaluate(tree, view)


def compile_orderby(text, fields):
    """A list of (path, descending) for an OData ``$orderby``, or a GraphError."""
    out = []
    for part in [p.strip() for p in (text or "").split(",") if p.strip()]:
        bits = part.split()
        if bits[0] not in fields or len(bits) > 2 or (len(bits) == 2 and bits[1].lower() not in ("asc", "desc")):
            return bad_request(f"Invalid $orderby clause '{part}'; this mock orders by {', '.join(fields)}.",
                               code="BadRequest")
        out.append((bits[0], len(bits) == 2 and bits[1].lower() == "desc"))
    return out


def _ordered(keyed, order):
    """``keyed`` ((view, ...) tuples) sorted by ``order``, earlier keys first, missing values last."""
    for path, descending in reversed(order):
        keyed = sorted(keyed, reverse=descending, key=lambda k, path=path: (
            _value_of(k[0], path) is None, str(_value_of(k[0], path)).casefold()))
    return keyed


def _selection(select, allowed, type_name):
    """The property names ``$select`` asks for (None for every property), or a GraphError."""
    if not select:
        return None
    names = [s.strip() for s in select.split(",") if s.strip()]
    unknown = [n for n in names if n not in allowed]
    if unknown:
        return bad_request(f"Could not find a property named '{unknown[0]}' on type 'microsoft.graph.{type_name}'.",
                           code="BadRequest")
    return names


def _pick(view, names):
    if names is None:
        return view
    out = {k: view[k] for k in ("@odata.etag", "id") if k in view}
    out.update((n, view.get(n)) for n in names)
    return out


# --- rendering ------------------------------------------------------------------------------

def _etag(row):
    digest = hashlib.sha256(json.dumps(row, sort_keys=True, default=str).encode()).digest()
    return 'W/"' + base64.b64encode(digest[:21]).decode() + '"'


def _time_view(utc_moment, zone):
    return {"dateTime": graph_time(from_utc(utc_moment, zone)), "timeZone": zone}


def _event_view(row, owner, zone, occurrence=None):
    start, end = occurrence or (_utc(row["start"]), _utc(row["end"]))
    etag = _etag(row)
    is_organizer = row["organizer_address"].lower() == owner["owner_address"].lower()
    online = row["is_online"]
    return {
        "@odata.etag": etag,
        "id": row["id"] if occurrence is None else f"{row['id']}_{start.strftime('%Y%m%d')}",
        "createdDateTime": row["created"],
        "lastModifiedDateTime": row["last_modified"],
        "changeKey": etag[3:-1],
        "categories": list(row["categories"]),
        "originalStartTimeZone": row["original_tz"],
        "originalEndTimeZone": row["original_tz"],
        "iCalUId": "040000008200E00074C5B7101A82E00800000000"
                   + hashlib.sha256(row["id"].encode()).hexdigest()[:32].upper(),
        "reminderMinutesBeforeStart": row["reminder_minutes"],
        "isReminderOn": row["is_reminder_on"],
        "hasAttachments": False,
        "subject": row["subject"],
        "bodyPreview": " ".join(re.sub(r"<[^>]+>", " ", row["body"]).split())[:255],
        "importance": row.get("importance") or "normal",
        "sensitivity": row.get("sensitivity") or "normal",
        "isAllDay": row["is_all_day"],
        "isCancelled": row["is_cancelled"],
        "isOrganizer": is_organizer,
        "responseRequested": True,
        "seriesMasterId": row["id"] if occurrence is not None else None,
        "showAs": row.get("show_as") or "busy",
        "type": "occurrence" if occurrence is not None else "seriesMaster" if row["recurrence"] else "singleInstance",
        "webLink": f"https://outlook.office365.com/owa/?itemid={quote(row['id'])}&exvsurl=1&path=/calendar/item",
        "isOnlineMeeting": online,
        "onlineMeetingProvider": "teamsForBusiness" if online else "unknown",
        "allowNewTimeProposals": True,
        "isDraft": False,
        "hideAttendees": False,
        "responseStatus": {"response": "organizer" if is_organizer else row.get("response") or "notResponded",
                           "time": "0001-01-01T00:00:00Z"},
        "body": {"contentType": row.get("body_type") or "html", "content": row["body"]},
        "start": _time_view(start, zone),
        "end": _time_view(end, zone),
        "location": {"displayName": row["location"], "locationType": row.get("location_type") or "default",
                     "address": dict(row.get("location_address") or {})},
        "recurrence": row["recurrence"] if occurrence is None else None,
        "attendees": [{"type": a.get("type") or "required",
                       "status": {"response": a.get("response") or "none",
                                  "time": a.get("response_time") or "0001-01-01T00:00:00Z"},
                       "emailAddress": {"name": a.get("name") or a["address"], "address": a["address"]}}
                      for a in row["attendees"]],
        "organizer": {"emailAddress": {"name": row["organizer_name"], "address": row["organizer_address"]}},
        "onlineMeeting": {"joinUrl": row["online_url"]} if online and row["online_url"] else None,
    }


SELECTABLE = ("id", "createdDateTime", "lastModifiedDateTime", "changeKey", "categories", "originalStartTimeZone",
              "originalEndTimeZone", "iCalUId", "reminderMinutesBeforeStart", "isReminderOn", "hasAttachments",
              "subject", "bodyPreview", "importance", "sensitivity", "isAllDay", "isCancelled", "isOrganizer",
              "responseRequested", "seriesMasterId", "showAs", "type", "webLink", "isOnlineMeeting",
              "onlineMeetingProvider", "allowNewTimeProposals", "isDraft", "hideAttendees", "responseStatus", "body",
              "start", "end", "location", "recurrence", "attendees", "organizer", "onlineMeeting")
FILTERABLE = ("id", "subject", "start/dateTime", "end/dateTime", "isAllDay", "isCancelled", "showAs", "importance",
              "sensitivity", "isOnlineMeeting", "isOrganizer", "type", "createdDateTime", "lastModifiedDateTime",
              "organizer/emailAddress/address", "organizer/emailAddress/name", "location/displayName", "categories",
              "seriesMasterId", "responseStatus/response")
ORDERABLE = ("subject", "start/dateTime", "end/dateTime", "createdDateTime", "lastModifiedDateTime", "importance",
             "showAs", "organizer/emailAddress/name")
CALENDAR_FIELDS = ("id", "name", "color", "hexColor", "isDefaultCalendar", "changeKey", "canShare",
                   "canViewPrivateItems", "canEdit", "allowedOnlineMeetingProviders", "defaultOnlineMeetingProvider",
                   "isTallyingResponses", "isRemovable", "owner")


def _calendar_view(row):
    return {"id": row["id"], "name": row["name"], "color": row.get("color") or "auto",
            "hexColor": row.get("hex_color") or "", "isDefaultCalendar": row["is_default"],
            "changeKey": _etag(row)[3:-1], "canShare": row["can_edit"], "canViewPrivateItems": True,
            "canEdit": row["can_edit"], "allowedOnlineMeetingProviders": ["teamsForBusiness"],
            "defaultOnlineMeetingProvider": "teamsForBusiness", "isTallyingResponses": row["can_edit"],
            "isRemovable": not row["is_default"],
            "owner": {"name": row["owner_name"], "address": row["owner_address"]}}


# --- recurrence ------------------------------------------------------------------------------------

def _overlaps(start, end, window_start, window_end):
    return start < window_end and (end > window_start or (start == end and start >= window_start))


def occurrences(row, window_start, window_end):
    """(start, end) UTC pairs of ``row`` that overlap the window: the event itself, or each occurrence of a series."""
    start, end = _utc(row["start"]), _utc(row["end"])
    if not row["recurrence"]:
        return [(start, end)] if _overlaps(start, end, window_start, window_end) else []
    pattern, span = row["recurrence"].get("pattern") or {}, row["recurrence"].get("range") or {}
    zone = next((z for z in (span.get("recurrenceTimeZone"), row["original_tz"]) if z in ZONES), "UTC")
    local_time = from_utc(start, zone).time()
    duration = end - start
    interval = max(1, int(pattern.get("interval") or 1))
    weekly = pattern.get("type") == "weekly"
    days = {DAYS.index(d) for d in pattern.get("daysOfWeek") or [] if d in DAYS} or {from_utc(start, zone).weekday()}
    first_day = _date(span.get("startDate")) or from_utc(start, zone).date()
    last_day = _date(span.get("endDate")) if span.get("type") == "endDate" else None
    limit = int(span.get("numberOfOccurrences") or 0) if span.get("type") == "numbered" else 0
    week_start = DAYS.index(pattern["firstDayOfWeek"]) if pattern.get("firstDayOfWeek") in DAYS else 6
    week0 = first_day - timedelta(days=(first_day.weekday() - week_start) % 7)
    out, count, day = [], 0, first_day
    while (last_day is None or day <= last_day) and (not limit or count < limit) and (day - first_day).days <= 3660:
        occ_start = to_utc(datetime.combine(day, local_time), zone)
        if occ_start >= window_end:
            break
        if weekly:
            hit = day.weekday() in days and ((day - week0).days // 7) % interval == 0
        else:
            hit = (day - first_day).days % interval == 0
        if hit:
            count += 1
            if _overlaps(occ_start, occ_start + duration, window_start, window_end):
                out.append((occ_start, occ_start + duration))
        day += timedelta(days=1)
    return out


def _recurrence(value, zone):
    """A stored recurrence from a request's patternedRecurrence with every Graph field filled in, or a GraphError."""
    if not value:
        return None
    pattern, span = value["pattern"], value["range"]
    kind = _enum(pattern.get("type"), PATTERN_TYPES)
    if isinstance(kind, GraphError):
        return kind
    if kind not in ("daily", "weekly"):
        return bad_request(f"This mock expands daily and weekly series only, so a {kind} pattern is not supported.")
    days = [_enum(d, DAYS) for d in pattern.get("daysOfWeek") or []]
    first_day = _enum(pattern.get("firstDayOfWeek") or "sunday", DAYS)
    index = _enum(pattern.get("index") or "first", WEEK_INDEXES)
    span_type = _enum(span.get("type"), RANGE_TYPES)
    for item in (*days, first_day, index, span_type):
        if isinstance(item, GraphError):
            return item
    interval = pattern.get("interval", 1)
    if interval is None or interval < 1:
        return bad_request("The recurrence interval must be 1 or more.", code="ErrorPropertyValidationFailure")
    if kind == "weekly" and not days:
        return bad_request("A weekly recurrence pattern needs at least one day in daysOfWeek.",
                           code="ErrorPropertyValidationFailure")
    start_day = _date(span.get("startDate"))
    if start_day is None:
        return bad_request(f"The recurrence range startDate '{span.get('startDate')}' is not a date.",
                           code="ErrorPropertyValidationFailure")
    end_day = _date(span.get("endDate")) if span_type == "endDate" else None
    if span_type == "endDate" and (end_day is None or end_day < start_day):
        return bad_request("An endDate recurrence range needs an endDate on or after its startDate.",
                           code="ErrorPropertyValidationFailure")
    count = span.get("numberOfOccurrences") or 0
    if span_type == "numbered" and count < 1:
        return bad_request("A numbered recurrence range needs numberOfOccurrences of 1 or more.",
                           code="ErrorPropertyValidationFailure")
    span_zone = span.get("recurrenceTimeZone") or zone
    if span_zone not in ZONES:
        return zone_error(span_zone)
    return {"pattern": {"type": kind, "interval": interval, "month": pattern.get("month") or 0,
                        "dayOfMonth": pattern.get("dayOfMonth") or 0, "daysOfWeek": days,
                        "firstDayOfWeek": first_day, "index": index},
            "range": {"type": span_type, "startDate": start_day.isoformat(),
                      "endDate": end_day.isoformat() if end_day else "0001-01-01",
                      "recurrenceTimeZone": span_zone, "numberOfOccurrences": count if span_type == "numbered" else 0}}


# --- lookup -------------------------------------------------------------------------------------

def _calendars(account_id):
    return sorted(_store.table("calendars").find(lambda c: c["owner_account_id"] == account_id),
                  key=lambda c: (not c["is_default"], c["name"]))


def _mailbox(account_id):
    """The account's default calendar, whose row names the mailbox owner; None when the account has no mailbox."""
    return next((c for c in _calendars(account_id) if c["is_default"]), None)


def _owned_calendar(calendar_id, account_id):
    row = _store.table("calendars").get(calendar_id)
    return row if row is not None and row["owner_account_id"] == account_id else None


def _events_in(calendar_id):
    return _store.table("events").find(lambda e: e["calendar_id"] == calendar_id)


def _event(event_id, account_id):
    """(row, None) for an event or series id, (series row, (start, end)) for an occurrence id, else (None, None)."""
    owned = {c["id"] for c in _calendars(account_id)}
    row = _store.table("events").get(event_id)
    if row is not None:
        return (row, None) if row["calendar_id"] in owned else (None, None)
    master_id, _, stamp = event_id.rpartition("_")
    row = _store.table("events").get(master_id) if re.fullmatch(r"\d{8}", stamp) else None
    if row is None or not row["recurrence"] or row["calendar_id"] not in owned:
        return None, None
    try:
        day = datetime.strptime(stamp, "%Y%m%d")
    except ValueError:
        return None, None
    for pair in occurrences(row, day, day + timedelta(days=1)):
        if pair[0].date() == day.date():
            return row, pair
    return None, None


# --- paging and shaping --------------------------------------------------------------------------

def _paged(views, top, skip, link, query, context):
    for name, value in (("$top", top), ("$skip", skip)):
        if value is not None and value < 0:
            return bad_request(f"Invalid value '{value}' for {name} query option found. The {name} query option "
                               "requires a non-negative integer value.", code="BadRequest")
    if top is not None and top > MAX_TOP:
        return bad_request(f"The limit of '{MAX_TOP}' for Top query has been exceeded. The value from the incoming "
                           f"request is '{top}'.", code="BadRequest")
    size, start = DEFAULT_TOP if top is None else top, skip or 0
    out = {"@odata.context": context, "value": views[start:start + size]}
    if size and start + size < len(views):
        params = {k: v for k, v in query.items() if v is not None}
        params["$skip"] = start + size
        out["@odata.nextLink"] = f"{link}?{urlencode(params, safe='$')}"
    return out


def _context(owner, what):
    return f"{GRAPH}/$metadata#users('{quote(owner['owner_address'])}')/{what}"


def _shape(items, owner, filter_text, orderby, select, default_order, zone):
    """Views of ``items`` ((row, occurrence) pairs), filtered and ordered on their UTC times, rendered in ``zone``."""
    predicate = compile_filter(filter_text, FILTERABLE) if filter_text else None
    if isinstance(predicate, GraphError):
        return predicate
    order = compile_orderby(orderby, ORDERABLE) if orderby else default_order
    if isinstance(order, GraphError):
        return order
    names = _selection(select, SELECTABLE, "event")
    if isinstance(names, GraphError):
        return names
    keyed = [(_event_view(row, owner, "UTC", occurrence), row, occurrence) for row, occurrence in items]
    if predicate is not None:
        keyed = [k for k in keyed if predicate(k[0])]
    return [_pick(view if zone == "UTC" else _event_view(row, owner, zone, occurrence), names)
            for view, row, occurrence in _ordered(keyed, order)]


# --- operations ------------------------------------------------------------------------------------

def list_calendars(account_id, link, top=None, skip=None, select=None):
    owner = _mailbox(account_id)
    if owner is None:
        return _no_mailbox()
    names = _selection(select, CALENDAR_FIELDS, "calendar")
    if isinstance(names, GraphError):
        return names
    views = [_pick(_calendar_view(c), names) for c in _calendars(account_id)]
    return _paged(views, top, skip, link, {"$select": select, "$top": top}, _context(owner, "calendars"))


def list_events(account_id, link, calendar_id=None, filter_text=None, orderby=None, select=None, top=None, skip=None,
                zone="UTC"):
    owner = _mailbox(account_id)
    if owner is None:
        return _no_mailbox()
    calendar = owner if calendar_id is None else _owned_calendar(calendar_id, account_id)
    if calendar is None:
        return _not_found()
    views = _shape([(e, None) for e in _events_in(calendar["id"])], owner, filter_text, orderby, select,
                   [("createdDateTime", True)], zone)
    if isinstance(views, GraphError):
        return views
    return _paged(views, top, skip, link, {"$filter": filter_text, "$orderby": orderby, "$select": select,
                                           "$top": top}, _context(owner, "events"))


def calendar_view(account_id, link, start_text, end_text, calendar_id=None, filter_text=None, orderby=None,
                  select=None, top=None, skip=None, zone="UTC"):
    owner = _mailbox(account_id)
    if owner is None:
        return _no_mailbox()
    calendar = owner if calendar_id is None else _owned_calendar(calendar_id, account_id)
    if calendar is None:
        return _not_found()
    if not start_text or not end_text:
        return bad_request("This request requires a time window specified by the query string parameters "
                           "StartDateTime and EndDateTime.", code="ErrorInvalidParameter")
    window_start = parse_window_bound(start_text, "startDateTime")
    if isinstance(window_start, GraphError):
        return window_start
    window_end = parse_window_bound(end_text, "endDateTime")
    if isinstance(window_end, GraphError):
        return window_end
    if window_end <= window_start:
        return bad_request("The end of the time window must be after its start.", code="ErrorInvalidParameter")
    items = [(e, pair if e["recurrence"] else None) for e in _events_in(calendar["id"])
             for pair in occurrences(e, window_start, window_end)]
    views = _shape(items, owner, filter_text, orderby, select, [("start/dateTime", False)], zone)
    if isinstance(views, GraphError):
        return views
    return _paged(views, top, skip, link, {"startDateTime": start_text, "endDateTime": end_text,
                                           "$filter": filter_text, "$orderby": orderby, "$select": select,
                                           "$top": top}, _context(owner, "calendarView"))


def get_event(event_id, account_id, select=None, zone="UTC"):
    owner = _mailbox(account_id)
    if owner is None:
        return _no_mailbox()
    row, occurrence = _event(event_id, account_id)
    if row is None:
        return _not_found()
    names = _selection(select, SELECTABLE, "event")
    if isinstance(names, GraphError):
        return names
    return {"@odata.context": _context(owner, "events/$entity"),
            **_pick(_event_view(row, owner, zone, occurrence), names)}


def _attendees(items, existing):
    """Stored attendees for a request's attendee list; a response already recorded for an address is kept."""
    before = {a["address"].lower(): a for a in existing}
    out = []
    for item in items:
        email = item.get("emailAddress") or {}
        address = (email.get("address") or "").strip()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", address):
            return bad_request(f"An attendee needs an emailAddress with a valid address; '{address}' is not one.",
                               code="ErrorInvalidRecipients")
        kind = _enum(item.get("type") or "required", ATTENDEE_TYPES)
        if isinstance(kind, GraphError):
            return kind
        known = before.get(address.lower(), {})
        out.append({"name": email.get("name") or known.get("name") or address, "address": address, "type": kind,
                    "response": known.get("response") or "none",
                    "response_time": known.get("response_time") or "0001-01-01T00:00:00Z"})
    return out


def _apply_body(row, body):
    """``row`` with the writable properties of an event body applied, or a GraphError."""
    out = dict(row)
    if "subject" in body:
        out["subject"] = body["subject"] or ""
    if "body" in body:
        content = body["body"] or {}
        kind = _enum(content.get("contentType") or "text", BODY_TYPES)
        if isinstance(kind, GraphError):
            return kind
        out["body"], out["body_type"] = content.get("content") or "", kind
    for name in ("start", "end"):
        if name in body:
            if not body[name]:
                return bad_request(f"The event's {name} cannot be empty.", code="ErrorPropertyValidationFailure")
            parsed = _time_input(body[name], name)
            if isinstance(parsed, GraphError):
                return parsed
            out[name] = _iso_z(parsed[0])
            if name == "start":
                out["original_tz"] = parsed[1]
    for key, column, allowed in (("showAs", "show_as", SHOW_AS), ("importance", "importance", IMPORTANCE),
                                 ("sensitivity", "sensitivity", SENSITIVITY)):
        if key in body:
            value = _enum(body[key], allowed)
            if isinstance(value, GraphError):
                return value
            out[column] = value
    for key, column in (("isAllDay", "is_all_day"), ("isReminderOn", "is_reminder_on"),
                        ("isOnlineMeeting", "is_online")):
        if body.get(key) is not None:
            out[column] = bool(body[key])
    if out["is_online"] and not out.get("online_url"):
        out["online_url"] = ("https://teams.microsoft.com/l/meetup-join/19%3ameeting_" + secrets.token_hex(16)
                             + "%40thread.v2/0")
    elif not out["is_online"]:
        out["online_url"] = ""
    if "location" in body:
        location = body["location"] or {}
        kind = _enum(location.get("locationType") or "default", LOCATION_TYPES)
        if isinstance(kind, GraphError):
            return kind
        out["location"], out["location_type"] = location.get("displayName") or "", kind
        out["location_address"] = {k: v for k, v in (location.get("address") or {}).items() if v is not None}
    if "attendees" in body:
        people = _attendees(body["attendees"] or [], row["attendees"])
        if isinstance(people, GraphError):
            return people
        out["attendees"] = people
    if "categories" in body:
        out["categories"] = [str(c) for c in body["categories"] or []]
    if "reminderMinutesBeforeStart" in body:
        minutes = body["reminderMinutesBeforeStart"]
        if minutes is None or minutes < 0:
            return bad_request("reminderMinutesBeforeStart must be 0 or more.", code="ErrorPropertyValidationFailure")
        out["reminder_minutes"] = minutes
    if "recurrence" in body:
        recurrence = _recurrence(body["recurrence"], _zone_of(out))
        if isinstance(recurrence, GraphError):
            return recurrence
        out["recurrence"] = recurrence
    start, end = _utc(out["start"]), _utc(out["end"])
    if end < start:
        return bad_request("The end time of the event must be on or after its start time.")
    if out["is_all_day"]:
        zone = _zone_of(out)
        if end <= start or from_utc(start, zone).time() != datetime.min.time() \
                or from_utc(end, zone).time() != datetime.min.time():
            return bad_request("An all-day event must start and end at midnight in its time zone and last at least "
                               "one day.", code="ErrorPropertyValidationFailure")
    out["last_modified"] = _iso_z(_now())
    return out


def create_event(account_id, body, calendar_id=None, zone="UTC"):
    owner = _mailbox(account_id)
    if owner is None:
        return _no_mailbox()
    calendar = owner if calendar_id is None else _owned_calendar(calendar_id, account_id)
    if calendar is None:
        return _not_found()
    if not calendar["can_edit"]:
        return _access_denied()
    if not body.get("start") or not body.get("end"):
        return bad_request("An event needs both a start and an end.", code="ErrorPropertyValidationFailure")
    now = _iso_z(_now())
    row = {"id": "AAMkAGevt" + secrets.token_hex(6), "calendar_id": calendar["id"], "subject": "", "body": "",
           "body_type": "text", "start": now, "end": now, "original_tz": "UTC", "is_all_day": False,
           "location": "", "location_type": "default", "location_address": {}, "attendees": [],
           "organizer_name": owner["owner_name"], "organizer_address": owner["owner_address"], "is_online": False,
           "online_url": "", "show_as": "busy", "importance": "normal", "sensitivity": "normal", "categories": [],
           "reminder_minutes": 15, "is_reminder_on": True, "created": now, "last_modified": now,
           "recurrence": None, "is_cancelled": False, "response": "organizer"}
    row = _apply_body(row, body)
    if isinstance(row, GraphError):
        return row
    _store.table("events").upsert(row)
    return {"@odata.context": _context(owner, "events/$entity"),
            **_event_view(_store.table("events").get(row["id"]), owner, zone)}


def update_event(event_id, account_id, body, zone="UTC"):
    owner = _mailbox(account_id)
    if owner is None:
        return _no_mailbox()
    row, occurrence = _event(event_id, account_id)
    if row is None:
        return _not_found()
    if occurrence is not None:
        return bad_request("This mock changes a series only through its series master; a single occurrence cannot "
                           "be updated on its own.")
    if not _owned_calendar(row["calendar_id"], account_id)["can_edit"]:
        return _access_denied()
    if body:
        changed = _apply_body(row, body)
        if isinstance(changed, GraphError):
            return changed
        _store.table("events").upsert(changed)
    return {"@odata.context": _context(owner, "events/$entity"),
            **_event_view(_store.table("events").get(row["id"]), owner, zone)}


def delete_event(event_id, account_id):
    if _mailbox(account_id) is None:
        return _no_mailbox()
    row, occurrence = _event(event_id, account_id)
    if row is None:
        return _not_found()
    if occurrence is not None:
        return bad_request("This mock deletes a series only through its series master; a single occurrence cannot "
                           "be deleted on its own.")
    if not _owned_calendar(row["calendar_id"], account_id)["can_edit"]:
        return _access_denied()
    _store.table("events").delete(row["id"])
    return None


# --- free/busy --------------------------------------------------------------------------------------

_RANK = {"free": 0, "tentative": 1, "busy": 2, "oof": 3, "workingElsewhere": 4}


def _schedule_items(address, owner, window_start, window_end):
    """Busy blocks for one address in the window.

    The owner's come from their default calendar as they show it. A colleague's
    are the meetings on that calendar they organize or were invited to (busy once
    accepted, tentative until they answer, none once declined), so a meeting the
    owner books shows on its invitees' schedules too, plus their other seeded
    commitments.
    """
    key = address.lower()
    is_owner = key == owner["owner_address"].lower()
    items = []
    for e in _events_in(owner["id"]):
        if e["is_cancelled"]:
            continue
        if is_owner:
            status = e.get("show_as") or "busy"
        elif e["organizer_address"].lower() == key:
            status = "busy"
        else:
            invited = next((a for a in e["attendees"] if a["address"].lower() == key), None)
            if invited is None or invited.get("response") == "declined":
                continue
            status = "busy" if invited.get("response") == "accepted" else "tentative"
        if status == "free":
            continue
        for start, end in occurrences(e, window_start, window_end):
            items.append({"isPrivate": e.get("sensitivity") == "private", "status": status,
                          "subject": e["subject"], "location": e["location"], "start": start, "end": end})
    if not is_owner:
        for b in _store.table("schedule_items").find(lambda s: str(s.get("address", "")).lower() == key):
            start, end = _utc(b["start"]), _utc(b["end"])
            if _overlaps(start, end, window_start, window_end):
                items.append({"isPrivate": False, "status": b.get("status") or "busy", "subject": b.get("subject") or "",
                              "location": b.get("location") or "", "start": start, "end": end})
    return sorted(items, key=lambda i: (i["start"], i["end"]))


def get_schedule(account_id, body, zone="UTC"):
    owner = _mailbox(account_id)
    if owner is None:
        return _no_mailbox()
    schedules = [s.strip() for s in body.get("schedules") or [] if s.strip()]
    if not schedules:
        return bad_request("schedules must name at least one email address.", code="ErrorInvalidParameter")
    if len(schedules) > 100:
        return bad_request("A free/busy request can name at most 100 schedules.", code="ErrorInvalidParameter")
    interval = body.get("availabilityViewInterval")
    interval = 30 if interval is None else interval
    if not 5 <= interval <= 1440:
        return bad_request("availabilityViewInterval must be between 5 and 1440 minutes.",
                           code="ErrorInvalidParameter")
    start = _time_input(body["startTime"], "startTime")
    if isinstance(start, GraphError):
        return start
    end = _time_input(body["endTime"], "endTime")
    if isinstance(end, GraphError):
        return end
    window_start, window_end = start[0], end[0]
    if window_end <= window_start:
        return bad_request("endTime must be after startTime.", code="ErrorInvalidParameter")
    if window_end - window_start > timedelta(days=62):
        return bad_request("The requested time window is longer than 62 days.", code="ErrorInvalidParameter")
    value = []
    for address in schedules:
        person = _store.table("people").get(address.lower())
        if person is None and address.lower() != owner["owner_address"].lower():
            value.append({"scheduleId": address, "availabilityView": "", "scheduleItems": [],
                          "error": {"message": f"The user {address} could not be found in the directory, so free/busy "
                                              "information is not available for it.",
                                    "responseCode": "ErrorMailRecipientNotFound"}})
            continue
        items = _schedule_items(address, owner, window_start, window_end)
        slots, cursor = [], window_start
        while cursor < window_end:
            slot_end = cursor + timedelta(minutes=interval)
            states = [_RANK.get(i["status"], 2) for i in items if i["start"] < slot_end and i["end"] > cursor]
            slots.append(str(max(states) if states else 0))
            cursor = slot_end
        hours = person or {"work_start": "08:00", "work_end": "17:00", "work_days": list(DAYS[:5]),
                           "time_zone": "Pacific Standard Time"}
        value.append({"scheduleId": address, "availabilityView": "".join(slots),
                      "scheduleItems": [{"isPrivate": i["isPrivate"], "status": i["status"],
                                         **({} if i["isPrivate"] else {"subject": i["subject"],
                                                                       "location": i["location"]}),
                                         "start": _time_view(i["start"], zone), "end": _time_view(i["end"], zone)}
                                        for i in items],
                      "workingHours": {"daysOfWeek": hours["work_days"],
                                       "startTime": f"{hours['work_start']}:00.0000000",
                                       "endTime": f"{hours['work_end']}:00.0000000",
                                       "timeZone": {"name": hours["time_zone"]}}})
    return {"@odata.context": f"{GRAPH}/$metadata#Collection(microsoft.graph.scheduleInformation)", "value": value}


_store.eager_load()
