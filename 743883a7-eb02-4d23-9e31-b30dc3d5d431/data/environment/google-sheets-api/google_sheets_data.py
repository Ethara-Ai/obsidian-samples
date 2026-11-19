"""Data access module for the Google Sheets API mock service.

Serves exactly the five Google Sheets operations the connector needs -- get a
spreadsheet, read values for an A1 range, update values for an A1 range, append
rows, create a spreadsheet -- for the spreadsheets one connected account owns.
The seed shares its spreadsheet ids and titles with google-drive-api, so a
spreadsheet found through Drive opens here.

Values are addressed as in the real API: under the spreadsheet id with an A1
range such as ``'Lobby Finishes'!A2:K17``, ``A1:C5`` (the first sheet),
``Budget!B:B`` or ``Invoices`` (a whole sheet). A range larger than the data
answers the requested range with trailing empty rows and columns left out; a
range larger than the grid is clipped to the grid.

A row stores its cells as objects: ``{"v": value}`` for a number, string or
boolean, ``{"f": "=SUM(B2:B9)"}`` for a formula, ``{"d": "2026-10-04"}`` for a
date (a date serial number inside), ``{}`` for an empty cell, each with an
optional ``"fmt"`` number format. Formulas are evaluated on every read, so
totals follow the cells they sum. Mock simplifications (also stated in api_test_results.md): the formula
language covers arithmetic, comparison, ``&`` and SUM, AVERAGE, MIN, MAX,
COUNT, COUNTA, ROUND, IF, ABS, SUMIF and COUNTIF; number formats are the
currency, number, percent and date patterns the seed uses; there is no styling,
merging, filtering or named range.
"""

import math
import re
import secrets
import sys
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

DATA_DIR = Path(__file__).parent

sys.path.insert(0, str(DATA_DIR.parent))
from _mutable_store import get_store, read_seed_with_ctx, strict_int  # noqa: E402
from _connector_auth import ConnectorAuth  # noqa: E402

_API = "google-sheets-api"
_store = get_store(_API)

UNTITLED = "Untitled spreadsheet"
DEFAULT_ROWS, DEFAULT_COLUMNS = 1000, 26
MAX_COLUMNS = 18278
CELL_LIMIT = 10_000_000
EPOCH = date(1899, 12, 30)
STATUS_NAMES = {400: "INVALID_ARGUMENT", 401: "UNAUTHENTICATED", 403: "PERMISSION_DENIED",
                404: "NOT_FOUND", 409: "ABORTED"}
NUMBER_FORMATS = {
    "currency": ("CURRENCY", '"$"#,##0.00'),
    "currency0": ("CURRENCY", '"$"#,##0'),
    "number0": ("NUMBER", "#,##0"),
    "number2": ("NUMBER", "#,##0.00"),
    "percent0": ("PERCENT", "0%"),
    "percent1": ("PERCENT", "0.0%"),
    "date": ("DATE", "yyyy-mm-dd"),
    "date_us": ("DATE", "m/d/yyyy"),
    "date_long": ("DATE", "mmm d, yyyy"),
    "text": ("TEXT", "@"),
}
ERROR_TYPES = {"#DIV/0!": "DIVIDE_BY_ZERO", "#NAME?": "NAME", "#REF!": "REF", "#VALUE!": "VALUE",
               "#N/A": "N_A", "#ERROR!": "ERROR", "#NUM!": "NUM"}


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _coerce_sheet_row(r):
    out = _strip_ctx(r)
    for key in ("sheet_id", "index", "row_count", "column_count", "frozen_row_count"):
        out[key] = strict_int(out, key)
    out["column_formats"] = dict(out.get("column_formats") or {})
    return out


def _coerce_value_row(r):
    out = _strip_ctx(r)
    out["sheet_id"] = strict_int(out, "sheet_id")
    out["row"] = strict_int(out, "row")
    out["values"] = [dict(c) if isinstance(c, dict) else {} for c in (out.get("values") or [])]
    return out


_store.register("spreadsheets", primary_key="id",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("spreadsheets.json", "spreadsheets")])
_store.register("sheets", primary_key="id",
                initial_loader=lambda: [_coerce_sheet_row(r) for r in _load("sheets.json", "sheets")],
                row_coercer=_coerce_sheet_row)
_store.register("rows", primary_key="id",
                initial_loader=lambda: [_coerce_value_row(r) for r in _load("rows.json", "rows")],
                row_coercer=_coerce_value_row)

auth = ConnectorAuth(_API, store=_store, data_dir=DATA_DIR)


class GoogleError:
    """A Google API error envelope (google.rpc.Status) and the HTTP status it is served with."""

    def __init__(self, status, message, status_name=None, field=None):
        self.status = status
        error = {"code": status, "message": message, "status": status_name or STATUS_NAMES.get(status, "UNKNOWN")}
        if field is not None:
            violation = {"field": field, "description": message} if field else {"description": message}
            error["details"] = [{"@type": "type.googleapis.com/google.rpc.BadRequest",
                                 "fieldViolations": [violation]}]
        self.body = {"error": error}


def _invalid(message, field=None):
    return GoogleError(400, message, field=field)


def _missing():
    return GoogleError(404, "Requested entity was not found.")


def _forbidden():
    return GoogleError(403, "The caller does not have permission")


# --- A1 notation ----------------------------------------------------------------------------

def col_letters(index):
    letters = ""
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def col_index(letters):
    index = 0
    for ch in letters.upper():
        index = index * 26 + ord(ch) - 64
    return index


def quote_sheet(title):
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", title) and not re.fullmatch(r"[A-Za-z]{1,3}\d+", title):
        return title
    return "'" + title.replace("'", "''") + "'"


def format_a1(title, r1, c1, r2, c2):
    start = f"{col_letters(c1)}{r1}"
    if (r1, c1) == (r2, c2):
        return f"{quote_sheet(title)}!{start}"
    return f"{quote_sheet(title)}!{start}:{col_letters(c2)}{r2}"


_REF = re.compile(r"^(?:([A-Za-z]{1,3})?(\d+)?)$")


def _endpoint(text):
    match = _REF.match(text)
    if not match or not text:
        return None
    col, row = match.group(1), match.group(2)
    if row is not None and int(row) < 1:
        return None
    return (col_index(col) if col else None, int(row) if row else None)


