"""Data access module for the Calendly mock service.

Serves exactly the operations the connector needs -- get the current user,
list event types, list scheduled events with status and date filters, get one
scheduled event, list an event's invitees, and cancel a scheduled event -- in
the shape of the Calendly API v2 (api.calendly.com). Resources are named by
their URIs, lists come back as {"collection", "pagination"}, and every read
and write is scoped to the organization of the Calendly user the presented
token's connected account is: Dana Whitfield, owner of Lakeshore Design
Studio's organization, the account the studio's Google Drive, Docs, Sheets,
Contacts, Forms, Slides and Tasks seeds serve.

Mock simplifications (also stated in api_test_results.md): solo event types
and one-to-many group event types only, no routing forms, webhooks,
availability or scheduling links, and cancellation is the one write.
"""

import base64
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

DATA_DIR = Path(__file__).parent

sys.path.insert(0, str(DATA_DIR.parent))
import _mock_clock  # noqa: E402
from _mutable_store import get_store, opt_bool, opt_int, read_seed_with_ctx  # noqa: E402
from _connector_auth import ConnectorAuth  # noqa: E402

_API = "calendly-api"
_store = get_store(_API)

BASE = "https://api.calendly.com"
DEFAULT_COUNT, MAX_COUNT = 20, 100
REASON_LIMIT = 10000


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _json_cell(value, empty):
    """A JSON-encoded cell (as a CSV overlay carries it) decoded; ``empty`` for a blank one."""
    if isinstance(value, str) and value.strip()[:1] in ("[", "{"):
        try:
            return json.loads(value)
        except ValueError:
            return empty
    if value is None or value == "":
        return empty
    return value


def _coerce_event_type(r):
    out = _strip_ctx(r)
    out["locations"] = _json_cell(out.get("locations"), [])
    out["custom_questions"] = _json_cell(out.get("custom_questions"), [])
    out["active"] = opt_bool(out, "active", default=True)
    out["secret"] = opt_bool(out, "secret")
    out["duration"] = opt_int(out, "duration", 30)
    out["position"] = opt_int(out, "position", 0)
    out["kind"] = out.get("kind") or "solo"
    out["invitee_limit"] = opt_int(out, "invitee_limit", 1)
    return out


def _coerce_event(r):
    out = _strip_ctx(r)
    out["location"] = _json_cell(out.get("location"), {})
    out["cancellation"] = _json_cell(out.get("cancellation"), None) or None
    out["guests"] = _json_cell(out.get("guests"), [])
    return out


def _coerce_invitee(r):
    out = _strip_ctx(r)
    out["questions_and_answers"] = _json_cell(out.get("questions_and_answers"), [])
    out["cancellation"] = _json_cell(out.get("cancellation"), None) or None
    out["rescheduled"] = opt_bool(out, "rescheduled")
    return out


_store.register("accounts", primary_key="account_id",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("accounts.json", "accounts")])
_store.register("organizations", primary_key="uuid",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("organizations.json", "organizations")])
_store.register("users", primary_key="uuid",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("users.json", "users")])
_store.register("event_types", primary_key="uuid",
                initial_loader=lambda: [_coerce_event_type(r) for r in _load("event_types.json", "event_types")],
                row_coercer=_coerce_event_type)
_store.register("scheduled_events", primary_key="uuid",
                initial_loader=lambda: [_coerce_event(r) for r in _load("scheduled_events.json", "scheduled_events")],
                row_coercer=_coerce_event)
_store.register("invitees", primary_key="uuid",
                initial_loader=lambda: [_coerce_invitee(r) for r in _load("invitees.json", "invitees")],
                row_coercer=_coerce_invitee)

auth = ConnectorAuth(_API, store=_store, data_dir=DATA_DIR)


class CalendlyError:
    """A Calendly error body ({"title", "message", "details"}) and the HTTP status it is served with."""

    def __init__(self, status, title, message, details=None):
        self.status = status
        self.body = {"title": title, "message": message}
        if details:
            self.body["details"] = details


def invalid(parameter, message):
    return CalendlyError(400, "Invalid Argument", "The supplied parameters are invalid.",
                         [{"parameter": parameter, "message": message}])


def not_found():
    return CalendlyError(404, "Resource Not Found", "The server could not find the requested resource.")


