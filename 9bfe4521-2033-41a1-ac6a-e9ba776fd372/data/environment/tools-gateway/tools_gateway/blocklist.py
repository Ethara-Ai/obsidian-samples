"""The client's blocked-domain list and the host matcher that enforces it.

``data/blocked_domains.txt`` is vendored verbatim from the client's
``requirements/2026-09-21 - blocked_domains.md`` by
``script/sync_blocked_domains.py``, with its provenance beside it.

A host is refused when it equals a listed entry or is a subdomain of one
(``news.example.com`` is refused when ``example.com`` is listed). Hosts and
entries are compared case-insensitively, without a trailing dot, and in both
their Unicode and IDNA (punycode) spellings, so ``xn--`` and native forms of an
internationalised entry match each other.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Optional

DATA_DIR = Path(__file__).parent / "data"
LIST_PATH = DATA_DIR / "blocked_domains.txt"
PROVENANCE_PATH = DATA_DIR / "blocked_domains.provenance.json"


def host_forms(host: str) -> set[str]:
    """Every spelling of ``host`` the matcher compares: Unicode and IDNA, lowercased."""
    base = host.strip().rstrip(".").lower()
    if not base:
        return set()
    forms = {base}
    try:
        forms.add(base.encode("idna").decode("ascii"))
    except UnicodeError:
        pass
    try:
        forms.add(base.encode("ascii").decode("idna"))
    except UnicodeError:
        pass
    return forms


class Blocklist:
    def __init__(self, entries: Iterable[str]):
        self._index: dict[str, str] = {}
        self._count = 0
        for entry in entries:
            entry = entry.strip()
            if not entry:
                continue
            self._count += 1
            for form in host_forms(entry):
                self._index.setdefault(form, entry)

    @classmethod
    def load(cls, path: Path = LIST_PATH) -> "Blocklist":
        return cls(path.read_text(encoding="utf-8").splitlines())

    def __len__(self) -> int:
        return self._count

    def match(self, host: str) -> Optional[str]:
        """The listed entry that blocks ``host``, or None when it is allowed."""
        for form in host_forms(host):
            labels = form.split(".")
            for i in range(len(labels)):
                hit = self._index.get(".".join(labels[i:]))
                if hit is not None:
                    return hit
        return None


def provenance(path: Path = PROVENANCE_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