def parse_a1(text):
    """``(sheet name or None, cell part or None)`` for an A1 range, or None when it cannot be parsed.

    The cell part is ``(r1, c1, r2, c2)`` with None for an open end; a missing cell
    part means the whole sheet. A sheet-less name that is not a cell reference is
    returned as a sheet name so the caller can resolve it against the titles.
    """
    text = (text or "").strip()
    if not text:
        return None
    sheet, cells = None, text
    if text.startswith("'"):
        i, name = 1, ""
        while i < len(text):
            if text[i] == "'":
                if text[i + 1:i + 2] == "'":
                    name += "'"
                    i += 2
                    continue
                break
            name += text[i]
            i += 1
        else:
            return None
        rest = text[i + 1:]
        if rest and not rest.startswith("!"):
            return None
        sheet, cells = name, rest[1:] if rest else ""
        if rest == "!":
            return None
    elif "!" in text:
        sheet, cells = text.rsplit("!", 1)
        if not sheet or not cells:
            return None
    if sheet is not None and not cells:
        return sheet, None
    parts = cells.split(":")
    if len(parts) > 2:
        return None
    start = _endpoint(parts[0])
    if start is None:
        return (cells, None) if sheet is None and len(parts) == 1 else None
    if len(parts) == 1:
        if start[0] is None or start[1] is None:
            return (cells, None) if sheet is None else None
        return sheet, (start[1], start[0], start[1], start[0])
    end = _endpoint(parts[1])
    if end is None:
        return None
    (sc, sr), (ec, er) = start, end
    if sc is None and sr is not None and ec is None and er is not None:   # 1:5, whole rows
        r1, r2, c1, c2 = sr, er, 1, None
    elif sc is not None and sr is None and ec is not None and er is None:  # A:C, whole columns
        r1, r2, c1, c2 = 1, None, sc, ec
    elif sc is not None and ec is not None:                               # A1:C5, A5:C, A:C5
        r1, r2, c1, c2 = sr or 1, er, sc, ec
    else:
        return None
    if c1 > MAX_COLUMNS or (c2 or 0) > MAX_COLUMNS:
        return None
    if c2 is not None and c1 > c2:
        c1, c2 = c2, c1
    if r2 is not None and r1 > r2:
        r1, r2 = r2, r1
    return sheet, (r1, c1, r2, c2)


# --- workbook access -----------------------------------------------------------------------

def _owned(spreadsheet_id, account_id):
    book = _store.table("spreadsheets").get(spreadsheet_id)
    if book is None:
        return _missing()
    if book.get("owner_account_id") != account_id:
        return _forbidden()
    return book


def _sheets(spreadsheet_id):
    return sorted(_store.table("sheets").find(lambda s: s["spreadsheet_id"] == spreadsheet_id),
                  key=lambda s: s["index"])


def _sheet_by_title(sheets, title):
    for s in sheets:
        if s["title"] == title:
            return s
    for s in sheets:
        if s["title"].lower() == title.lower():
            return s
    return None


def resolve(spreadsheet_id, text):
    """``(sheet row, (r1, c1, r2, c2))`` for an A1 range, or a GoogleError when it does not resolve."""
    parsed = parse_a1(text)
    sheets = _sheets(spreadsheet_id)
    if parsed is None or not sheets:
        return _invalid(f"Unable to parse range: {text}")
    name, cells = parsed
    sheet = sheets[0] if name is None else _sheet_by_title(sheets, name)
    if sheet is None:
        return _invalid(f"Unable to parse range: {text}")
    return sheet, (cells or (1, 1, None, None))


def _clip(sheet, bounds, text):
    r1, c1, r2, c2 = bounds
    rows, cols = sheet["row_count"], sheet["column_count"]
    if r1 > rows or c1 > cols:
        return _invalid(f"Range ({quote_sheet(sheet['title'])}!{text.split('!')[-1]}) exceeds grid limits. "
                        f"Max rows: {rows}, max columns: {cols}")
    return r1, c1, min(r2 or rows, rows), min(c2 or cols, cols)


def _cell_value(cell):
    if "f" in cell:
        return {"formula": cell["f"]}
    if "d" in cell:
        return {"date": cell["d"]}
    return cell.get("v")


def _grid(spreadsheet_id):
    """{sheet_id: {(row, col): (value, format key or None)}} for every non-empty seeded or written cell."""
    out = {}
    for r in _store.table("rows").find(lambda x: x["spreadsheet_id"] == spreadsheet_id):
        cells = out.setdefault(r["sheet_id"], {})
        for j, cell in enumerate(r["values"]):
            value = _cell_value(cell)
            if value is None or value == "":
                continue
            cells[(r["row"], j + 1)] = (value, cell.get("fmt"))
    return out


# --- values: numbers, dates, formatting ---------------------------------------------------------

class CellError:
    def __init__(self, code, message):
        self.code, self.message = code, message

    def __eq__(self, other):
        return isinstance(other, CellError) and other.code == self.code


def _serial(day):
    return float((day - EPOCH).days)


def _day(serial):
    return EPOCH + timedelta(days=math.floor(serial))


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _num(v):
    return int(v) if float(v).is_integer() and abs(v) < 1e15 else v


def _round_half_up(value, places):
    q = Decimal(1).scaleb(-places)
    return Decimal(repr(float(value))).quantize(q, rounding=ROUND_HALF_UP)


def _grouped(value, places):
    d = _round_half_up(abs(value), places)
    whole, _, frac = f"{d:f}".partition(".")
    whole = f"{int(whole):,}"
    return whole + (f".{frac}" if places else "")


def _general(value):
    if float(value).is_integer() and abs(value) < 1e15:
        return str(int(value))
    text = format(value, ".10g")
    return text.replace("e+", "E+").replace("e-", "E-")


def format_number(value, fmt):
    sign = "-" if value < 0 else ""
    if fmt == "currency":
        return f"{sign}${_grouped(value, 2)}"
    if fmt == "currency0":
        return f"{sign}${_grouped(value, 0)}"
    if fmt == "number0":
        return f"{sign}{_grouped(value, 0)}"
    if fmt == "number2":
        return f"{sign}{_grouped(value, 2)}"
    if fmt == "percent0":
        return f"{sign}{_grouped(value * 100, 0)}%"
    if fmt == "percent1":
        return f"{sign}{_grouped(value * 100, 1)}%"
    if fmt in ("date", "date_us", "date_long"):
        day = _day(value)
        if fmt == "date":
            return day.isoformat()
        if fmt == "date_us":
            return f"{day.month}/{day.day}/{day.year}"
        return f"{day.strftime('%b')} {day.day}, {day.year}"
    return _general(value)