def _denied(message="You do not have permission to access this resource."):
    return CalendlyError(403, "Permission Denied", message)


def _stamp(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%S.000000Z")


def _moment(text):
    """An aware UTC datetime from an ISO 8601 string; None when it is not one."""
    try:
        moment = datetime.fromisoformat(str(text).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment.astimezone(timezone.utc) if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _uri(kind, key):
    return f"{BASE}/{kind}/{key}"


def _uuid_of(value, kind):
    """The uuid at the end of a Calendly URI of ``kind`` (any host), or None."""
    match = re.fullmatch(rf"https?://[^/]+/{kind}/([A-Za-z0-9-]+)", str(value or "").strip())
    return match.group(1) if match else None


# --- lookup -------------------------------------------------------------------------------------

def _me(account_id):
    account = _store.table("accounts").get(account_id)
    return _store.table("users").get(account["user_uuid"]) if account else None


def _members(org_uuid):
    return {u["uuid"]: u for u in _store.table("users").find(lambda u: u["org_uuid"] == org_uuid)}


def _owner_scope(me, user, organization):
    """The member uuids a list covers for ``user``/``organization`` query values, or a CalendlyError."""
    members = _members(me["org_uuid"])
    if user is None and organization is None:
        return invalid("organization", "organization or user is required")
    if organization is not None:
        org = _uuid_of(organization, "organizations")
        if org is None:
            return invalid("organization", "must be a valid organization URI")
        if org != me["org_uuid"]:
            return _denied()
    if user is None:
        return set(members)
    key = _uuid_of(user, "users")
    if key is None:
        return invalid("user", "must be a valid user URI")
    if key not in members:
        return _denied()
    if key != me["uuid"] and me.get("role") not in ("owner", "admin"):
        return _denied()
    return {key}


def _event(event_uuid, me):
    row = _store.table("scheduled_events").get(event_uuid)
    if row is None or row["user_uuid"] not in _members(me["org_uuid"]):
        return None
    return row


def _invitees(event_uuid):
    return _store.table("invitees").find(lambda i: i["event_uuid"] == event_uuid)


# --- paging -------------------------------------------------------------------------------------

def _token(offset):
    return base64.urlsafe_b64encode(f"cy:{offset}".encode()).decode().rstrip("=")


def _offset(token):
    try:
        text = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode()
    except (ValueError, UnicodeDecodeError):
        return None
    return int(text[3:]) if re.fullmatch(r"cy:\d+", text) else None


def _page(views, count, page_token, link, query):
    if count is not None and not 1 <= count <= MAX_COUNT:
        return invalid("count", f"must be between 1 and {MAX_COUNT}")
    start = 0
    if page_token is not None:
        start = _offset(page_token)
        if start is None:
            return invalid("page_token", "is invalid")
    size = count or DEFAULT_COUNT
    window = views[start:start + size]
    params = {k: v for k, v in query.items() if v is not None}

    def link_to(offset):
        return f"{link}?{urlencode({**params, 'count': size, 'page_token': _token(offset)})}"

    has_next, has_previous = start + size < len(views), start > 0
    return {"collection": window, "pagination": {
        "count": len(window), "next_page": link_to(start + size) if has_next else None,
        "previous_page": link_to(max(0, start - size)) if has_previous else None,
        "next_page_token": _token(start + size) if has_next else None,
        "previous_page_token": _token(max(0, start - size)) if has_previous else None}}


def _sort(sort, fields, default):
    """(field, descending) from a ``field:direction`` sort value, or a CalendlyError."""
    text = sort or default
    match = re.fullmatch(r"(\w+):(asc|desc)", text)
    if not match or match.group(1) not in fields:
        return invalid("sort", f"must be one of {', '.join(f + ':asc|desc' for f in fields)}")
    return match.group(1), match.group(2) == "desc"


# --- rendering ------------------------------------------------------------------------------

def user_view(user):
    org = _store.table("organizations").get(user["org_uuid"])
    return {"uri": _uri("users", user["uuid"]), "name": user["name"], "slug": user["slug"], "email": user["email"],
            "scheduling_url": f"https://calendly.com/{user['slug']}", "timezone": user["timezone"],
            "time_notation": "12h", "avatar_url": None, "created_at": user["created_at"],
            "updated_at": user["updated_at"],
            "current_organization": _uri("organizations", org["uuid"]) if org else None, "resource_type": "User",
            "locale": "en"}


def event_type_view(row):
    owner = _store.table("users").get(row["user_uuid"]) or {}
    return {"uri": _uri("event_types", row["uuid"]), "name": row["name"], "active": row["active"],
            "booking_method": "instant", "slug": row["slug"],
            "scheduling_url": f"https://calendly.com/{owner.get('slug', '')}/{row['slug']}",
            "duration": row["duration"], "duration_options": None, "kind": row["kind"], "pooling_type": None,
            "type": "StandardEventType", "color": row["color"], "created_at": row["created_at"],
            "updated_at": row["updated_at"], "internal_note": row.get("internal_note") or None,
            "description_plain": row.get("description") or None,
            "description_html": f"<p>{row['description']}</p>" if row.get("description") else None,
            "profile": {"type": "User", "name": owner.get("name"), "owner": _uri("users", row["user_uuid"])},
            "secret": row["secret"], "deleted_at": None, "admin_managed": False, "locations": row["locations"],
            "position": row["position"], "custom_questions": row["custom_questions"], "locale": "en"}


def event_view(row):
    host = _store.table("users").get(row["user_uuid"]) or {}
    invitees = _invitees(row["uuid"])
    event_type = _store.table("event_types").get(row["event_type_uuid"]) or {}
    view = {"uri": _uri("scheduled_events", row["uuid"]), "name": row["name"],
            "meeting_notes_plain": row.get("meeting_notes") or None,
            "meeting_notes_html": f"<p>{row['meeting_notes']}</p>" if row.get("meeting_notes") else None,
            "status": row["status"], "start_time": row["start_time"], "end_time": row["end_time"],
            "event_type": _uri("event_types", row["event_type_uuid"]), "location": row["location"],
            "invitees_counter": {"total": len(invitees), "active": sum(i["status"] == "active" for i in invitees),
                                 "limit": event_type.get("invitee_limit", 1)},
            "created_at": row["created_at"], "updated_at": row["updated_at"],
            "event_memberships": [{"user": _uri("users", row["user_uuid"]), "user_email": host.get("email"),
                                   "user_name": host.get("name"), "buffered_start_time": row["start_time"],
                                   "buffered_end_time": row["end_time"]}],
            "event_guests": [{"email": g, "created_at": row["created_at"], "updated_at": row["created_at"]}
                             for g in row["guests"]]}
    if row["cancellation"]:
        view["cancellation"] = row["cancellation"]
    return view


def invitee_view(row):
    view = {"uri": f"{_uri('scheduled_events', row['event_uuid'])}/invitees/{row['uuid']}", "email": row["email"],
            "first_name": row.get("first_name") or None, "last_name": row.get("last_name") or None,
            "name": row["name"], "status": row["status"], "questions_and_answers": row["questions_and_answers"],
            "timezone": row["timezone"], "event": _uri("scheduled_events", row["event_uuid"]),
            "created_at": row["created_at"], "updated_at": row["updated_at"],
            "tracking": {"utm_campaign": None, "utm_source": None, "utm_medium": None, "utm_content": None,
                         "utm_term": None, "salesforce_uuid": None},
            "text_reminder_number": None, "rescheduled": row["rescheduled"], "old_invitee": None,
            "new_invitee": None, "cancel_url": f"https://calendly.com/cancellations/{row['uuid']}",
            "reschedule_url": f"https://calendly.com/reschedulings/{row['uuid']}", "routing_form_submission": None,
            "payment": None, "no_show": None, "reconfirmation": None, "scheduling_method": None,
            "invitee_scheduled_by": None}
    if row["cancellation"]:
        view["cancellation"] = row["cancellation"]
    return view


# --- operations ------------------------------------------------------------------------------------

def current_user(account_id):
    me = _me(account_id)
    return not_found() if me is None else {"resource": user_view(me)}


def list_event_types(account_id, link, user=None, organization=None, active=None, sort=None, count=None,
                     page_token=None):
    me = _me(account_id)
    if me is None:
        return not_found()
    owners = _owner_scope(me, user, organization)
    if isinstance(owners, CalendlyError):
        return owners
    order = _sort(sort, ("name", "position", "created_at", "updated_at"), "name:asc")
    if isinstance(order, CalendlyError):
        return order
    rows = _store.table("event_types").find(lambda t: t["user_uuid"] in owners
                                            and (active is None or t["active"] == active))
    field, descending = order
    rows.sort(key=lambda t: (str(t[field]).casefold() if field == "name" else t[field], t["uuid"]), reverse=descending)
    return _page([event_type_view(t) for t in rows], count, page_token, link, {
        "user": user, "organization": organization,
        "active": None if active is None else str(active).lower(), "sort": sort})


def list_scheduled_events(account_id, link, user=None, organization=None, invitee_email=None, status=None,
                          min_start_time=None, max_start_time=None, sort=None, count=None, page_token=None):
    me = _me(account_id)
    if me is None:
        return not_found()
    owners = _owner_scope(me, user, organization)
    if isinstance(owners, CalendlyError):
        return owners
    if status is not None and status not in ("active", "canceled"):
        return invalid("status", "must be one of active, canceled")
    bounds = {}
    for name, value in (("min_start_time", min_start_time), ("max_start_time", max_start_time)):
        if value is not None:
            bounds[name] = _moment(value)
            if bounds[name] is None:
                return invalid(name, "must be a valid ISO 8601 date and time")
    order = _sort(sort, ("start_time",), "start_time:asc")
    if isinstance(order, CalendlyError):
        return order
    email = (invitee_email or "").strip().casefold()

    def keep(event):
        start = _moment(event["start_time"])
        if event["user_uuid"] not in owners or (status and event["status"] != status):
            return False
        if "min_start_time" in bounds and start < bounds["min_start_time"]:
            return False
        if "max_start_time" in bounds and start >= bounds["max_start_time"]:
            return False
        return not email or any(i["email"].casefold() == email for i in _invitees(event["uuid"]))

    rows = sorted(_store.table("scheduled_events").find(keep), key=lambda e: (e["start_time"], e["uuid"]),
                  reverse=order[1])
    return _page([event_view(e) for e in rows], count, page_token, link, {
        "user": user, "organization": organization, "invitee_email": invitee_email, "status": status,
        "min_start_time": min_start_time, "max_start_time": max_start_time, "sort": sort})


def get_scheduled_event(event_uuid, account_id):
    me = _me(account_id)
    event = _event(event_uuid, me) if me else None
    return not_found() if event is None else {"resource": event_view(event)}


def list_invitees(event_uuid, account_id, link, status=None, sort=None, email=None, count=None, page_token=None):
    me = _me(account_id)
    event = _event(event_uuid, me) if me else None
    if event is None:
        return not_found()
    if status is not None and status not in ("active", "canceled"):
        return invalid("status", "must be one of active, canceled")
    order = _sort(sort, ("created_at",), "created_at:asc")
    if isinstance(order, CalendlyError):
        return order
    wanted = (email or "").strip().casefold()
    rows = [i for i in _invitees(event_uuid) if (status is None or i["status"] == status)
            and (not wanted or i["email"].casefold() == wanted)]
    rows.sort(key=lambda i: (i["created_at"], i["uuid"]), reverse=order[1])
    return _page([invitee_view(i) for i in rows], count, page_token, link,
                 {"status": status, "sort": sort, "email": email})


def cancel_event(event_uuid, account_id, reason=None):
    me = _me(account_id)
    event = _event(event_uuid, me) if me else None
    if event is None:
        return not_found()
    if event["user_uuid"] != me["uuid"] and me.get("role") not in ("owner", "admin"):
        return _denied()
    if event["status"] == "canceled":
        return _denied("Event is already canceled")
    now = _mock_clock.now(timezone.utc)
    if reason is not None and len(reason) > REASON_LIMIT:
        return invalid("reason", f"must be at most {REASON_LIMIT} characters")
    cancellation = {"canceled_by": me["name"], "reason": reason or None, "canceler_type": "host",
                    "created_at": _stamp(now)}
    _store.table("scheduled_events").upsert({**event, "status": "canceled", "cancellation": cancellation,
                                             "updated_at": _stamp(now)})
    for invitee in _invitees(event_uuid):
        if invitee["status"] == "active":
            _store.table("invitees").upsert({**invitee, "status": "canceled", "cancellation": cancellation,
                                             "updated_at": _stamp(now)})
    return {"resource": cancellation}


_store.eager_load()
