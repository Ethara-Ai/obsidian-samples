"""Data access module for the HealthEx mock service.

A FHIR R4-style patient records API modelled on what a health records
aggregator serves, not copied from a published API (see README.md). It lists
the connected patient's records by type (Condition, MedicationRequest,
Observation for lab results, Immunization, Encounter for visits) as searchset
Bundles, filtered by date and by provider, and reads one record. Every read is
scoped to the patient the presented token's connected account holds.

Each record row keeps its FHIR resource with the organization and practitioner
it came from and the date the date filter uses. Mock simplifications (also
stated in api_test_results.md): read-only, no Patient, Practitioner,
Organization, DiagnosticReport, AllergyIntolerance or DocumentReference
resources, no _include, _sort or chained search, and no other search
parameters.
"""

import re
import sys
from calendar import monthrange
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

DATA_DIR = Path(__file__).parent

sys.path.insert(0, str(DATA_DIR.parent))
from _mutable_store import get_store, read_seed_with_ctx  # noqa: E402
from _connector_auth import ConnectorAuth  # noqa: E402

_API = "healthex-api"
_store = get_store(_API)

BASE = "/fhir/R4"
SCOPES = {"Condition": "patient/Condition.read", "MedicationRequest": "patient/MedicationRequest.read",
          "Observation": "patient/Observation.read", "Immunization": "patient/Immunization.read",
          "Encounter": "patient/Encounter.read"}
PREFIXES = ("eq", "gt", "lt", "ge", "le")


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


for _table, _file in (("patients", "patients.json"), ("organizations", "organizations.json"),
                      ("practitioners", "practitioners.json"), ("records", "records.json")):
    _store.register(_table, primary_key="id",
                    initial_loader=lambda f=_file, t=_table: [_strip_ctx(r) for r in _load(f, t)])

auth = ConnectorAuth(_API, store=_store, data_dir=DATA_DIR)


class FhirError:
    """A FHIR OperationOutcome and its HTTP status."""

    def __init__(self, status, code, diagnostics):
        self.status = status
        self.body = {"resourceType": "OperationOutcome",
                     "issue": [{"severity": "error", "code": code, "diagnostics": diagnostics}]}


def invalid(message):
    return FhirError(400, "invalid", message)


def not_found(message):
    return FhirError(404, "not-found", message)


# --- search parameters --------------------------------------------------------------------------

def _period(text):
    """The first and last day a FHIR date value (YYYY, YYYY-MM, YYYY-MM-DD or a date-time) covers."""
    if re.fullmatch(r"\d{4}", text):
        year = int(text)
        return date(year, 1, 1), date(year, 12, 31)
    if re.fullmatch(r"\d{4}-\d{2}", text):
        year, month = int(text[:4]), int(text[5:])
        if not 1 <= month <= 12:
            return None
        return date(year, month, 1), date(year, month, monthrange(year, month)[1])
    try:
        day = date.fromisoformat(text[:10])
    except ValueError:
        return None
    if len(text) > 10 and text[10] != "T":
        return None
    return day, day


def _date_tests(values):
    tests = []
    for value in values or []:
        prefix = value[:2] if value[:2] in PREFIXES else "eq"
        period = _period(value[2:] if value[:2] in PREFIXES else value)
        if period is None:
            return invalid(f"date {value!r} is not a FHIR date: use an optional prefix ({', '.join(PREFIXES)}) and "
                           "YYYY, YYYY-MM or YYYY-MM-DD, for example ge2026-01-01")
        tests.append((prefix, period))
    return tests


def _matches_dates(day, tests):
    for prefix, (start, end) in tests:
        if prefix == "eq" and not start <= day <= end:
            return False
        if (prefix == "gt" and not day > end) or (prefix == "lt" and not day < start):
            return False
        if (prefix == "ge" and not day >= start) or (prefix == "le" and not day <= end):
            return False
    return True


def _providers(text):
    """Organization and practitioner ids a provider value names: an id, a reference, or a name."""
    wanted = text.strip().lower()
    wanted = wanted.split("/", 1)[1] if wanted.startswith(("organization/", "practitioner/")) else wanted
    orgs = {o["id"] for o in _store.table("organizations").rows()
            if wanted in (o["id"].lower(), o["name"].lower())}
    pracs = {p["id"] for p in _store.table("practitioners").rows()
             if wanted in (p["id"].lower(), p["name"].lower(), f"{p['name']}, {p['credential']}".lower())}
    if not orgs and not pracs:
        known = sorted(o["name"] for o in _store.table("organizations").rows())
        return invalid(f"provider {text!r} names no organization or practitioner in these records; organizations "
                       f"are {', '.join(known)}")
    return orgs, pracs


# --- search and read ----------------------------------------------------------------------------

def search(kind, account_id, base_url, dates=None, provider=None, count=20, offset=0):
    if not 1 <= count <= 100:
        return invalid("_count must be between 1 and 100")
    if offset < 0:
        return invalid("_offset must not be negative")
    tests = _date_tests(dates)
    if isinstance(tests, FhirError):
        return tests
    named = _providers(provider) if provider is not None else None
    if isinstance(named, FhirError):
        return named
    rows = [r for r in _store.table("records").find(lambda r: r["type"] == kind and r["owner_account_id"] == account_id)
            if _matches_dates(date.fromisoformat(r["date"]), tests)
            and (named is None or r["organization_id"] in named[0] or r["practitioner_id"] in named[1])]
    rows.sort(key=lambda r: (r["date"], r["id"]), reverse=True)
    page = rows[offset:offset + count]
    root = base_url.rstrip("/") + BASE

    def link(at):
        query = [("date", d) for d in dates or []] + ([("provider", provider)] if provider is not None else [])
        return f"{root}/{kind}?" + urlencode(query + [("_count", count), ("_offset", at)])

    links = [{"relation": "self", "url": link(offset)}]
    if offset + count < len(rows):
        links.append({"relation": "next", "url": link(offset + count)})
    if offset > 0:
        links.append({"relation": "previous", "url": link(max(0, offset - count))})
    return {"resourceType": "Bundle", "type": "searchset", "total": len(rows), "link": links,
            "entry": [{"fullUrl": f"{root}/{kind}/{r['id']}", "resource": r["resource"], "search": {"mode": "match"}}
                      for r in page]}


def read(kind, record_id, account_id):
    row = _store.table("records").get(record_id)
    if row is None or row["type"] != kind or row["owner_account_id"] != account_id:
        return not_found(f"{kind}/{record_id} is not a record of this patient")
    return row["resource"]


_store.eager_load()
