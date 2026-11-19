"""Live link between google-drive-api and the Google editor mocks.

Real Drive and the Docs, Sheets, Slides and Forms APIs are one system: a Doc
edited through the Docs API exports with the edit from Drive, a Doc renamed in
Drive has the new title in the Docs API, and a Doc created in either shows in
both. Here each mock is its own process (its own container in a delivered
bundle) with its own in-memory store, so Drive cannot read the editors' state
from disk: the seed on disk is only the state at the start of the run.

So each editor mock serves its live state to Drive on a private peer route,
and Drive asks for it on every call:

* Editor side: :func:`install` adds ``/_wcb/peer/...`` to the editor's app.
  The routes answer only a caller presenting ``WCB_PEER_TOKEN`` in
  ``X-WCB-Peer-Token``; anyone else, the agent included, gets the service's
  ordinary not-found. The tracking middleware keeps them out of the audit log,
  because they are the mocks talking to each other, not the agent.
* Drive side: :func:`peer_for` returns the peer of an editor API, or None when
  that API is not deployed in this run (then nothing can change it, and its
  seed is the truth).

A peer that is deployed but does not answer raises :class:`PeerUnavailable`.
Drive turns that into a 503 and records it, rather than serving the seed: a
stale answer the agent cannot tell from a real one is the failure this module
exists to remove.

Where the peers are:

* ``WCB_PEER_URLS`` (``api=url,api=url``), set by the bundle packagers for
  the editors a bundle ships.
* Otherwise, inside the harness's umbrella mock stack, the APIs the stack runs
  (``/tmp/mock_enabled_ports``, written by its entrypoint) on loopback, at the
  ports of ``/opt/mock_ports.json``.
* :func:`register_inprocess`, for a caller that has the editor data modules
  imported in this process (the pre-run task gate, tests). It wins over both.
"""

import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PEER_PREFIX = "/_wcb/peer"
PEER_TOKEN_ENV = "WCB_PEER_TOKEN"
PEER_URLS_ENV = "WCB_PEER_URLS"
PEER_HEADER = "X-WCB-Peer-Token"
STACK_PORTS_MANIFEST = Path("/opt/mock_ports.json")
STACK_ENABLED_PORTS = Path("/tmp/mock_enabled_ports")

DOC_MIME = "application/vnd.google-apps.document"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"
SLIDES_MIME = "application/vnd.google-apps.presentation"
FORM_MIME = "application/vnd.google-apps.form"

# Each editor's file table, the column Drive shows as the file's name, and the
# tables holding the file's content (with the column naming the file).
EDITORS = {
    "google-docs-api": {"table": "documents", "title": "title", "mime": DOC_MIME,
                        "children": (("paragraphs", "document_id"),)},
    "google-sheets-api": {"table": "spreadsheets", "title": "title", "mime": SHEET_MIME,
                          "children": (("sheets", "spreadsheet_id"), ("rows", "spreadsheet_id"))},
    "google-slides-api": {"table": "presentations", "title": "title", "mime": SLIDES_MIME,
                          "children": (("slides", "presentation_id"), ("elements", "presentation_id"))},
    "google-forms-api": {"table": "forms", "title": "document_title", "mime": FORM_MIME,
                         "children": (("items", "form_id"), ("responses", "form_id"))},
}

_GET_ATTEMPTS = 3
_TIMEOUT = 5.0


class PeerUnavailable(RuntimeError):
    """A deployed editor mock did not answer Drive."""


class PeerRefused(Exception):
    """The editor answered and refused the request (``kind``: not_found or invalid)."""

    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


# --- what both sides agree on -----------------------------------------------------------

def doc_plain_text(rows):
    """A Doc's text/plain export from its body rows: one line per paragraph, a table's cells
    in reading order, each cell paragraph on its own line."""
    lines = []
    for row in sorted(rows, key=lambda r: int(r["position"])):
        if row.get("table"):
            for cells in row["table"]:
                for cell in cells:
                    lines.extend(p.get("text") or "" for p in cell)
        else:
            lines.append(row.get("text") or "")
    return "".join(line + "\n" for line in lines)