_NUMBER = re.compile(r"^([+-])?(\$)?(\d{1,3}(?:,\d{3})+|\d+)?(\.\d+)?(%)?$")
_ISO_DATE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
_US_DATE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})$")
_LONG_DATE = re.compile(r"^([A-Za-z]{3})[a-z]*\.? (\d{1,2}), (\d{4})$")
_MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
                                         "nov", "dec"), start=1)}


def _date_or_none(year, month, day):
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_user_entered(value):
    """``(stored value, format key or None)`` for one value written with USER_ENTERED."""
    if not isinstance(value, str):
        return value, None
    text = value.strip()
    if value.startswith("'"):
        return value[1:], "text"
    if value.startswith("="):
        return {"formula": value}, None
    if text.upper() in ("TRUE", "FALSE"):
        return text.upper() == "TRUE", None
    match = _NUMBER.match(text)
    if match and (match.group(3) or match.group(4)):
        sign, dollar, whole, frac, pct = match.groups()
        number = float((whole or "0").replace(",", "") + (frac or ""))
        if sign == "-":
            number = -number
        if pct:
            return _num(number / 100), "percent0" if not frac else "percent1"
        if dollar:
            return _num(number), "currency"
        return _num(number), ("number0" if whole and "," in whole else None)
    for pattern, fmt in ((_ISO_DATE, "date"), (_US_DATE, "date_us")):
        match = pattern.match(text)
        if match:
            a, b, c = (int(g) for g in match.groups())
            day = _date_or_none(a, b, c) if fmt == "date" else _date_or_none(c + (2000 if c < 100 else 0), a, b)
            if day:
                return _serial(day), fmt
    match = _LONG_DATE.match(text)
    if match and match.group(1).lower() in _MONTHS:
        day = _date_or_none(int(match.group(3)), _MONTHS[match.group(1).lower()], int(match.group(2)))
        if day:
            return _serial(day), "date_long"
    return value, None


# --- formulas ---------------------------------------------------------------------------------

_TOKEN = re.compile(r"""
    (?P<ws>\s+)
  | (?P<number>\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|\.\d+)
  | (?P<string>"(?:[^"]|"")*")
  | (?P<ref>(?:(?:'(?:[^']|'')+'|[A-Za-z_][A-Za-z0-9_]*)!)?
          (?:\$?[A-Za-z]{1,3}\$?\d+(?::\$?[A-Za-z]{1,3}\$?\d*)?|\$?[A-Za-z]{1,3}:\$?[A-Za-z]{1,3}\$?\d*))
  | (?P<name>[A-Za-z_][A-Za-z0-9_.]*)
  | (?P<op><>|<=|>=|[-+*/^&=<>(),%])
""", re.VERBOSE)


class _FormulaSyntax(Exception):
    pass


def _tokens(text):
    out, pos = [], 0
    while pos < len(text):
        match = _TOKEN.match(text, pos)
        if not match:
            raise _FormulaSyntax(text)
        pos = match.end()
        kind = match.lastgroup
        if kind != "ws":
            out.append((kind, match.group(kind)))
    return out


class _Parser:
    def __init__(self, tokens):
        self.tokens, self.pos = tokens, 0

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else (None, None)

    def take(self, value=None):
        tok = self.peek()
        if tok[0] is None or (value is not None and tok[1] != value):
            raise _FormulaSyntax(value)
        self.pos += 1
        return tok

    def parse(self):
        node = self.comparison()
        if self.pos != len(self.tokens):
            raise _FormulaSyntax("trailing")
        return node

    def comparison(self):
        node = self.concat()
        while self.peek()[1] in ("=", "<>", "<", ">", "<=", ">="):
            op = self.take()[1]
            node = ("cmp", op, node, self.concat())
        return node

    def concat(self):
        node = self.additive()
        while self.peek()[1] == "&":
            self.take()
            node = ("&", node, self.additive())
        return node

    def additive(self):
        node = self.term()
        while self.peek()[1] in ("+", "-"):
            op = self.take()[1]
            node = ("arith", op, node, self.term())
        return node

    def term(self):
        node = self.power()
        while self.peek()[1] in ("*", "/"):
            op = self.take()[1]
            node = ("arith", op, node, self.power())
        return node

    def power(self):
        node = self.unary()
        while self.peek()[1] == "^":
            self.take()
            node = ("arith", "^", node, self.unary())
        return node

    def unary(self):
        if self.peek()[1] in ("-", "+"):
            op = self.take()[1]
            operand = self.unary()
            return ("neg", operand) if op == "-" else operand
        return self.postfix()

    def postfix(self):
        node = self.primary()
        while self.peek()[1] == "%":
            self.take()
            node = ("arith", "/", node, ("num", 100.0))
        return node

    def primary(self):
        kind, value = self.peek()
        if kind == "number":
            self.take()
            return ("num", float(value))
        if kind == "string":
            self.take()
            return ("str", value[1:-1].replace('""', '"'))
        if kind == "ref":
            self.take()
            return ("ref", value)
        if kind == "name":
            self.take()
            if self.peek()[1] == "(":
                self.take("(")
                args = []
                if self.peek()[1] != ")":
                    args.append(self.comparison())
                    while self.peek()[1] == ",":
                        self.take()
                        args.append(self.comparison())
                self.take(")")
                return ("call", value.upper(), args)
            if value.upper() in ("TRUE", "FALSE"):
                return ("bool", value.upper() == "TRUE")
            return ("badname", value)
        if value == "(":
            self.take()
            node = self.comparison()
            self.take(")")
            return node
        raise _FormulaSyntax(value)


