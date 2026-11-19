"""Write-only record of the pages the text browser fetched, kept for review.

The browser reads the live web on every request. Each page it fetched is
written here once, and nothing here is ever read back to serve the agent: the
record exists so a reviewer can see what a rollout read. A record lives at
``<root>/<key[:2]>/<key>.json``, ``key`` being the SHA-256 of the record file's
own bytes, so two reads of a page that changed in between are two records. The
ledger row of each read names its record as ``snapshot_key``, and after the
rollout the harness copies the records it fetched into ``browser_snapshots/``
beside its ``tool_usage.json``.

Browser replay and the snapshot modes are gone; ``REMOVED_SETTINGS`` names the
settings that used to choose them, which every entry point now refuses.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

REMOVED_SETTINGS = ("WCB_BROWSER_SNAPSHOT_MODE", "WCB_BROWSER_SNAPSHOT_DIR")
LIVE_ONLY = ("browser replay and the snapshot modes no longer exist: the text browser reads the live web "
             "on every request, and the browser_snapshots/ a rollout writes is a record for review that "
             "nothing serves back")


def removed_settings(environ: Mapping[str, str]) -> List[str]:
    """The removed browser settings that ``environ`` still sets."""
    return [name for name in REMOVED_SETTINGS if (environ.get(name) or "").strip()]


def _record_bytes(record: Dict[str, Any]) -> bytes:
    return json.dumps(record, sort_keys=True).encode("utf-8")


def record_path(root: Path, key: str) -> Path:
    return Path(root) / key[:2] / f"{key}.json"


class SnapshotRecorder:
    """Writes each fetched page once; it has no way to read one back."""

    def __init__(self, root: Optional[Path]):
        self.root = Path(root) if root is not None else None
        if self.root is not None:
            self.root.mkdir(parents=True, exist_ok=True)

    def write(self, record: Dict[str, Any]) -> Optional[str]:
        """Keep ``record``; its key, or None when there is no record directory."""
        if self.root is None:
            return None
        data = _record_bytes(record)
        key = hashlib.sha256(data).hexdigest()
        path = record_path(self.root, key)
        if path.exists():
            return key
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".snap-")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            try:
                os.link(tmp, path)
            except FileExistsError:
                pass
            return key
        finally:
            os.unlink(tmp)