def _fingerprint(row, children):
    blob = json.dumps([row, children], sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


# --- editor side ---------------------------------------------------------------------------

class EditorPeer:
    """An editor mock's files, read and changed through that mock's own store and functions."""

    def __init__(self, api, module):
        self.api = api
        self.spec = EDITORS[api]
        self.module = module
        self.store = module._store
        # The state the run started from, so the first look already tells an edit made
        # before Drive was ever asked (a mid-run change applied between turns) from none.
        self.baseline = {e["id"]: e["fingerprint"] for e in self._entries()}

    def _title(self, row):
        title = row.get(self.spec["title"]) or row.get("title") or ""
        return title or "Untitled"

    def _children(self, file_id):
        out = []
        for table, column in self.spec["children"]:
            rows = self.store.table(table).find(lambda r, c=column: r.get(c) == file_id)
            out.append(sorted(rows, key=lambda r: str(r.get("id"))))
        return out

    def _entry(self, row):
        return {"id": row["id"], "owner_account_id": row.get("owner_account_id") or "",
                "title": self._title(row), "fingerprint": _fingerprint(row, self._children(row["id"]))}

    def _entries(self):
        return [self._entry(r) for r in self.store.table(self.spec["table"]).rows()]

    def _row(self, file_id):
        row = self.store.table(self.spec["table"]).get(file_id)
        if row is None:
            raise PeerRefused("not_found", f"no {self.spec['table']} row {file_id}")
        return row

    def files(self):
        return [{**e, "baseline": self.baseline.get(e["id"], "")} for e in self._entries()]

    def export(self, file_id, mime_type):
        self._row(file_id)
        if self.api != "google-docs-api" or mime_type != "text/plain":
            raise PeerRefused("invalid", f"{self.api} does not export {mime_type}")
        paragraphs = self.store.table("paragraphs").find(lambda p: p["document_id"] == file_id)
        return doc_plain_text(paragraphs)

    def create(self, account_id, title=None):
        m = self.module
        if self.api == "google-docs-api":
            made, key = m.create_document(account_id, title), "documentId"
        elif self.api == "google-sheets-api":
            made, key = m.create_spreadsheet(account_id, {"title": title} if title else None), "spreadsheetId"
        elif self.api == "google-slides-api":
            made, key = m.create_presentation(account_id, title=title), "presentationId"
        else:
            info = {"title": title, "documentTitle": title} if title else {}
            made, key = m.create_form(account_id, info), "formId"
        if not isinstance(made, dict) or key not in made:
            raise PeerRefused("invalid", f"{self.api} refused to create {title!r}: {getattr(made, 'body', made)}")
        return self._entry(self._row(made[key]))

    def rename(self, file_id, title):
        self._row(file_id)
        self.store.table(self.spec["table"]).patch(file_id, {self.spec["title"]: title})
        return self._entry(self._row(file_id))

    def delete(self, file_id):
        self._row(file_id)
        for table, column in self.spec["children"]:
            self.store.table(table).delete_where(lambda r, c=column: r.get(c) == file_id)
        self.store.table(self.spec["table"]).delete(file_id)
        return None


def _token_ok(request):
    token = os.environ.get(PEER_TOKEN_ENV, "").strip()
    return bool(token) and hmac.compare_digest(request.headers.get(PEER_HEADER, ""), token)


def install(app, api, module):
    """Serve ``module``'s files to Drive on the peer routes of ``app``."""
    from fastapi import HTTPException, Request
    from fastapi.responses import JSONResponse, PlainTextResponse

    peer = EditorPeer(api, module)

    def guarded(request, call):
        if not _token_ok(request):
            # The service's own not-found: the peer routes are not shown to the agent.
            raise HTTPException(status_code=404)
        try:
            result = call()
        except PeerRefused as exc:
            return JSONResponse(status_code=200, content={"ok": False, "kind": exc.kind, "message": str(exc)})
        if isinstance(result, str):
            return PlainTextResponse(result, headers={"X-WCB-Peer": "ok"})
        return JSONResponse(status_code=200, content={"ok": True, "result": result})

    async def body(request):
        try:
            return json.loads((await request.body()) or b"{}")
        except ValueError:
            return {}

    @app.get(PEER_PREFIX + "/files", include_in_schema=False)
    def peer_files(request: Request):
        return guarded(request, peer.files)

    @app.get(PEER_PREFIX + "/files/{file_id}/export", include_in_schema=False)
    def peer_export(file_id: str, request: Request):
        # Read off the request, not declared: the agent-facing query-parameter checks
        # (tests/mocks/test_connector_query_params.py) cover declared parameters.
        return guarded(request, lambda: peer.export(file_id, request.query_params.get("mimeType", "")))

    @app.post(PEER_PREFIX + "/files", include_in_schema=False)
    async def peer_create(request: Request):
        data = await body(request)
        return guarded(request, lambda: peer.create(data.get("account_id") or "", data.get("title")))

    @app.patch(PEER_PREFIX + "/files/{file_id}", include_in_schema=False)
    async def peer_rename(file_id: str, request: Request):
        data = await body(request)
        return guarded(request, lambda: peer.rename(file_id, data.get("title") or ""))

    @app.delete(PEER_PREFIX + "/files/{file_id}", include_in_schema=False)
    def peer_delete(file_id: str, request: Request):
        return guarded(request, lambda: peer.delete(file_id))

    return peer


# --- Drive side ------------------------------------------------------------------------------

class HttpPeer:
    """An editor mock in another process or container, reached over its peer routes."""

    def __init__(self, api, base_url):
        self.api = api
        self.base = base_url.rstrip("/")

    def _call(self, method, path, payload=None, query=None):
        token = os.environ.get(PEER_TOKEN_ENV, "").strip()
        if not token:
            raise PeerUnavailable(f"{self.api}: {PEER_TOKEN_ENV} is not set in google-drive-api")
        url = self.base + PEER_PREFIX + path
        if query:
            url += "?" + "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in query.items())
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        # A read is retried through a peer still starting up; a write is sent once, so a
        # create that landed is never made twice.
        attempts = _GET_ATTEMPTS if method == "GET" else 1
        last = ""
        for attempt in range(attempts):
            request = urllib.request.Request(url, data=data, method=method,
                                             headers={PEER_HEADER: token, "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                    raw = response.read()
                    if response.headers.get("X-WCB-Peer") == "ok":
                        return raw.decode("utf-8")
                    reply = json.loads(raw or b"{}")
                    break
            except urllib.error.HTTPError as exc:
                # 404 here is the peer gate (token mismatch, or an editor without the routes).
                raise PeerUnavailable(f"{self.api} refused the peer call {method} {path}: HTTP {exc.code}") from exc
            except (urllib.error.URLError, OSError, ValueError) as exc:
                last = f"{type(exc).__name__}: {exc}"
                if attempt + 1 < attempts:
                    time.sleep(0.25 * (attempt + 1))
        else:
            raise PeerUnavailable(f"{self.api} did not answer {method} {path} at {self.base}: {last}")
        if not reply.get("ok"):
            raise PeerRefused(reply.get("kind") or "invalid", reply.get("message") or "refused")
        return reply.get("result")

    def files(self):
        return self._call("GET", "/files")

    def export(self, file_id, mime_type):
        return self._call("GET", f"/files/{urllib.parse.quote(file_id, safe='')}/export",
                          query={"mimeType": mime_type})

    def create(self, account_id, title=None):
        return self._call("POST", "/files", {"account_id": account_id, "title": title})

    def rename(self, file_id, title):
        return self._call("PATCH", f"/files/{urllib.parse.quote(file_id, safe='')}", {"title": title})

    def delete(self, file_id):
        return self._call("DELETE", f"/files/{urllib.parse.quote(file_id, safe='')}")


_INPROCESS = {}


def register_inprocess(api, module):
    """Serve ``api`` to Drive from ``module``, imported in this process; returns its peer."""
    _INPROCESS[api] = EditorPeer(api, module)
    return _INPROCESS[api]


def clear_inprocess():
    _INPROCESS.clear()


def _env_targets():
    raw = os.environ.get(PEER_URLS_ENV, "").strip()
    targets = {}
    for part in raw.split(","):
        api, sep, url = part.strip().partition("=")
        if sep and api.strip() and url.strip():
            targets[api.strip()] = url.strip()
    return targets


def _stack_targets():
    try:
        ports = json.loads(STACK_PORTS_MANIFEST.read_text(encoding="utf-8"))
        running = {int(p) for p in STACK_ENABLED_PORTS.read_text(encoding="utf-8").split()}
    except (OSError, ValueError):
        return {}
    return {api: f"http://127.0.0.1:{int(port)}" for api, port in ports.items() if int(port) in running}


def peer_for(api):
    """The peer serving ``api``'s live files, or None when ``api`` is not deployed in this run."""
    if api in _INPROCESS:
        return _INPROCESS[api]
    if os.environ.get(PEER_URLS_ENV, "").strip():
        url = _env_targets().get(api)
    else:
        url = _stack_targets().get(api)
    return HttpPeer(api, url) if url else None
