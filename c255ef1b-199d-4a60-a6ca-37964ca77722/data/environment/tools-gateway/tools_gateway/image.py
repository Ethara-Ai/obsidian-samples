"""Image generation proxy for the client's image model, configured only from the environment.

The client allows its image-generation API in tasks but offers no private tier,
so calls go out on our own account. The endpoint, the model name, and the API
key therefore come from external configuration and nowhere else:

  MUSE_IMAGE_API_BASE          base URL of the OpenAI-compatible images API
  MUSE_IMAGE_MODEL             model id sent with every request
  MUSE_IMAGE_API_KEY           bearer key; never logged, echoed, or written to usage
  MUSE_IMAGE_TOOL_ENABLEMENT   optional JSON object sent as ``tool_enablement``;
                               unset sends the default below, empty sends none
  MUSE_IMAGE_TIMEOUT           optional request timeout in seconds (default 180)

The request is the provider's documented single-shot ``POST {base}/images/generations``
(``model``, ``prompt``, ``n``, ``size``, ``output_format``, ``response_format``).
That format has not been confirmed against the live API; run
``script/probe_image_api.py`` to send one request and compare the answer with
what ``parse_response`` expects. The model's built-in web search, image search,
and shell are switched off by default: they would fetch pages outside the
blocked-domain gate and make an image depend on live web content, which the
browser's reproducibility rules exist to avoid. An operator can re-enable them
through ``MUSE_IMAGE_TOOL_ENABLEMENT``.

``ImageBudget`` is a runaway guard on the images requested, not a budget: the
client sets no image limit and asks only that we call the model on our own
account and bill it back (requirements/2026-09-22 - Use Cases - 22-09.md).
The gateway reads its limits from the environment:

  WCB_IMAGE_MAX_PER_TASK       images one task may request (default 20)
  WCB_IMAGE_MAX_PER_BATCH      images the whole batch may request (unset: no limit)
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from .usage import images_requested, read_rows

DEFAULT_TOOL_ENABLEMENT = {"enable_web_search": False, "enable_image_search": False, "enable_shell": False}
OUTPUT_FORMATS = ("webp", "png", "jpeg")
MAX_IMAGES = 10
MAX_PROMPT_CHARS = 32000
DEFAULT_MAX_PER_TASK = 20
_SIZE = re.compile(r"^\d{2,5}x\d{2,5}$")


class ImageRefused(Exception):
    def __init__(self, status: int, reason: str, message: str):
        super().__init__(message)
        self.status = status
        self.reason = reason
        self.message = message


class ImageRefusedWithUsage(ImageRefused):
    """An upstream failure that still cost a request, carrying its ledger fields."""

    def __init__(self, status: int, reason: str, message: str, ledger: Dict[str, Any]):
        super().__init__(status, reason, message)
        self.ledger = ledger


class BudgetExceeded(ImageRefused):
    """A request the runaway guard stopped before it was sent, carrying its ledger fields."""

    def __init__(self, message: str, ledger: Dict[str, Any]):
        super().__init__(429, "budget_exceeded", message)
        self.ledger = ledger


@dataclass
class ImageConfig:
    base: str = ""
    model: str = ""
    key: str = field(default="", repr=False)
    tool_enablement: Optional[Dict[str, Any]] = None
    timeout: float = 180.0

    @classmethod
    def from_env(cls, env: Optional[Dict[str, str]] = None) -> "ImageConfig":
        env = os.environ if env is None else env
        raw = env.get("MUSE_IMAGE_TOOL_ENABLEMENT")
        if raw is None:
            enablement: Optional[Dict[str, Any]] = dict(DEFAULT_TOOL_ENABLEMENT)
        elif not raw.strip():
            enablement = None
        else:
            enablement = json.loads(raw)
            if not isinstance(enablement, dict):
                raise ValueError("MUSE_IMAGE_TOOL_ENABLEMENT must be a JSON object")
        return cls(
            base=(env.get("MUSE_IMAGE_API_BASE") or "").strip().rstrip("/"),
            model=(env.get("MUSE_IMAGE_MODEL") or "").strip(),
            key=(env.get("MUSE_IMAGE_API_KEY") or "").strip(),
            tool_enablement=enablement,
            timeout=float(env.get("MUSE_IMAGE_TIMEOUT") or 180),
        )

    def missing(self) -> List[str]:
        return [name for name, value in (("MUSE_IMAGE_API_BASE", self.base),
                                         ("MUSE_IMAGE_MODEL", self.model),
                                         ("MUSE_IMAGE_API_KEY", self.key)) if not value]


Poster = Callable[[str, Dict[str, str], bytes, float], Tuple[int, Dict[str, str], bytes]]


def _urllib_post(url: str, headers: Dict[str, str], body: bytes, timeout: float):
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as err:
        resp = err
    with resp:
        return resp.getcode(), {k.lower(): v for k, v in resp.headers.items()}, resp.read()


def _upstream_message(raw: bytes) -> str:
    try:
        err = json.loads(raw).get("error")
    except (ValueError, AttributeError):
        return raw[:300].decode("utf-8", "replace")
    if isinstance(err, dict):
        return str(err.get("message") or err)[:500]
    return str(err)[:500]


def prepare(cfg: ImageConfig, prompt: str, n: int = 1, size: Optional[str] = None,
            output_format: Optional[str] = None) -> Dict[str, Any]:
    """The upstream request body for a valid request; refuses an invalid one before anything is sent."""
    missing = cfg.missing()
    if missing:
        raise ImageRefused(503, "not_configured",
                           "image generation is not configured on this harness (missing "
                           + ", ".join(missing) + ")")
    if not prompt or not prompt.strip():
        raise ImageRefused(400, "invalid_request", "prompt is required")
    if len(prompt) > MAX_PROMPT_CHARS:
        raise ImageRefused(400, "invalid_request", f"prompt is longer than {MAX_PROMPT_CHARS} characters")
    if not 1 <= n <= MAX_IMAGES:
        raise ImageRefused(400, "invalid_request", f"n must be between 1 and {MAX_IMAGES}")
    if size is not None and not _SIZE.match(size):
        raise ImageRefused(400, "invalid_request", "size must look like 1024x1024")
    if output_format is not None and output_format not in OUTPUT_FORMATS:
        raise ImageRefused(400, "invalid_request", "output_format must be one of " + ", ".join(OUTPUT_FORMATS))
    payload: Dict[str, Any] = {"model": cfg.model, "prompt": prompt, "n": n, "response_format": "b64_json"}
    if size:
        payload["size"] = size
    if output_format:
        payload["output_format"] = output_format
    if cfg.tool_enablement is not None:
        payload["tool_enablement"] = cfg.tool_enablement
    return payload


def parse_response(raw: bytes) -> Tuple[Dict[str, Any], List[Dict[str, str]], Dict[str, Any]]:
    """(body, images, usage) of a 200 answer; raises ValueError, KeyError, TypeError or AttributeError
    when the body is not the shape this module expects."""
    body = json.loads(raw)
    images = [{"b64_json": item["b64_json"]} for item in body.get("data", []) if item.get("b64_json")]
    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    return body, images, usage


def send(cfg: ImageConfig, payload: Dict[str, Any],
         post: Poster = _urllib_post) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """(agent-facing result, usage-ledger fields) for one prepared request.

    A request that fails after it was handed to the HTTP client, a network error
    included, raises ``ImageRefusedWithUsage``: the provider may have received
    and billed it, so the ledger records it as sent upstream.
    """
    ledger = {"model": cfg.model, "n": payload["n"], "size": payload.get("size") or "",
              "output_format": payload.get("output_format") or ""}
    started = time.monotonic()
    try:
        status, headers, raw = post(f"{cfg.base}/images/generations",
                                    {"Authorization": f"Bearer {cfg.key}", "Content-Type": "application/json"},
                                    json.dumps(payload).encode("utf-8"), cfg.timeout)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        ledger.update({"http_status": 0, "latency_ms": int((time.monotonic() - started) * 1000),
                       "request_id": "", "status": "error", "images": 0, "error": str(exc)[:500]})
        raise ImageRefusedWithUsage(502, "upstream_unreachable", f"the image API could not be reached: {exc}",
                                    ledger)
    ledger.update({"http_status": status, "latency_ms": int((time.monotonic() - started) * 1000),
                   "request_id": headers.get("x-request-id") or headers.get("x-fb-trace-id") or ""})
    if status != 200:
        message = _upstream_message(raw)
        ledger.update({"status": "error", "images": 0, "error": message})
        raise ImageRefusedWithUsage(502 if status >= 500 else status, "upstream_error",
                                    f"the image API answered {status}: {message}", ledger)
    try:
        body, images, usage = parse_response(raw)
    except (ValueError, KeyError, TypeError, AttributeError):
        ledger.update({"status": "error", "images": 0, "error": "malformed response"})
        raise ImageRefusedWithUsage(502, "upstream_error", "the image API returned a malformed response", ledger)
    ledger.update({"status": "ok", "images": len(images), "usage": usage})
    result = {"model": cfg.model, "created": body.get("created"),
              "output_format": body.get("output_format") or payload.get("output_format") or "",
              "images": images, "usage": usage}
    return result, ledger


def generate(cfg: ImageConfig, prompt: str, n: int = 1, size: Optional[str] = None,
             output_format: Optional[str] = None,
             post: Poster = _urllib_post) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """(agent-facing result, usage-ledger fields) for one generation request."""
    return send(cfg, prepare(cfg, prompt, n=n, size=size, output_format=output_format), post=post)


class ImageBudget:
    """Per-task and per-batch ceilings on images requested upstream, enforced from the usage ledger.

    Every request sent upstream counts its ``n``, failed ones included, because
    a failed call may still be billed. Requests still in flight count too, so
    concurrent calls cannot overshoot a ceiling between the check and the
    ledger row.
    """

    def __init__(self, ledger_path: Path, per_task: int = DEFAULT_MAX_PER_TASK,
                 per_batch: Optional[int] = None):
        self.ledger_path = Path(ledger_path)
        self.per_task = per_task
        self.per_batch = per_batch
        self._lock = threading.Lock()
        self._in_flight: Dict[Tuple[str, str], int] = {}

    def _requested(self, rows: List[Dict[str, Any]], run: str, task: Optional[str] = None) -> int:
        pending = sum(n for (r, t), n in self._in_flight.items()
                      if r == run and (task is None or t == task))
        return images_requested(rows, run, task) + pending

    def allowance(self, run: str, task: str) -> Dict[str, int]:
        """The per-task ceiling, what this task has requested, and what it may still request."""
        with self._lock:
            requested = self._requested(list(read_rows(self.ledger_path)), run, task)
        return {"limit": self.per_task, "requested": requested,
                "remaining": max(0, self.per_task - requested)}

    @contextmanager
    def hold(self, run: str, task: str, n: int) -> Iterator[None]:
        """Admit a request for ``n`` images until the block ends, or raise ``BudgetExceeded``.

        Append the request's ledger row inside the block, so it is counted
        before its hold is released.
        """
        with self._lock:
            rows = list(read_rows(self.ledger_path))
            ceilings = [("per_task", self.per_task, self._requested(rows, run, task), "this task",
                         "WCB_IMAGE_MAX_PER_TASK")]
            if self.per_batch is not None:
                ceilings.append(("per_batch", self.per_batch, self._requested(rows, run), "this batch",
                                 "WCB_IMAGE_MAX_PER_BATCH"))
            for scope, limit, requested, who, setting in ceilings:
                if requested + n > limit:
                    raise BudgetExceeded(
                        f"{who} has requested {requested} of its {limit} images, so {n} more would pass the "
                        f"{scope.replace('_', '-')} image limit ({setting}). The limit stops runaway "
                        f"generation; nothing was sent.",
                        {"n": n, "limit": scope, "limit_images": limit, "requested_images": requested})
            self._in_flight[(run, task)] = self._in_flight.get((run, task), 0) + n
        try:
            yield
        finally:
            with self._lock:
                left = self._in_flight[(run, task)] - n
                if left:
                    self._in_flight[(run, task)] = left
                else:
                    del self._in_flight[(run, task)]

