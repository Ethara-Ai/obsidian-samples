"""FastAPI server wrapping healthex_data as REST endpoints.

A FHIR R4-style patient records API modelled on a health records aggregator,
not copied from a published API (see README.md), for the operations the
connector needs: list the patient's records by type (conditions, medications,
lab results, immunizations, visits) filtered by date and by provider, and get
one record. Every operation needs a bearer token from POST /oauth/token and
checks its own SMART-style scope. Errors are FHIR OperationOutcomes, request
validation failures included, and a search parameter the operation does not
take is a 400 rather than ignored.
"""

from typing import List, Optional

from fastapi import Depends, FastAPI, Query, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

import healthex_data
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

auth = healthex_data.auth
FhirError = healthex_data.FhirError
B = healthex_data.BASE
SCOPES = healthex_data.SCOPES

app = FastAPI(title="HealthEx API (Mock)", version="R4")
install_tracker(app)
install_admin_plane(app, store=healthex_data._store)
auth.install(app)

SHARED_PLANES = ("/admin", "/audit")


class FhirApiError(Exception):
    def __init__(self, error: FhirError):
        super().__init__(error.body["issue"][0]["diagnostics"])
        self.error = error


def _render(error: FhirError) -> JSONResponse:
    return JSONResponse(status_code=error.status, content=error.body, media_type="application/fhir+json")


@app.exception_handler(FhirApiError)
async def _fhir_api_error(_request: Request, exc: FhirApiError):
    return _render(exc.error)


@app.exception_handler(RequestValidationError)
async def _invalid_request(request: Request, exc: RequestValidationError):
    if request.url.path.startswith(SHARED_PLANES):
        return await request_validation_exception_handler(request, exc)
    err = exc.errors()[0]
    name = ".".join(str(p) for p in (err.get("loc") or ())[1:]) or "request"
    if err.get("type") == "int_parsing":
        return _render(healthex_data.invalid(f"{name} must be an integer"))
    return _render(healthex_data.invalid(f"{name} is invalid: {err.get('msg', '')}"))


@app.exception_handler(StarletteHTTPException)
async def _http_error(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith(SHARED_PLANES) or exc.status_code not in (404, 405):
        return await http_exception_handler(request, exc)
    if exc.status_code == 405:
        return _render(FhirError(405, "not-supported", "this mock serves only GET (search and read)"))
    return _render(healthex_data.not_found(
        f"{request.url.path} is not served; the resource types are {', '.join(SCOPES)}"))


def known_query(request: Request):
    """Refuse a search parameter the operation does not declare instead of ignoring it."""
    route = request.scope.get("route")
    allowed = {p.alias for p in route.dependant.query_params} if route is not None else set()
    for name in request.query_params.keys():
        if name not in allowed:
            raise FhirApiError(healthex_data.invalid(
                f"{name} is not a search parameter this operation takes; this mock refuses it rather than ignore it"))


STRICT = Depends(known_query)


@app.get("/health")
def health():
    return {"status": "ok"}


def _reply(result):
    if isinstance(result, FhirError):
        return _render(result)
    return JSONResponse(content=result, media_type="application/fhir+json")


def _search(kind: str, request: Request, date: Optional[List[str]], provider: Optional[str], count: int,
            offset: int):
    return _reply(healthex_data.search(kind, request.state.oauth["account_id"], str(request.base_url), date,
                                       provider, count, offset))


def _read(kind: str, record_id: str, request: Request):
    return _reply(healthex_data.read(kind, record_id, request.state.oauth["account_id"]))


@app.get(B + "/Condition", dependencies=[auth.require(SCOPES["Condition"]), STRICT])
def search_conditions(request: Request, date: Optional[List[str]] = Query(None), provider: Optional[str] = None,
                      _count: int = 20, _offset: int = 0):
    return _search("Condition", request, date, provider, _count, _offset)


@app.get(B + "/Condition/{record_id}", dependencies=[auth.require(SCOPES["Condition"]), STRICT])
def read_condition(record_id: str, request: Request):
    return _read("Condition", record_id, request)


@app.get(B + "/MedicationRequest", dependencies=[auth.require(SCOPES["MedicationRequest"]), STRICT])
def search_medications(request: Request, date: Optional[List[str]] = Query(None), provider: Optional[str] = None,
                       _count: int = 20, _offset: int = 0):
    return _search("MedicationRequest", request, date, provider, _count, _offset)


@app.get(B + "/MedicationRequest/{record_id}", dependencies=[auth.require(SCOPES["MedicationRequest"]), STRICT])
def read_medication(record_id: str, request: Request):
    return _read("MedicationRequest", record_id, request)


@app.get(B + "/Observation", dependencies=[auth.require(SCOPES["Observation"]), STRICT])
def search_lab_results(request: Request, date: Optional[List[str]] = Query(None), provider: Optional[str] = None,
                       _count: int = 20, _offset: int = 0):
    return _search("Observation", request, date, provider, _count, _offset)


@app.get(B + "/Observation/{record_id}", dependencies=[auth.require(SCOPES["Observation"]), STRICT])
def read_lab_result(record_id: str, request: Request):
    return _read("Observation", record_id, request)


@app.get(B + "/Immunization", dependencies=[auth.require(SCOPES["Immunization"]), STRICT])
def search_immunizations(request: Request, date: Optional[List[str]] = Query(None), provider: Optional[str] = None,
                         _count: int = 20, _offset: int = 0):
    return _search("Immunization", request, date, provider, _count, _offset)


@app.get(B + "/Immunization/{record_id}", dependencies=[auth.require(SCOPES["Immunization"]), STRICT])
def read_immunization(record_id: str, request: Request):
    return _read("Immunization", record_id, request)


@app.get(B + "/Encounter", dependencies=[auth.require(SCOPES["Encounter"]), STRICT])
def search_visits(request: Request, date: Optional[List[str]] = Query(None), provider: Optional[str] = None,
                  _count: int = 20, _offset: int = 0):
    return _search("Encounter", request, date, provider, _count, _offset)


@app.get(B + "/Encounter/{record_id}", dependencies=[auth.require(SCOPES["Encounter"]), STRICT])
def read_visit(record_id: str, request: Request):
    return _read("Encounter", record_id, request)
