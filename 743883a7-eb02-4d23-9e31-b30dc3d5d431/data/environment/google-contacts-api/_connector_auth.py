"""Account-link authentication for the connector mocks that separate connection from permission.

The ranked connector mocks (instagram, facebook, health, ...) model a linked
account the way the client's connectors do: linking an account yields a
credential, and the credential alone authorises nothing. Every operation route
names the one scope it needs, and a bearer token carries only the scopes it was
issued with, so "connected" never implies "allowed to do everything".

Install it next to the shared tracking and admin planes::

    from _connector_auth import ConnectorAuth
    auth = ConnectorAuth("instagram-api", store=instagram_data._store,
                         data_dir=instagram_data.DATA_DIR)
    auth.install(app)

    @app.get("/v21.0/me/accounts", dependencies=[auth.require("instagram_basic")])

SEED. ``auth.json`` in the service directory. A per-task ``mock_data/<api>/``
overlay replaces it like any other seed file::

    {
      "token_ttl_seconds": 3600,
      "agent_client_id": "<client whose credentials the harness exports>",
      "clients": [{"client_id": "...", "client_secret": "...", "account_id": "...",
                   "granted_scopes": [...], "default_scopes": [...]}],
      "tokens": [{"access_token": "...", "client_id": "...", "scopes": [...],
                  "expires_at": "2026-01-01T00:00:00Z"}],
      "refresh_tokens": [{"refresh_token": "...", "client_id": "...", "scopes": [...],
                          "revoked": false}]
    }

``granted_scopes`` is what the account owner consented to for that client;
``default_scopes`` is what a token carries when the request names no scope. A
scope outside ``granted_scopes`` is refused at the token endpoint, and a scope the
token does not carry is refused at the operation. A route may name broader scopes
that include its own (``implied_by``), the way Google's ``presentations`` includes
``presentations.readonly``; a token carrying one of those is admitted too. Issued
tokens live in the shared store (``oauth_tokens``), so the admin plane can revoke
or expire one mid-run the same way it drifts any other row.

ROUTES
  POST /oauth/token      grant_type ``client_credentials`` or ``refresh_token``;
                         form-encoded or JSON body; client authentication in the
                         body or as HTTP Basic. Unknown parameters are ignored,
                         as RFC 6749 section 3.2 requires of a token endpoint.
  GET  /oauth/tokeninfo  the presented bearer token's client, account, scopes,
                         and remaining lifetime.

FAILURES (RFC 6749 section 5.2, RFC 6750 section 3.1)
  401 invalid_token       no bearer token, an unknown one, or an expired one
  403 insufficient_scope  a live token that lacks the route's scope
  token endpoint          400 invalid_request / invalid_grant / invalid_scope /
                          unsupported_grant_type, 401 invalid_client
"""

from __future__ import annotations

import base64
import hmac
import json
import secrets
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

import _mock_clock

GRANT_CLIENT_CREDENTIALS = "client_credentials"
GRANT_REFRESH_TOKEN = "refresh_token"
DEFAULT_TTL_SECONDS = 3600


