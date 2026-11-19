"""Append-only usage ledger for gateway calls, and its per-task roll-up.

The image API is called on our own account and billed back per run, so every
upstream image request becomes one JSON line here, keyed by the run and task the
caller's token names, with the provider's own usage counts copied verbatim and
no price attached (rates are not part of the client's requirements). The price
is applied afterwards, by ``image_cost``, for the run's usage.json. Browser
fetches are recorded beside them, including refusals, so a blocked-domain
attempt is visible after the run. A browser row keeps the full URL, query
string included, so the search terms a rollout sent can be checked after the
run, plus the SHA-256 of the URL as it was requested.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlsplit, urlunsplit


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def url_fields(url: str) -> Dict[str, str]:
    """``url`` as the ledger keeps it, query string included, plus the full URL's SHA-256.

    The fragment and any user:password part go; the browser never sends either.
    """
    parts = urlsplit(url)
    netloc = parts.netloc.rpartition("@")[2]
    return {"url": urlunsplit((parts.scheme, netloc, parts.path, parts.query, "")),
            "url_sha256": hashlib.sha256(url.encode("utf-8", "surrogatepass")).hexdigest()}


def images_requested(rows: Iterable[Dict[str, Any]], run: str, task: Optional[str] = None) -> int:
    """Images asked of the upstream image API by ``run`` (and ``task``), failed requests included."""
    return sum(int(r.get("n") or 0) for r in rows
               if r.get("tool") == "image" and r.get("upstream") is True and r.get("run") == run
               and (task is None or r.get("task") == task))


class UsageLedger:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, row: Dict[str, Any]) -> None:
        line = json.dumps({"ts": utc_now(), **row}, sort_keys=True, ensure_ascii=False)
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()
                os.fsync(fh.fileno())


def read_rows(path: Path) -> Iterable[Dict[str, Any]]:
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows = []
    for line in lines:
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def _add_counts(total: Dict[str, Any], counts: Any) -> None:
    if not isinstance(counts, dict):
        return
    for key, value in counts.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            total[key] = total.get(key, 0) + value
        elif isinstance(value, dict):
            _add_counts(total.setdefault(key, {}), value)


def default_price_per_image() -> float:
    """The price card's per-image price (src/utils/price_card.py). Host side
    only: the gateway shipped in a bundle records usage and never prices it."""
    from src.utils.price_card import IMAGE_PRICE_PER_IMAGE
    return IMAGE_PRICE_PER_IMAGE


def price_per_image(environ: Optional[Dict[str, str]] = None) -> float:
    """Dollars per returned image when the provider reports no cost
    (``MUSE_IMAGE_PRICE_PER_IMAGE``, else the price card's)."""
    raw = ((os.environ if environ is None else environ).get("MUSE_IMAGE_PRICE_PER_IMAGE") or "").strip()
    if not raw:
        return default_price_per_image()
    try:
        price = float(raw)
    except ValueError:
        price = -1.0
    if not 0 <= price < float("inf"):
        raise ValueError(f"MUSE_IMAGE_PRICE_PER_IMAGE must be a number of dollars, zero or more, not {raw!r}")
    return price


def _reported_cost(row: Dict[str, Any]) -> Optional[float]:
    usage = row.get("usage")
    cost = usage.get("cost") if isinstance(usage, dict) else None
    if isinstance(cost, bool) or not isinstance(cost, (int, float)):
        return None
    return float(cost)


def image_cost(path: Path, run: str, task: str,
               price: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """The ``image`` source of one rollout's usage.json, None when the task asked for no image.

    ``cost_usd`` is the provider's reported cost (``usage.cost`` of each ledger
    row) when the provider reports one, otherwise images returned x ``price``
    (default: the price card's ``default_price_per_image``).
    A request with no reported cost and no image returned costs nothing.
    ``cost_source`` says which was used: ``provider``, ``price_setting``, or
    ``mixed`` when only some of the requests that returned images carried a
    cost and the rest were priced from the setting. ``price_per_image`` is
    recorded whenever the setting priced anything.
    """
    rows = [r for r in read_rows(path)
            if r.get("run") == run and r.get("task") == task and r.get("tool") == "image"]
    if not rows:
        return None
    if price is None:
        price = default_price_per_image()
    provider_cost = priced_cost = 0.0
    provider_rows = priced_rows = 0
    reasons: Dict[str, int] = {}
    for r in rows:
        images = int(r.get("images", 0) or 0)
        reported = _reported_cost(r)
        if reported is not None:
            provider_cost += reported
            provider_rows += 1
        elif images:
            priced_cost += images * price
            priced_rows += 1
        if r.get("status") != "ok":
            reason = r.get("reason") or ("upstream_unreachable" if r.get("http_status") == 0 else "upstream_error")
            reasons[reason] = reasons.get(reason, 0) + 1
    if provider_rows and priced_rows:
        cost_source = "mixed"
    else:
        cost_source = "provider" if provider_rows else "price_setting"
    source = {
        "requests": len(rows),
        "images_requested": images_requested(rows, run, task),
        "images": sum(int(r.get("images", 0) or 0) for r in rows),
        "refused": sum(reasons.values()),
        "refused_reasons": dict(sorted(reasons.items())),
        "models": sorted({r.get("model", "") for r in rows if r.get("model")}),
        "cost_usd": round(provider_cost + priced_cost, 6),
        "cost_source": cost_source,
    }
    if cost_source != "provider":
        source["price_per_image"] = price
    tokens = _image_tokens(rows)
    if tokens:
        source["token_usage"] = tokens
    return source


_TOKEN_KEYS = ("prompt_tokens", "completion_tokens", "total_tokens")


def _image_tokens(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    """Provider-reported image-generation tokens summed over the ledger rows.

    Kept under ``token_usage`` (not the top-level token keys) so recompute_combined
    still totals model-call tokens only, while usage.json records what Muse billed.
    """
    totals: Dict[str, int] = {}
    for r in rows:
        usage = r.get("usage")
        if not isinstance(usage, dict):
            continue
        for key in _TOKEN_KEYS:
            value = usage.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                totals[key] = totals.get(key, 0) + value
        details = usage.get("completion_tokens_details")
        image_tokens = details.get("image_tokens") if isinstance(details, dict) else None
        if isinstance(image_tokens, int) and not isinstance(image_tokens, bool):
            totals["image_tokens"] = totals.get("image_tokens", 0) + image_tokens
    return totals


def summarize(path: Path, run: str, task: str) -> Dict[str, Any]:
    """Per-task totals for one run, every count zero when the task made no gateway call."""
    rows = [r for r in read_rows(path) if r.get("run") == run and r.get("task") == task]
    image_rows = [r for r in rows if r.get("tool") == "image"]
    browser_rows = [r for r in rows if r.get("tool") == "browser"]
    provider_usage: Dict[str, Any] = {}
    for r in image_rows:
        _add_counts(provider_usage, r.get("usage"))
    return {
        "run": run,
        "task": task,
        "ledger": str(path),
        "image": {
            "requests": len(image_rows),
            "upstream_requests": sum(1 for r in image_rows if r.get("upstream") is True),
            "succeeded": sum(1 for r in image_rows if r.get("status") == "ok"),
            "images": sum(int(r.get("images", 0) or 0) for r in image_rows),
            "images_requested": images_requested(rows, run, task),
            "budget_refused": sum(1 for r in image_rows if r.get("reason") == "budget_exceeded"),
            "models": sorted({r.get("model", "") for r in image_rows if r.get("model")}),
            "provider_usage": provider_usage,
        },
        "browser": {
            "requests": len(browser_rows),
            "refused": sum(1 for r in browser_rows if r.get("status") == "refused"),
            "blocked_domain": sum(1 for r in browser_rows if r.get("reason") == "blocked_domain"),
            "live_fetches": sum(1 for r in browser_rows if r.get("source") == "live"),
            "snapshot_hits": sum(1 for r in browser_rows if r.get("source") == "snapshot"),
        },
    }
