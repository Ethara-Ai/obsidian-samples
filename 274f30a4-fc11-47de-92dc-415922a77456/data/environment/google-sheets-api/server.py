"""FastAPI server wrapping google_sheets_data as REST endpoints.

Mirrors the Google Sheets API v4 (sheets.googleapis.com/v4) for the five
operations the connector needs: get a spreadsheet, read values for an A1 range,
update values for an A1 range, append rows, and create a spreadsheet. Values are
addressed under the spreadsheet id and an A1 range exactly as in the real API.
Every operation needs a bearer token from POST /oauth/token, and each one checks
its own scope, so a connected account is not by itself permission to write.
Errors use Google's own envelope, including request validation failures and
query parameters the method does not take, which Google refuses rather than
ignores.
"""

import json
import re
from typing import List, Literal, Optional, Union

from fastapi import Depends, FastAPI, Query, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, StrictBool, StrictFloat, StrictInt, StrictStr
from starlette.exceptions import HTTPException as StarletteHTTPException

import google_sheets_data
import _linked_peer
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

V = "/v4/spreadsheets"
auth = google_sheets_data.auth
GoogleError = google_sheets_data.GoogleError

app = FastAPI(title="Google Sheets API (Mock)", version="v4")
install_tracker(app)
install_admin_plane(app, store=google_sheets_data._store)
# Drive reads and changes this mock's files live, through the peer routes (_linked_peer.py).
_linked_peer.install(app, "google-sheets-api", google_sheets_data)
auth.install(app)

SHARED_PLANES = ("/admin", "/audit")
ENUM_TYPES = {
    "valueInputOption": "ValueInputOption", "valueRenderOption": "ValueRenderOption",
    "responseValueRenderOption": "ValueRenderOption", "dateTimeRenderOption": "DateTimeRenderOption",
    "responseDateTimeRenderOption": "DateTimeRenderOption", "majorDimension": "Dimension",
    "insertDataOption": "InsertDataOption",
}
SCALAR_TYPES = (("int", "TYPE_INT32"), ("bool", "TYPE_BOOL"), ("string", "TYPE_STRING"), ("float", "TYPE_DOUBLE"))
# Real Spreadsheet fields this service does not implement, by parent path, so the
# refusal names them as unsupported instead of calling them unknown.
UNSUPPORTED_FIELDS = {
    (): {"namedRanges", "developerMetadata", "dataSources", "dataSourceSchedules"},
    ("properties",): {"autoRecalc", "defaultFormat", "iterativeCalculationSettings", "spreadsheetTheme",
                      "importFunctionsExternalUrlAccessAllowed"},
    ("sheets", "*"): {"data", "merges", "conditionalFormats", "filterViews", "protectedRanges", "basicFilter",
                      "charts", "bandedRanges", "developerMetadata", "rowGroups", "columnGroups", "slicers"},
    ("sheets", "*", "properties"): {"sheetType", "hidden", "tabColor", "tabColorStyle", "rightToLeft",
                                    "dataSourceSheetProperties"},
    ("sheets", "*", "properties", "gridProperties"): {"frozenColumnCount", "hideGridlines", "rowGroupControlAfter",
                                                      "columnGroupControlAfter"},
}
OUTPUT_ONLY = {"spreadsheetId", "spreadsheetUrl"}


class GoogleApiError(Exception):
    def __init__(self, error: GoogleError):
        super().__init__(error.body["error"]["message"])
        self.error = error


def _render(error: GoogleError) -> JSONResponse:
    return JSONResponse(status_code=error.status, content=error.body)


def _snake(name) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", str(name)).lower()


def _google_path(parts) -> str:
    out = ""
    for part in parts:
        out += f"[{part}]" if isinstance(part, int) else ("." if out else "") + _snake(part)
    return out


def _validation_error(exc: RequestValidationError) -> GoogleError:
    err = exc.errors()[0]
    loc = list(err.get("loc") or [])
    where, parts = (loc[0], loc[1:]) if loc else ("body", [])
    kind, value = err.get("type", ""), err.get("input")
    shown = json.dumps(value, default=str)
    if kind == "json_invalid":
        return GoogleError(400, "Invalid JSON payload received. Unexpected token.", field="")
    if where == "body" and len(parts) >= 3 and parts[0] == "values" and isinstance(parts[1], int) \
            and isinstance(parts[2], int):
        return GoogleError(400, f"Invalid values[{parts[1]}][{parts[2]}]: {shown}",
                           field=f"data.values[{parts[1]}][{parts[2]}]")
    if kind == "extra_forbidden" and parts:
        name, parent = str(parts[-1]), parts[:-1]
        shape = tuple("*" if isinstance(p, int) else p for p in parent)
        path = _google_path(parent)
        if not parent and name in OUTPUT_ONLY:
            return GoogleError(400, f"'{name}' is output only; the service assigns it.", field=name)
        if name in UNSUPPORTED_FIELDS.get(shape, ()):
            where_text = f" at '{path}'" if path else ""
            return GoogleError(400, f"'{name}'{where_text} is not supported by this service.",
                               field=f"{path}.{_snake(name)}" if path else _snake(name))
        message = (f'Invalid JSON payload received. Unknown name "{name}"'
                   + (f" at '{path}'" if path else "") + ": Cannot find field.")
        return GoogleError(400, message, field=path)
    path = _google_path(parts)
    if parts and str(parts[-1]) in ENUM_TYPES:
        return GoogleError(400, f"Invalid value at '{path}' (type.googleapis.com/google.apps.sheets.v4."
                                f"{ENUM_TYPES[str(parts[-1])]}), {shown}", field=path)
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