class OAuthError(Exception):
    """An RFC 6749 / RFC 6750 failure rendered as ``{"error", "error_description"}``."""

    def __init__(self, status: int, error: str, description: str,
                 challenge: Optional[str] = None, scope: Optional[str] = None):
        super().__init__(description)
        self.status = status
        self.error = error
        self.description = description
        self.challenge = challenge
        self.scope = scope


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(int(epoch), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _epoch(value: Any) -> Optional[float]:
    """Seconds since the epoch for an ISO-8601 instant or a number; None when absent."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _scope_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [s for s in value.split() if s]
    return [str(s) for s in value if str(s)]


def load_auth_seed(data_dir: Path) -> Dict[str, Any]:
    with open(Path(data_dir) / "auth.json", encoding="utf-8") as fh:
        seed = json.load(fh)
    if not isinstance(seed, dict) or not isinstance(seed.get("clients"), list):
        raise ValueError(f"{data_dir}/auth.json must be an object with a 'clients' list")
    return seed


class ConnectorAuth:
    """The token endpoint, token introspection, and per-route scope guard for one service."""

    def __init__(self, service: str, store: Any, data_dir: Path,
                 clock: Callable[[], float] = time.time,
                 display_clock: Optional[Callable[[], float]] = None):
        self.service = service
        self.data_dir = Path(data_dir)
        self._store = store
        # Issue and expiry are judged on the real clock, so a turn boundary that
        # moves the story a day on never expires a live token (_mock_clock.py).
        self._clock = clock
        # ...but a time the agent READS is shown on the task's simulated clock:
        # a real date in a tokeninfo answer contradicts the story's date.
        self._display_clock = display_clock or _mock_clock.time
        self.known_scopes: set = set()
        store.register_document("oauth", initial_loader=lambda: load_auth_seed(self.data_dir))
        store.register("oauth_tokens", primary_key="access_token",
                       initial_loader=self._seed_tokens)
        store.register("oauth_refresh_tokens", primary_key="refresh_token",
                       initial_loader=self._seed_refresh_tokens)

    # -- seed --------------------------------------------------------------

    def _seed(self) -> Dict[str, Any]:
        return self._store.document("oauth").get() or {}

    def _seed_tokens(self) -> List[Dict[str, Any]]:
        rows = []
        for t in load_auth_seed(self.data_dir).get("tokens", []):
            expires = _epoch(t.get("expires_at"))
            rows.append({
                "access_token": str(t["access_token"]),
                "client_id": str(t.get("client_id", "")),
                "account_id": str(t.get("account_id", "")),
                "scopes": _scope_list(t.get("scopes")),
                "issued_at": _iso(_epoch(t.get("issued_at")) or 0),
                "expires_at": _iso(expires) if expires is not None else "",
                "grant_type": str(t.get("grant_type", "seed")),
            })
        return rows

    def _seed_refresh_tokens(self) -> List[Dict[str, Any]]:
        return [{
            "refresh_token": str(r["refresh_token"]),
            "client_id": str(r.get("client_id", "")),
            "scopes": _scope_list(r.get("scopes")),
            "revoked": bool(r.get("revoked", False)),
        } for r in load_auth_seed(self.data_dir).get("refresh_tokens", [])]

    def _client(self, client_id: str) -> Optional[Dict[str, Any]]:
        for c in self._seed().get("clients", []):
            if str(c.get("client_id")) == client_id:
                return c
        return None

    def _ttl(self) -> int:
        return int(self._seed().get("token_ttl_seconds", DEFAULT_TTL_SECONDS))

    # -- token endpoint ----------------------------------------------------

    @staticmethod
    async def _params(request: Request) -> Dict[str, str]:
        raw = await request.body()
        ctype = request.headers.get("content-type", "")
        if "application/x-www-form-urlencoded" in ctype:
            return dict(urllib.parse.parse_qsl(raw.decode("utf-8", "replace"),
                                               keep_blank_values=True))
        if not raw.strip():
            return {}
        try:
            data = json.loads(raw)
        except ValueError:
            raise OAuthError(400, "invalid_request",
                             "the token request body must be JSON or form-encoded")
        if not isinstance(data, dict):
            raise OAuthError(400, "invalid_request", "the token request body must be an object")
        out: Dict[str, str] = {}
        for key, value in data.items():
            if isinstance(value, list):
                out[str(key)] = " ".join(str(v) for v in value)
            elif value is not None:
                out[str(key)] = str(value)
        return out

    def _authenticate_client(self, request: Request, params: Dict[str, str],
                             required: bool) -> Optional[Dict[str, Any]]:
        client_id = params.get("client_id", "")
        secret = params.get("client_secret", "")
        header = request.headers.get("authorization", "")
        if header[:6].lower() == "basic ":
            try:
                decoded = base64.b64decode(header[6:].strip()).decode("utf-8")
                basic_id, _, basic_secret = decoded.partition(":")
            except (ValueError, UnicodeDecodeError):
                raise OAuthError(401, "invalid_client", "malformed HTTP Basic client credentials",
                                 challenge=f'Basic realm="{self.service}"')
            client_id = urllib.parse.unquote_plus(basic_id)
            secret = urllib.parse.unquote_plus(basic_secret)
        if not client_id:
            if required:
                raise OAuthError(401, "invalid_client", "client authentication is required",
                                 challenge=f'Basic realm="{self.service}"')
            return None
        client = self._client(client_id)
        if client is None or not hmac.compare_digest(str(client.get("client_secret", "")), secret):
            raise OAuthError(401, "invalid_client", "unknown client or wrong client secret",
                             challenge=f'Basic realm="{self.service}"')
        return client

    def _check_scopes(self, requested: List[str], allowed: List[str], what: str) -> None:
        unknown = [s for s in requested if self.known_scopes and s not in self.known_scopes]
        if unknown:
            raise OAuthError(400, "invalid_scope", f"unknown scope(s): {' '.join(unknown)}")
        refused = [s for s in requested if s not in allowed]
        if refused:
            raise OAuthError(400, "invalid_scope",
                             f"scope(s) not {what}: {' '.join(refused)}")

    def _issue(self, client: Dict[str, Any], scopes: List[str], grant_type: str) -> Dict[str, Any]:
        now = self._clock()
        ttl = self._ttl()
        token = f"{self.service.split('-')[0]}_at_{secrets.token_urlsafe(24)}"
        self._store.table("oauth_tokens").upsert({
            "access_token": token,
            "client_id": str(client.get("client_id", "")),
            "account_id": str(client.get("account_id", "")),
            "scopes": list(scopes),
            "issued_at": _iso(now),
            "expires_at": _iso(now + ttl),
            "grant_type": grant_type,
        })
        return {"access_token": token, "token_type": "Bearer", "expires_in": ttl,
                "scope": " ".join(scopes)}

    async def token(self, request: Request) -> JSONResponse:
        params = await self._params(request)
        grant_type = params.get("grant_type", "")
        if not grant_type:
            raise OAuthError(400, "invalid_request", "grant_type is required")
        requested = _scope_list(params.get("scope"))
        if grant_type == GRANT_CLIENT_CREDENTIALS:
            client = self._authenticate_client(request, params, required=True)
            granted = _scope_list(client.get("granted_scopes"))
            scopes = requested or [s for s in _scope_list(client.get("default_scopes"))
                                   if s in granted]
            self._check_scopes(scopes, granted, "granted to this client")
        elif grant_type == GRANT_REFRESH_TOKEN:
            value = params.get("refresh_token", "")
            if not value:
                raise OAuthError(400, "invalid_request", "refresh_token is required")
            row = self._store.table("oauth_refresh_tokens").get(value)
            if row is None or row.get("revoked"):
                raise OAuthError(400, "invalid_grant", "the refresh token is unknown or revoked")
            client = self._authenticate_client(request, params, required=False)
            if client is not None and str(client.get("client_id")) != row["client_id"]:
                raise OAuthError(400, "invalid_grant", "the refresh token was issued to another client")
            client = client or self._client(row["client_id"])
            if client is None:
                raise OAuthError(400, "invalid_grant", "the refresh token's client no longer exists")
            original = _scope_list(row.get("scopes"))
            scopes = requested or original
            self._check_scopes(scopes, original, "covered by the refresh token")
        else:
            raise OAuthError(400, "unsupported_grant_type",
                             f"grant_type {grant_type!r} is not supported; use "
                             f"{GRANT_CLIENT_CREDENTIALS} or {GRANT_REFRESH_TOKEN}")
        body = self._issue(client, scopes, grant_type)
        return JSONResponse(body, headers={"Cache-Control": "no-store", "Pragma": "no-cache"})

    # -- bearer validation -------------------------------------------------

    def principal(self, request: Request) -> Dict[str, Any]:
        """The live token presented on ``request``, or an ``invalid_token`` failure."""
        realm = f'Bearer realm="{self.service}"'
        header = request.headers.get("authorization", "")
        if header[:7].lower() != "bearer " or not header[7:].strip():
            raise OAuthError(401, "invalid_token", "a bearer access token is required",
                             challenge=realm)
        token = header[7:].strip()
        row = self._store.table("oauth_tokens").get(token)
        if row is None:
            raise OAuthError(401, "invalid_token", "the access token is unknown or revoked",
                             challenge=f'{realm}, error="invalid_token"')
        expires = _epoch(row.get("expires_at"))
        if expires is not None and self._clock() >= expires:
            raise OAuthError(401, "invalid_token", "the access token expired",
                             challenge=f'{realm}, error="invalid_token"')
        return row

    def require(self, scope: Optional[str], implied_by: Sequence[str] = ()):
        """A route dependency admitting only a live token that carries ``scope``.

        ``None`` admits any live token, for an operation the provider serves to
        every authenticated caller (Spotify catalog search, a reachability probe).
        ``implied_by`` names the broader scopes the provider counts as including
        ``scope`` (Google's edit scope includes its ``.readonly`` one); a token
        carrying any of them is admitted as well. The refusal still names ``scope``.
        """
        accepted = ((scope,) + tuple(implied_by)) if scope else ()
        self.known_scopes.update(accepted)

        def _guard(request: Request) -> Dict[str, Any]:
            row = self.principal(request)
            if scope and not set(accepted) & set(_scope_list(row.get("scopes"))):
                raise OAuthError(
                    403, "insufficient_scope",
                    f"this operation needs the {scope!r} scope, which the access token does not carry",
                    challenge=f'Bearer realm="{self.service}", error="insufficient_scope", scope="{scope}"',
                    scope=scope,
                )
            request.state.oauth = row
            return row

        # Read back by the docs generators so a route's scope is stated once, here.
        _guard.oauth_scope = scope or ""
        _guard.oauth_implied_by = accepted[1:]
        _guard.oauth_guard = True
        return Depends(_guard)

    def tokeninfo(self, request: Request) -> Dict[str, Any]:
        row = self.principal(request)
        expires = _epoch(row.get("expires_at"))
        remaining = expires - self._clock() if expires is not None else None
        shown = row.get("expires_at", "")
        if remaining is not None and row.get("grant_type") != "seed":
            # A token this mock issued: its expiry is a real-clock instant. Show
            # the same remaining time from the simulated now instead. A seeded
            # token keeps the expiry its task wrote.
            shown = _iso(self._display_clock() + remaining)
        return {
            "active": True,
            "client_id": row.get("client_id", ""),
            "account_id": row.get("account_id", ""),
            "scope": " ".join(_scope_list(row.get("scopes"))),
            "expires_at": shown,
            "expires_in": max(0, int(remaining)) if remaining is not None else None,
        }

    # -- wiring ------------------------------------------------------------

    def install(self, app: FastAPI) -> None:
        async def _render(_request: Request, exc: OAuthError) -> JSONResponse:
            body = {"error": exc.error, "error_description": exc.description}
            if exc.scope:
                body["required_scope"] = exc.scope
            headers = {"Cache-Control": "no-store"}
            if exc.challenge:
                headers["WWW-Authenticate"] = exc.challenge
            return JSONResponse(status_code=exc.status, content=body, headers=headers)

        app.add_exception_handler(OAuthError, _render)
        app.add_api_route("/oauth/token", self.token, methods=["POST"])
        app.add_api_route("/oauth/tokeninfo", self.tokeninfo, methods=["GET"])