class _Workbook:
    """Evaluates the formulas of one spreadsheet against its current cells."""

    def __init__(self, spreadsheet_id):
        self.sheets = _sheets(spreadsheet_id)
        self.grid = _grid(spreadsheet_id)
        self.cache, self.stack = {}, set()

    def sheet_id(self, title):
        sheet = _sheet_by_title(self.sheets, title)
        return sheet["sheet_id"] if sheet else None

    def raw(self, sheet_id, row, col):
        return self.grid.get(sheet_id, {}).get((row, col), (None, None))

    def value(self, sheet_id, row, col):
        """The effective value of one cell: None (empty), number, string, bool or CellError."""
        key = (sheet_id, row, col)
        if key in self.cache:
            return self.cache[key]
        raw, _fmt = self.raw(sheet_id, row, col)
        if isinstance(raw, dict) and "formula" in raw:
            if key in self.stack:
                return CellError("#REF!", "Circular dependency detected. To resolve with iterative "
                                          "calculation, see File > Settings.")
            self.stack.add(key)
            try:
                result = self.formula(raw["formula"], sheet_id)
            finally:
                self.stack.discard(key)
        elif isinstance(raw, dict) and "date" in raw:
            day = date.fromisoformat(str(raw["date"]))
            result = _serial(day)
        else:
            result = raw
        self.cache[key] = result
        return result

    def formula(self, text, sheet_id):
        try:
            tree = _Parser(_tokens(text[1:])).parse()
        except _FormulaSyntax:
            return CellError("#ERROR!", "Formula parse error.")
        result = self.eval(tree, sheet_id)
        if isinstance(result, list):
            return result[0] if len(result) == 1 else CellError("#VALUE!", "An array value could not be found.")
        return result

    def ref_cells(self, ref, sheet_id):
        sheet_part, _, cells = ref.rpartition("!")
        target = sheet_id
        if sheet_part:
            name = sheet_part[1:-1].replace("''", "'") if sheet_part.startswith("'") else sheet_part
            target = self.sheet_id(name)
            if target is None:
                return CellError("#REF!", f"Unresolved sheet name '{name}'.")
        cells = cells.replace("$", "")
        parsed = parse_a1(cells)
        if parsed is None or parsed[1] is None:
            return CellError("#REF!", f"Unresolved reference {ref}.")
        r1, c1, r2, c2 = parsed[1]
        sheet = next(s for s in self.sheets if s["sheet_id"] == target)
        r2, c2 = r2 or sheet["row_count"], c2 or sheet["column_count"]
        if r2 - r1 > 5000 or c2 - c1 > 200:
            used = [k for k in self.grid.get(target, {})]
            r2 = min(r2, max((r for r, _ in used), default=r1))
            c2 = min(c2, max((c for _, c in used), default=c1))
        return [self.value(target, r, c) for r in range(r1, r2 + 1) for c in range(c1, c2 + 1)]

    def eval(self, node, sheet_id):
        kind = node[0]
        if kind == "num":
            return node[1]
        if kind in ("str", "bool"):
            return node[1]
        if kind == "badname":
            return CellError("#NAME?", f"Unknown range name: '{node[1].upper()}'.")
        if kind == "ref":
            return self.ref_cells(node[1], sheet_id)
        if kind == "neg":
            value = _scalar_number(self.eval(node[1], sheet_id))
            return value if isinstance(value, CellError) else -value
        if kind == "arith":
            a = _scalar_number(self.eval(node[2], sheet_id))
            b = _scalar_number(self.eval(node[3], sheet_id))
            for v in (a, b):
                if isinstance(v, CellError):
                    return v
            op = node[1]
            if op == "+":
                return a + b
            if op == "-":
                return a - b
            if op == "*":
                return a * b
            if op == "/":
                return CellError("#DIV/0!", "Function DIVIDE parameter 2 cannot be zero.") if b == 0 else a / b
            try:
                return float(a) ** float(b)
            except (OverflowError, ValueError, ZeroDivisionError):
                return CellError("#NUM!", "Function POW result was not a number.")
        if kind == "&":
            parts = [_scalar(self.eval(n, sheet_id)) for n in node[1:]]
            for v in parts:
                if isinstance(v, CellError):
                    return v
            return "".join(_text(v) for v in parts)
        if kind == "cmp":
            a, b = _scalar(self.eval(node[2], sheet_id)), _scalar(self.eval(node[3], sheet_id))
            for v in (a, b):
                if isinstance(v, CellError):
                    return v
            return _compare(node[1], a, b)
        if kind == "call":
            return self.call(node[1], [self.eval(arg, sheet_id) for arg in node[2]])
        return CellError("#ERROR!", "Formula parse error.")

    def call(self, name, args):
        flat = []
        for arg in args:
            flat.extend(arg if isinstance(arg, list) else [arg])
        for v in flat:
            if isinstance(v, CellError) and name not in ("IF", "COUNTA", "COUNT"):
                return v
        numbers = [v for v in flat if _is_number(v)]
        direct = [_scalar_number(a) for a in args if not isinstance(a, list)]
        if name in ("SUM", "AVERAGE", "MIN", "MAX"):
            for v in direct:
                if isinstance(v, CellError):
                    return v
            values = numbers if not direct else [v for a in args for v in (
                [x for x in a if _is_number(x)] if isinstance(a, list) else [_scalar_number(a)])]
            if name == "SUM":
                return float(sum(values))
            if name == "AVERAGE":
                return CellError("#DIV/0!", "Evaluation of function AVERAGE caused a divide by zero error.") \
                    if not values else sum(values) / len(values)
            return float((min if name == "MIN" else max)(values)) if values else 0.0
        if name == "COUNT":
            return float(len(numbers))
        if name == "COUNTA":
            return float(sum(1 for v in flat if v is not None and v != ""))
        if name == "ABS":
            if len(args) != 1:
                return _arg_count(name, 1, len(args))
            v = _scalar_number(args[0])
            return v if isinstance(v, CellError) else abs(v)
        if name == "ROUND":
            if not 1 <= len(args) <= 2:
                return _arg_count(name, 2, len(args))
            v = _scalar_number(args[0])
            places = _scalar_number(args[1]) if len(args) == 2 else 0
            for x in (v, places):
                if isinstance(x, CellError):
                    return x
            return float(_round_half_up(v, int(places)))
        if name == "IF":
            if not 2 <= len(args) <= 3:
                return _arg_count(name, 3, len(args))
            cond = _scalar(args[0])
            if isinstance(cond, CellError):
                return cond
            chosen = args[1] if _truthy(cond) else (args[2] if len(args) == 3 else False)
            return _scalar(chosen)
        if name in ("SUMIF", "COUNTIF"):
            if not isinstance(args[0], list) or len(args) < 2 or (name == "COUNTIF" and len(args) != 2):
                return _arg_count(name, 2, len(args))
            criterion = _scalar(args[1])
            matches = [_matches(v, criterion) for v in args[0]]
            if name == "COUNTIF":
                return float(sum(matches))
            sums = args[2] if len(args) == 3 and isinstance(args[2], list) else args[0]
            return float(sum(v for v, ok in zip(sums, matches) if ok and _is_number(v)))
        return CellError("#NAME?", f"Unknown function: '{name}'.")