Render = Literal["FORMATTED_VALUE", "UNFORMATTED_VALUE", "FORMULA"]
DateRender = Literal["SERIAL_NUMBER", "FORMATTED_STRING"]
InputOption = Literal["RAW", "USER_ENTERED"]
Dimension = Literal["ROWS", "COLUMNS"]


@app.get("/health")
def health():
    return {"status": "ok"}


def _reply(result, fields=None):
    if isinstance(result, GoogleError):
        return _render(result)
    return google_sheets_data.apply_fields(result, fields)


def _mask(fields: Optional[str]):
    tree = google_sheets_data.parse_fields(fields)
    if isinstance(tree, GoogleError):
        raise GoogleApiError(tree)
    return tree


def _account(request: Request) -> str:
    return request.state.oauth["account_id"]


# --- spreadsheets.get ------------------------------------------------------------------------

@app.get(V + "/{spreadsheetId}", dependencies=[auth.require("spreadsheets.readonly", implied_by=("spreadsheets",)), STRICT])
def get_spreadsheet(
    spreadsheetId: str,
    request: Request,
    ranges: Optional[List[str]] = Query(None),
    includeGridData: bool = False,
    fields: Optional[str] = None,
):
    tree = _mask(fields)
    # Google ignores includeGridData when a field mask is set: the mask alone decides.
    grid = True if tree is not None else includeGridData
    return _reply(google_sheets_data.get_spreadsheet(spreadsheetId, _account(request), ranges=ranges,
                                                     include_grid_data=grid), tree)


# --- spreadsheets.values.get --------------------------------------------------------------------

@app.get(V + "/{spreadsheetId}/values/{range}", dependencies=[auth.require("spreadsheets.readonly", implied_by=("spreadsheets",)), STRICT])
def get_values(
    spreadsheetId: str,
    range: str,
    request: Request,
    majorDimension: Dimension = "ROWS",
    valueRenderOption: Render = "FORMATTED_VALUE",
    dateTimeRenderOption: DateRender = "SERIAL_NUMBER",
    fields: Optional[str] = None,
):
    tree = _mask(fields)
    return _reply(google_sheets_data.get_values(spreadsheetId, _account(request), range, major=majorDimension,
                                                render=valueRenderOption, datetime_render=dateTimeRenderOption),
                  tree)


# --- spreadsheets.values.update / append ---------------------------------------------------------

CellValue = Union[StrictBool, StrictInt, StrictFloat, StrictStr, None]


class ValueRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    range: Optional[str] = None
    majorDimension: Optional[Dimension] = None
    values: Optional[List[List[CellValue]]] = None


@app.put(V + "/{spreadsheetId}/values/{range}", dependencies=[auth.require("spreadsheets"), STRICT])
def update_values(
    spreadsheetId: str,
    range: str,
    request: Request,
    body: Optional[ValueRange] = None,
    valueInputOption: Optional[InputOption] = None,
    includeValuesInResponse: bool = False,
    responseValueRenderOption: Render = "FORMATTED_VALUE",
    responseDateTimeRenderOption: DateRender = "SERIAL_NUMBER",
    fields: Optional[str] = None,
):
    tree = _mask(fields)
    body = body or ValueRange()
    return _reply(google_sheets_data.update_values(
        spreadsheetId, _account(request), range, body.values, valueInputOption, major=body.majorDimension,
        body_range=body.range, include_values=includeValuesInResponse, render=responseValueRenderOption,
        datetime_render=responseDateTimeRenderOption), tree)


@app.post(V + "/{spreadsheetId}/values/{range}:append", dependencies=[auth.require("spreadsheets"), STRICT])
def append_values(
    spreadsheetId: str,
    range: str,
    request: Request,
    body: Optional[ValueRange] = None,
    valueInputOption: Optional[InputOption] = None,
    insertDataOption: Literal["OVERWRITE", "INSERT_ROWS"] = "OVERWRITE",
    includeValuesInResponse: bool = False,
    responseValueRenderOption: Render = "FORMATTED_VALUE",
    responseDateTimeRenderOption: DateRender = "SERIAL_NUMBER",
    fields: Optional[str] = None,
):
    tree = _mask(fields)
    body = body or ValueRange()
    return _reply(google_sheets_data.append_values(
        spreadsheetId, _account(request), range, body.values, valueInputOption, insert_option=insertDataOption,
        major=body.majorDimension, body_range=body.range, include_values=includeValuesInResponse,
        render=responseValueRenderOption, datetime_render=responseDateTimeRenderOption), tree)


# --- spreadsheets.create --------------------------------------------------------------------------

class GridProperties(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rowCount: Optional[int] = None
    columnCount: Optional[int] = None
    frozenRowCount: Optional[int] = None


class SheetProperties(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sheetId: Optional[int] = None
    title: Optional[str] = None
    index: Optional[int] = None
    gridProperties: Optional[GridProperties] = None


class SheetSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    properties: Optional[SheetProperties] = None


class SpreadsheetProperties(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = None
    locale: Optional[str] = None
    timeZone: Optional[str] = None


class SpreadsheetBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    properties: Optional[SpreadsheetProperties] = None
    sheets: Optional[List[SheetSpec]] = None


@app.post(V, dependencies=[auth.require("spreadsheets"), STRICT])
def create_spreadsheet(request: Request, body: Optional[SpreadsheetBody] = None, fields: Optional[str] = None):
    tree = _mask(fields)
    body = body or SpreadsheetBody()
    properties = body.properties.model_dump(exclude_none=True) if body.properties else None
    sheets = [s.model_dump(exclude_none=True) for s in body.sheets] if body.sheets else None
    return _reply(google_sheets_data.create_spreadsheet(_account(request), properties=properties, sheets=sheets),
                  tree)
