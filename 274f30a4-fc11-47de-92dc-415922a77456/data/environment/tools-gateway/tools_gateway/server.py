"""FastAPI app for the agent tools gateway.

Every route except ``/health`` needs ``Authorization: Bearer <WCB_TOOLS_TOKEN>``,
the per-attempt token the harness mints (``tokens.py``); the token names the run
and task each ledger row is billed to. A tool the batch did not enable answers
404 ``tool_disabled``.

Gateway configuration, all from the environment of the gateway container:

  WCB_TOOLS_ENABLED          comma list of ``browser`` and ``image``
  WCB_TOOLS_HMAC_KEY         batch secret that verifies agent tokens (hex)
  WCB_TOOLS_USAGE_LOG        JSONL usage ledger path
  WCB_BROWSER_RECORD_DIR     where each fetched page is written for review; never read back
  WCB_BROWSER_TIMEOUT        per-fetch timeout seconds (default 20)
  WCB_BROWSER_MAX_BYTES      largest body read (default 3000000)
  WCB_BROWSER_PAGE_CHARS     characters per rendered page (default 8000)
  WCB_IMAGE_MAX_PER_TASK     images one task may request (default 20)
  WCB_IMAGE_MAX_PER_BATCH    images the batch may request (unset: no limit)
  MUSE_IMAGE_*               see image.py

The browser always reads the live web: the removed WCB_BROWSER_SNAPSHOT_MODE and
WCB_BROWSER_SNAPSHOT_DIR stop the gateway at start rather than being ignored.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from . import tokens
from .image import (
    DEFAULT_MAX_PER_TASK, BudgetExceeded, ImageBudget, ImageConfig, ImageRefused, ImageRefusedWithUsage,
    Poster, prepare, send,
)
from .usage import UsageLedger, url_fields

# A delivered task ships this package with the image tool only: the packager
# (script/repackage_to_bundle.py) leaves these modules out. Without them the
# gateway still starts, and refuses to if WCB_TOOLS_ENABLED names the browser.
BROWSER_MODULES = ("blocklist", "browser", "render", "snapshots")
try:
    from .blocklist import Blocklist
    from .browser import Browser, BrowserRefused
    from .snapshots import LIVE_ONLY, SnapshotRecorder, removed_settings
except ModuleNotFoundError as _missing:
    if (_missing.name or "").rpartition(".")[2] not in BROWSER_MODULES:
        raise
    Browser = None

TOOLS = ("browser", "image")
DEFAULT_PORT = 8790


def _image_limit(env: Mapping[str, str], name: str, default: Optional[int]) -> Optional[int]:
    raw = (env.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} must be a whole number of images, got {raw!r}") from None
    if value < 0:
        raise ValueError(f"{name} must not be negative, got {value}")
    return value


@dataclass
class Settings:
    tools: frozenset
    hmac_key: bytes
    usage_log: Path
    snapshot_dir: Optional[Path] = None
    timeout: float = 20.0
    max_bytes: int = 3_000_000
    page_chars: int = 8000
    image: Optional[ImageConfig] = None
    image_max_per_task: int = DEFAULT_MAX_PER_TASK
    image_max_per_batch: Optional[int] = None

    @classmethod
    def from_env(cls, env: Optional[Dict[str, str]] = None) -> "Settings":
        env = os.environ if env is None else env
        tools = frozenset(t.strip() for t in (env.get("WCB_TOOLS_ENABLED") or "").split(",") if t.strip())
        unknown = tools - set(TOOLS)
        if unknown:
            raise ValueError(f"WCB_TOOLS_ENABLED names unknown tool(s): {sorted(unknown)}")
        key = (env.get("WCB_TOOLS_HMAC_KEY") or "").strip()
        if not key:
            raise ValueError("WCB_TOOLS_HMAC_KEY is required")
        log = (env.get("WCB_TOOLS_USAGE_LOG") or "").strip()
        if not log:
            raise ValueError("WCB_TOOLS_USAGE_LOG is required")
        if "browser" in tools and Browser is None:
            raise ValueError("WCB_TOOLS_ENABLED names browser, but this copy of the gateway ships "
                             "without the browser. Set WCB_TOOLS_ENABLED=image.")
        removed = removed_settings(env) if Browser is not None else []
        if removed:
            raise ValueError(f"{' and '.join(removed)} {'is' if len(removed) == 1 else 'are'} set, but "
                             f"{LIVE_ONLY}. Unset {' and '.join(removed)}.")
        record_dir = (env.get("WCB_BROWSER_RECORD_DIR") or "").strip()
        return cls(
            tools=tools,
            hmac_key=bytes.fromhex(key),
            usage_log=Path(log),
            snapshot_dir=Path(record_dir) if record_dir else None,
            timeout=float(env.get("WCB_BROWSER_TIMEOUT") or 20),
            max_bytes=int(env.get("WCB_BROWSER_MAX_BYTES") or 3_000_000),
            page_chars=int(env.get("WCB_BROWSER_PAGE_CHARS") or 8000),
            image=ImageConfig.from_env(env),
            image_max_per_task=_image_limit(env, "WCB_IMAGE_MAX_PER_TASK", DEFAULT_MAX_PER_TASK),
            image_max_per_batch=_image_limit(env, "WCB_IMAGE_MAX_PER_BATCH", None),
        )


class OpenBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    page: int = Field(1, ge=1)


class FindBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    pattern: str


class GenerateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str
    n: int = 1
    size: Optional[str] = None
    output_format: Optional[str] = None


class _Unauthorized(Exception):
    pass


def _error(status: int, reason: str, message: str, **detail: Any) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": reason, "message": message, **detail})


def create_app(settings: Settings, *, browser: Optional[Browser] = None,
               image_post: Optional[Poster] = None) -> FastAPI:
    ledger = UsageLedger(settings.usage_log)
    budget = ImageBudget(settings.usage_log, per_task=settings.image_max_per_task,
                         per_batch=settings.image_max_per_batch)
    if "browser" in settings.tools and browser is None:
        browser = Browser(Blocklist.load(), SnapshotRecorder(settings.snapshot_dir),
                          timeout=settings.timeout, max_bytes=settings.max_bytes,
                          page_chars=settings.page_chars)
    app = FastAPI(title="WildClawBench agent tools gateway", version="1")

    def caller(request: Request) -> Dict[str, str]:
        header = request.headers.get("authorization", "")
        claims = tokens.verify(settings.hmac_key, header[7:].strip()) if header[:7].lower() == "bearer " else None
        if claims is None:
            raise _Unauthorized()
        return claims

    @app.exception_handler(_Unauthorized)
    async def _unauthorized(_request, _exc):
        return _error(401, "invalid_token", "send Authorization: Bearer $WCB_TOOLS_TOKEN")

    def disabled(tool: str) -> Optional[JSONResponse]:
        if tool in settings.tools:
            return None
        return _error(404, "tool_disabled", f"the {tool} tool is not enabled for this run")

    @app.get("/health")
    def health():
        return {"status": "ok", "tools": sorted(settings.tools)}

    def _browse(op: str, url: str, who: Dict[str, str], action):
        where = {**url_fields(url), "host": urlsplit(url).hostname or ""}
        try:
            result, source = action()
        except BrowserRefused as exc:
            ledger.append({**who, "tool": "browser", "op": op, **where,
                           "status": "refused", "reason": exc.reason, "http_status": exc.status})
            return _error(exc.status, exc.reason, exc.message, **exc.detail)
        row = {**who, "tool": "browser", "op": op, **where, "status": "ok",
               "source": source, "http_status": result.get("status", 200)}
        if result["snapshot"]["key"]:
            row["snapshot_key"] = result["snapshot"]["key"]
        ledger.append(row)
        return result

    @app.post("/browser/open")
    def browser_open(body: OpenBody, who: Dict[str, str] = Depends(caller)):
        refused = disabled("browser")
        if refused is not None:
            return refused
        return _browse("open", body.url, who, lambda: browser.open(body.url, body.page))

    @app.post("/browser/find")
    def browser_find(body: FindBody, who: Dict[str, str] = Depends(caller)):
        refused = disabled("browser")
        if refused is not None:
            return refused
        return _browse("find", body.url, who, lambda: browser.find(body.url, body.pattern))

    @app.get("/image/info")
    def image_info(who: Dict[str, str] = Depends(caller)):
        refused = disabled("image")
        if refused is not None:
            return refused
        missing = settings.image.missing()
        return {"model": settings.image.model, "configured": not missing, "missing": missing,
                "images_per_task": budget.allowance(who["run"], who["task"])}

    @app.post("/image/generate")
    def image_generate(body: GenerateBody, who: Dict[str, str] = Depends(caller)):
        refused = disabled("image")
        if refused is not None:
            return refused
        kwargs = {"post": image_post} if image_post is not None else {}
        try:
            payload = prepare(settings.image, body.prompt, n=body.n, size=body.size,
                              output_format=body.output_format)
            with budget.hold(who["run"], who["task"], body.n):
                try:
                    result, fields = send(settings.image, payload, **kwargs)
                except ImageRefusedWithUsage as exc:
                    ledger.append({**who, "tool": "image", "op": "generate", "upstream": True, **exc.ledger})
                    return _error(exc.status, exc.reason, exc.message)
                ledger.append({**who, "tool": "image", "op": "generate", "upstream": True, **fields})
                return result
        except BudgetExceeded as exc:
            ledger.append({**who, "tool": "image", "op": "generate", "upstream": False, "status": "refused",
                           "reason": exc.reason, "model": settings.image.model, **exc.ledger})
            return _error(exc.status, exc.reason, exc.message, **exc.ledger)
        except ImageRefused as exc:
            ledger.append({**who, "tool": "image", "op": "generate", "upstream": False,
                           "status": "refused", "reason": exc.reason, "model": settings.image.model})
            return _error(exc.status, exc.reason, exc.message)

    return app