def _arg_count(name, expected, got):
    return CellError("#N/A", f"Wrong number of arguments to {name}. Expected {expected} arguments, "
                             f"but got {got} arguments.")


def _scalar(v):
    if isinstance(v, list):
        return v[0] if len(v) == 1 else CellError("#VALUE!", "An array value could not be found.")
    return v


def _scalar_number(v):
    v = _scalar(v)
    if isinstance(v, CellError) or _is_number(v):
        return v
    if v is None or v == "":
        return 0.0
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return CellError("#VALUE!", f"Function expects number values. But '{v}' is a text and cannot be "
                                    "coerced to a number.")


def _text(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if _is_number(v):
        return _general(v)
    return str(v)


def _truthy(v):
    if isinstance(v, str):
        return v.upper() == "TRUE" or (v != "" and v.upper() != "FALSE")
    return bool(v)


def _compare(op, a, b):
    if _is_number(a) and _is_number(b):
        x, y = a, b
    elif isinstance(a, str) and isinstance(b, str):
        x, y = a.lower(), b.lower()
    else:
        x, y = (_text(a).lower(), _text(b).lower()) if not (a is None or b is None) else (
            a if a is not None else (0 if _is_number(b) else ""), b if b is not None else (0 if _is_number(a) else ""))
    return {"=": x == y, "<>": x != y, "<": x < y, ">": x > y, "<=": x <= y, ">=": x >= y}[op]


def _matches(value, criterion):
    if _is_number(criterion):
        return _is_number(value) and value == criterion
    text = _text(criterion)
    match = re.match(r"^(<>|<=|>=|=|<|>)(.*)$", text)
    op, operand = (match.group(1), match.group(2)) if match else ("=", text)
    try:
        number = float(operand)
        if _is_number(value):
            return _compare(op, value, number)
        return op == "<>"
    except ValueError:
        return _compare(op, _text(value), operand)


# --- rendering ------------------------------------------------------------------------------------

def _format_key(book, sheet, row, col):
    raw, fmt = book.raw(sheet["sheet_id"], row, col)
    if fmt:
        return fmt
    if isinstance(raw, dict) and "date" in raw:
        return "date"
    return sheet["column_formats"].get(col_letters(col))


def _render(book, sheet, row, col, render="FORMATTED_VALUE", datetime_render="SERIAL_NUMBER"):
    raw, _fmt = book.raw(sheet["sheet_id"], row, col)
    value = book.value(sheet["sheet_id"], row, col)
    fmt = _format_key(book, sheet, row, col)
    if render == "FORMULA" and isinstance(raw, dict) and "formula" in raw:
        return raw["formula"]
    if value is None:
        return ""
    if isinstance(value, CellError):
        return value.code
    if render == "FORMATTED_VALUE":
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        if _is_number(value):
            return format_number(value, fmt)
        return value
    if _is_number(value):
        if fmt and NUMBER_FORMATS.get(fmt, ("",))[0] == "DATE" and datetime_render == "FORMATTED_STRING":
            return format_number(value, fmt)
        return _num(value)
    return value


def _trim(rows):
    rows = [list(r) for r in rows]
    for r in rows:
        while r and r[-1] == "":
            r.pop()
    while rows and not rows[-1]:
        rows.pop()
    return rows


def _value_range(book, sheet, bounds, major="ROWS", render="FORMATTED_VALUE", datetime_render="SERIAL_NUMBER"):
    r1, c1, r2, c2 = bounds
    used = book.grid.get(sheet["sheet_id"], {})
    last_row = max((r for r, c in used if c1 <= c <= c2 and r1 <= r <= r2), default=r1 - 1)
    last_col = max((c for r, c in used if r1 <= r <= r2 and c1 <= c <= c2), default=c1 - 1)
    grid = [[_render(book, sheet, r, c, render, datetime_render) for c in range(c1, last_col + 1)]
            for r in range(r1, last_row + 1)]
    if major == "COLUMNS":
        grid = [list(col) for col in zip(*grid)] if grid else []
    out = {"range": format_a1(sheet["title"], *bounds), "majorDimension": major}
    values = _trim(grid)
    if values:
        out["values"] = values
    return out


def _sheet_properties(sheet):
    grid = {"rowCount": sheet["row_count"], "columnCount": sheet["column_count"]}
    if sheet.get("frozen_row_count"):
        grid["frozenRowCount"] = sheet["frozen_row_count"]
    props = {"sheetId": sheet["sheet_id"], "title": sheet["title"], "index": sheet["index"],
             "sheetType": "GRID", "gridProperties": grid}
    if sheet.get("tab_color"):
        hexcolor = sheet["tab_color"].lstrip("#")
        rgb = {k: round(int(hexcolor[i:i + 2], 16) / 255, 4) for k, i in (("red", 0), ("green", 2), ("blue", 4))}
        props["tabColorStyle"] = {"rgbColor": rgb}
    return props


def _cell_data(book, sheet, row, col):
    raw, _fmt = book.raw(sheet["sheet_id"], row, col)
    if raw is None:
        return {}
    value = book.value(sheet["sheet_id"], row, col)
    fmt = _format_key(book, sheet, row, col)
    if isinstance(raw, dict) and "formula" in raw:
        entered = {"formulaValue": raw["formula"]}
    elif isinstance(raw, dict) and "date" in raw:
        entered = {"numberValue": _num(value)}
    elif isinstance(raw, bool):
        entered = {"boolValue": raw}
    elif _is_number(raw):
        entered = {"numberValue": _num(raw)}
    else:
        entered = {"stringValue": str(raw)}
    if isinstance(value, CellError):
        effective = {"errorValue": {"type": ERROR_TYPES.get(value.code, "ERROR"), "message": value.message}}
    elif isinstance(value, bool):
        effective = {"boolValue": value}
    elif _is_number(value):
        effective = {"numberValue": _num(value)}
    else:
        effective = {"stringValue": "" if value is None else str(value)}
    cell = {"userEnteredValue": entered, "effectiveValue": effective,
            "formattedValue": _render(book, sheet, row, col)}
    if fmt in NUMBER_FORMATS:
        kind, pattern = NUMBER_FORMATS[fmt]
        cell["userEnteredFormat"] = {"numberFormat": {"type": kind, "pattern": pattern}}
    return cell


def _grid_data(book, sheet, bounds=None):
    used = book.grid.get(sheet["sheet_id"], {})
    if bounds is None:
        r1, c1 = 1, 1
        r2 = max((r for r, _ in used), default=0)
        c2 = max((c for _, c in used), default=0)
    else:
        r1, c1, r2, c2 = bounds
    rows = []
    for r in range(r1, r2 + 1):
        cells = [_cell_data(book, sheet, r, c) for c in range(c1, c2 + 1)]
        while cells and not cells[-1]:
            cells.pop()
        rows.append({"values": cells} if cells else {})
    while rows and not rows[-1]:
        rows.pop()
    data = {"rowData": rows}
    if r1 > 1:
        data["startRow"] = r1 - 1
    if c1 > 1:
        data["startColumn"] = c1 - 1
    return data


def _spreadsheet_view(book_row, book, sheet_rows, grid=None):
    sheets = []
    for sheet in sheet_rows:
        entry = {"properties": _sheet_properties(sheet)}
        if grid is not None:
            entry["data"] = [_grid_data(book, sheet, b) for b in grid.get(sheet["sheet_id"], [None])]
        sheets.append(entry)
    return {
        "spreadsheetId": book_row["id"],
        "properties": {"title": book_row["title"], "locale": book_row.get("locale") or "en_US",
                       "autoRecalc": "ON_CHANGE", "timeZone": book_row.get("time_zone") or "America/Chicago",
                       "defaultFormat": {"backgroundColor": {"red": 1, "green": 1, "blue": 1},
                                         "verticalAlignment": "BOTTOM", "wrapStrategy": "OVERFLOW_CELL",
                                         "textFormat": {"fontFamily": "arial", "fontSize": 10}}},
        "sheets": sheets,
        "spreadsheetUrl": f"https://docs.google.com/spreadsheets/d/{book_row['id']}/edit",
    }


# --- fields (partial response) ------------------------------------------------------------------

class _MaskError(ValueError):
    pass


def _parse_mask(text):
    text = re.sub(r"\s+", "", text or "")
    pos = 0

    def parse_list():
        nonlocal pos
        tree = {}
        while True:
            names = parse_path()
            sub = True
            if pos < len(text) and text[pos] == "(":
                pos += 1
                sub = parse_list()
                if pos >= len(text) or text[pos] != ")":
                    raise _MaskError(text)
                pos += 1
            node = tree
            for name in names[:-1]:
                child = node.get(name)
                if child is True:
                    break
                node = node.setdefault(name, {})
            else:
                leaf = names[-1]
                if sub is True or node.get(leaf) is True:
                    node[leaf] = True
                else:
                    existing = node.get(leaf) or {}
                    existing.update(sub)
                    node[leaf] = existing
            if pos < len(text) and text[pos] == ",":
                pos += 1
                continue
            return tree

    def parse_path():
        nonlocal pos
        names = []
        while True:
            match = re.match(r"[A-Za-z0-9_*]+", text[pos:])
            if not match:
                raise _MaskError(text)
            names.append(match.group(0))
            pos += len(match.group(0))
            if pos < len(text) and text[pos] in "./":
                pos += 1
                continue
            return names

    if not text:
        raise _MaskError(text)
    tree = parse_list()
    if pos != len(text):
        raise _MaskError(text)
    return tree


def _mask_paths(tree, prefix=""):
    for name, sub in tree.items():
        path = f"{prefix}.{name}" if prefix else name
        yield name, path
        if sub is not True:
            yield from _mask_paths(sub, path)


KNOWN_FIELDS = {
    "spreadsheetId", "properties", "title", "locale", "autoRecalc", "timeZone", "defaultFormat", "backgroundColor",
    "red", "green", "blue", "verticalAlignment", "wrapStrategy", "textFormat", "fontFamily", "fontSize", "sheets",
    "sheetId", "index", "sheetType", "gridProperties", "rowCount", "columnCount", "frozenRowCount",
    "tabColorStyle", "rgbColor", "data", "rowData", "values", "startRow", "startColumn", "userEnteredValue",
    "effectiveValue", "formattedValue", "userEnteredFormat", "numberFormat", "type", "pattern", "numberValue",
    "stringValue", "boolValue", "formulaValue", "errorValue", "message", "spreadsheetUrl", "range",
    "majorDimension", "updatedRange", "updatedRows", "updatedColumns", "updatedCells", "updatedData",
    "tableRange", "updates",
}


def _field_error(description):
    error = GoogleError(400, "Request contains an invalid argument.")
    error.body["error"]["details"] = [{"@type": "type.googleapis.com/google.rpc.BadRequest",
                                       "fieldViolations": [{"field": "fields", "description": description}]}]
    return error


def parse_fields(mask):
    """The parsed ``fields`` selection, or a GoogleError for a malformed or unknown path."""
    if mask is None:
        return None
    try:
        tree = _parse_mask(mask)
    except _MaskError:
        return _field_error(f"Error expanding 'fields' parameter. Invalid field selection '{mask}'.")
    for name, path in _mask_paths(tree):
        if name != "*" and name not in KNOWN_FIELDS:
            return _field_error(f"Error expanding 'fields' parameter. Cannot find matching fields for path "
                                f"'{path}'.")
    return tree


def apply_fields(obj, tree):
    if tree is None or tree is True:
        return obj
    if isinstance(obj, list):
        return [apply_fields(item, tree) for item in obj]
    if not isinstance(obj, dict):
        return obj
    out = {}
    wildcard = tree.get("*")
    for key, value in obj.items():
        sub = tree.get(key, wildcard)
        if sub is not None:
            out[key] = apply_fields(value, sub)
    return out


# --- operations --------------------------------------------------------------------------------

def get_spreadsheet(spreadsheet_id, account_id, ranges=None, include_grid_data=False):
    book_row = _owned(spreadsheet_id, account_id)
    if isinstance(book_row, GoogleError):
        return book_row
    sheet_rows = _sheets(spreadsheet_id)
    book = _Workbook(spreadsheet_id)
    if not ranges:
        grid = {s["sheet_id"]: [None] for s in sheet_rows} if include_grid_data else None
        return _spreadsheet_view(book_row, book, sheet_rows, grid)
    wanted = {}
    for text in ranges:
        resolved = resolve(spreadsheet_id, text)
        if isinstance(resolved, GoogleError):
            return resolved
        sheet, bounds = resolved
        clipped = _clip(sheet, bounds, text)
        if isinstance(clipped, GoogleError):
            return clipped
        wanted.setdefault(sheet["sheet_id"], []).append(clipped)
    selected = [s for s in sheet_rows if s["sheet_id"] in wanted]
    return _spreadsheet_view(book_row, book, selected, wanted if include_grid_data else None)


def get_values(spreadsheet_id, account_id, range_text, major="ROWS", render="FORMATTED_VALUE",
               datetime_render="SERIAL_NUMBER"):
    book_row = _owned(spreadsheet_id, account_id)
    if isinstance(book_row, GoogleError):
        return book_row
    resolved = resolve(spreadsheet_id, range_text)
    if isinstance(resolved, GoogleError):
        return resolved
    sheet, bounds = resolved
    clipped = _clip(sheet, bounds, range_text)
    if isinstance(clipped, GoogleError):
        return clipped
    return _value_range(_Workbook(spreadsheet_id), sheet, clipped, major, render, datetime_render)


def _check_body_range(spreadsheet_id, body_range, sheet, bounds, range_text):
    if body_range is None:
        return None
    other = resolve(spreadsheet_id, body_range)
    if isinstance(other, GoogleError) or other[0]["sheet_id"] != sheet["sheet_id"] or other[1] != bounds:
        return _invalid(f'Requested range "{range_text}" does not match the range in the request body '
                        f'"{body_range}".', field="data.range")
    return None


def _prepare(values, major):
    rows = [list(r) for r in (values or [])]
    if major == "COLUMNS":
        width = max((len(r) for r in rows), default=0)
        rows = [[r[i] if i < len(r) else None for r in rows] for i in range(width)]
    return rows


def _write(spreadsheet_id, sheet, start_row, start_col, rows, input_option):
    """Write ``rows`` at (start_row, start_col); null values are skipped and "" clears a cell."""
    table = _store.table("rows")
    written_rows, written_cols, cells = set(), set(), 0
    need_rows = start_row + len(rows) - 1
    need_cols = start_col + max((len(r) for r in rows), default=1) - 1
    patch = {}
    if need_rows > sheet["row_count"]:
        patch["row_count"] = need_rows
    if need_cols > sheet["column_count"]:
        patch["column_count"] = need_cols
    if (patch.get("row_count", sheet["row_count"]) * patch.get("column_count", sheet["column_count"])
            > CELL_LIMIT):
        return _invalid(f"This action would increase the number of cells in the workbook above the limit of "
                        f"{CELL_LIMIT} cells.")
    if patch:
        _store.table("sheets").patch(sheet["id"], patch)
    for i, values in enumerate(rows):
        row_no = start_row + i
        if all(v is None for v in values):
            continue
        key = f"{spreadsheet_id}:{sheet['sheet_id']}:{row_no}"
        current = table.get(key) or {"id": key, "spreadsheet_id": spreadsheet_id, "sheet_id": sheet["sheet_id"],
                                     "row": row_no, "values": []}
        stored = [dict(c) for c in current["values"]]
        for j, value in enumerate(values):
            if value is None:
                continue
            col = start_col + j - 1
            while len(stored) <= col:
                stored.append({})
            if input_option == "USER_ENTERED":
                entered, fmt = parse_user_entered(value)
            else:
                entered, fmt = value, None
            if entered == "":
                stored[col] = {}
            else:
                stored[col] = {"f": entered["formula"]} if isinstance(entered, dict) else {"v": entered}
                if fmt:
                    stored[col]["fmt"] = fmt
            written_rows.add(row_no)
            written_cols.add(start_col + j)
            cells += 1
        while stored and not stored[-1]:
            stored.pop()
        if stored:
            table.upsert({**current, "values": stored})
        else:
            table.delete(key)
    return written_rows, written_cols, cells


def _update_response(spreadsheet_id, sheet, start_row, start_col, rows, written, include_values, render,
                     datetime_render):
    written_rows, written_cols, cells = written
    out = {"spreadsheetId": spreadsheet_id}
    if rows:
        end_row = start_row + len(rows) - 1
        end_col = start_col + max(len(r) for r in rows) - 1
        out["updatedRange"] = format_a1(sheet["title"], start_row, start_col, end_row, end_col)
        if cells:
            out.update({"updatedRows": len(written_rows), "updatedColumns": len(written_cols),
                        "updatedCells": cells})
        if include_values:
            fresh = _store.table("sheets").get(sheet["id"])
            out["updatedData"] = _value_range(_Workbook(spreadsheet_id), fresh,
                                              (start_row, start_col, end_row, end_col), "ROWS", render,
                                              datetime_render)
    return out


def update_values(spreadsheet_id, account_id, range_text, values, input_option, major=None, body_range=None,
                  include_values=False, render="FORMATTED_VALUE", datetime_render="SERIAL_NUMBER"):
    book_row = _owned(spreadsheet_id, account_id)
    if isinstance(book_row, GoogleError):
        return book_row
    if input_option is None:
        return _invalid("'valueInputOption' is required but not specified")
    resolved = resolve(spreadsheet_id, range_text)
    if isinstance(resolved, GoogleError):
        return resolved
    sheet, bounds = resolved
    mismatch = _check_body_range(spreadsheet_id, body_range, sheet, bounds, range_text)
    if mismatch:
        return mismatch
    rows = _prepare(values, major or "ROWS")
    r1, c1, r2, c2 = bounds
    single = (r1, c1) == (r2, c2)
    if not single:
        shown = "'" + sheet["title"].replace("'", "''") + "'!" + range_text.split("!")[-1]
        if r2 is not None and len(rows) > r2 - r1 + 1:
            return _invalid(f"Requested writing within range [{shown}], but tried writing to row "
                            f"[{r1 + len(rows) - 1}]")
        width = max((len(r) for r in rows), default=0)
        if c2 is not None and width > c2 - c1 + 1:
            return _invalid(f"Requested writing within range [{shown}], but tried writing to column "
                            f"[{col_letters(c1 + width - 1)}]")
    written = _write(spreadsheet_id, sheet, r1, c1, rows, input_option)
    if isinstance(written, GoogleError):
        return written
    return _update_response(spreadsheet_id, sheet, r1, c1, rows, written, include_values, render, datetime_render)


def _find_table(book, sheet, bounds):
    r1, c1, r2, c2 = bounds
    used = book.grid.get(sheet["sheet_id"], {})
    last_col = c2 or max((c for _, c in used), default=c1)
    occupied = lambda r: any((r, c) in used for c in range(c1, max(last_col, c1) + 1))  # noqa: E731
    last_row = max((r for r, _ in used), default=0)
    # The table starts inside the requested rows but runs on past them while rows stay
    # occupied, so a header range such as A1:G1 appends below the existing data.
    start = next((r for r in range(r1, min(r2 or last_row, last_row) + 1) if occupied(r)), None)
    if start is None:
        return None
    end = start
    while end + 1 <= last_row and occupied(end + 1):
        end += 1
    cols = [c for r in range(start, end + 1) for c in range(c1, max(last_col, c1) + 1) if (r, c) in used]
    return start, min(cols), end, max(cols)


def append_values(spreadsheet_id, account_id, range_text, values, input_option, insert_option=None, major=None,
                  body_range=None, include_values=False, render="FORMATTED_VALUE", datetime_render="SERIAL_NUMBER"):
    book_row = _owned(spreadsheet_id, account_id)
    if isinstance(book_row, GoogleError):
        return book_row
    if input_option is None:
        return _invalid("'valueInputOption' is required but not specified")
    resolved = resolve(spreadsheet_id, range_text)
    if isinstance(resolved, GoogleError):
        return resolved
    sheet, bounds = resolved
    mismatch = _check_body_range(spreadsheet_id, body_range, sheet, bounds, range_text)
    if mismatch:
        return mismatch
    rows = _prepare(values, major or "ROWS")
    table = _find_table(_Workbook(spreadsheet_id), sheet, bounds)
    out = {"spreadsheetId": spreadsheet_id}
    if table is None:
        start_row, start_col = bounds[0], bounds[1]
    else:
        t_r1, t_c1, t_r2, t_c2 = table
        out["tableRange"] = format_a1(sheet["title"], t_r1, t_c1, t_r2, t_c2)
        start_row, start_col = t_r2 + 1, t_c1
    if (insert_option or "OVERWRITE") == "INSERT_ROWS" and rows:
        shift = len(rows)
        store_rows = _store.table("rows")
        moving = sorted(store_rows.find(lambda x: x["spreadsheet_id"] == spreadsheet_id
                                        and x["sheet_id"] == sheet["sheet_id"] and x["row"] >= start_row),
                        key=lambda x: x["row"], reverse=True)
        for row in moving:
            store_rows.delete(row["id"])
            new_row = row["row"] + shift
            store_rows.upsert({**row, "id": f"{spreadsheet_id}:{sheet['sheet_id']}:{new_row}", "row": new_row})
        sheet = _store.table("sheets").patch(sheet["id"], {"row_count": sheet["row_count"] + shift})
    written = _write(spreadsheet_id, sheet, start_row, start_col, rows, input_option)
    if isinstance(written, GoogleError):
        return written
    out["updates"] = _update_response(spreadsheet_id, sheet, start_row, start_col, rows, written,
                                      include_values, render, datetime_render)
    return out


def _new_spreadsheet_id():
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
    return "1" + "".join(secrets.choice(alphabet) for _ in range(33))


def create_spreadsheet(account_id, properties=None, sheets=None):
    properties = properties or {}
    specs = sheets or [{}]
    titles, ids, prepared = set(), set(), []
    for i, spec in enumerate(specs):
        props = spec.get("properties") or {}
        grid = props.get("gridProperties") or {}
        title = props.get("title") or f"Sheet{i + 1}"
        if title.lower() in titles:
            return _invalid(f'A sheet with the name "{title}" already exists. Please enter another name.')
        titles.add(title.lower())
        sheet_id = props.get("sheetId")
        if sheet_id is None:
            sheet_id = 0 if i == 0 else int.from_bytes(secrets.token_bytes(4), "big") % 2_000_000_000
        if sheet_id < 0 or sheet_id in ids:
            return _invalid(f"Invalid sheets[{i}].properties.sheetId: {sheet_id} is negative or already used.")
        ids.add(sheet_id)
        rows, cols = grid.get("rowCount") or DEFAULT_ROWS, grid.get("columnCount") or DEFAULT_COLUMNS
        if rows < 1 or cols < 1 or cols > MAX_COLUMNS:
            return _invalid(f"Invalid sheets[{i}].properties.gridProperties: rowCount and columnCount must be "
                            f"positive and columnCount at most {MAX_COLUMNS}.")
        prepared.append({"sheet_id": sheet_id, "title": title, "index": props.get("index"), "row_count": rows,
                         "column_count": cols, "frozen_row_count": grid.get("frozenRowCount") or 0})
    if sum(s["row_count"] * s["column_count"] for s in prepared) > CELL_LIMIT:
        return _invalid(f"This action would increase the number of cells in the workbook above the limit of "
                        f"{CELL_LIMIT} cells.")
    order = sorted(range(len(prepared)), key=lambda k: (prepared[k]["index"] if prepared[k]["index"] is not None
                                                        else k, k))
    book_id = _new_spreadsheet_id()
    book_row = {"id": book_id, "owner_account_id": account_id, "title": properties.get("title") or UNTITLED,
                "locale": properties.get("locale") or "en_US",
                "time_zone": properties.get("timeZone") or "America/Chicago"}
    _store.table("spreadsheets").upsert(book_row)
    for position, k in enumerate(order):
        sheet = prepared[k]
        _store.table("sheets").upsert({**sheet, "id": f"{book_id}:{sheet['sheet_id']}", "spreadsheet_id": book_id,
                                       "index": position, "tab_color": "", "column_formats": {}})
    return _spreadsheet_view(book_row, _Workbook(book_id), _sheets(book_id))


_store.eager_load()
