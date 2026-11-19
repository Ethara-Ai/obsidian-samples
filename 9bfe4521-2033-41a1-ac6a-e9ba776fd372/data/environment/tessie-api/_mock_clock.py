"""The "now" every mock stamps its data with and answers time queries against.

The agent runs on its task's simulated clock (src/utils/sim_clock.py and
docker/agent_faketime_shim.js). The harness hands the containers that serve the
task's mocks the very same anchor at the same moments, run start and each turn
boundary (src/utils/docker_utils.py, set_mock_sim_clock), by writing the file
WCB_FAKE_CLOCK_FILE names in the shim's format: it holds the simulated epoch in
milliseconds, and its mtime is the real instant that anchor took effect.
Simulated time is the anchor plus the real time elapsed since then, so it
advances in real time between anchors. Mocks running in the agent's own
container read the agent's own file.

A daemon thread re-reads the file every POLL_SECONDS, so a call here only reads
the anchor it holds. With WCB_FAKE_CLOCK_FILE unset, or no file there, each
function is the real-clock call it replaces. Token issue and expiry
(_connector_auth.py) and the request audit log (tracking_middleware.py) stay on
the real clock on purpose: a turn boundary that moves the story a day on must
not expire a live token. What the agent reads is shown on this clock all the
same: tokeninfo's expires_at, and every response's Date header
(tracking_middleware.py).
"""

from __future__ import annotations

import os
import threading
import time as _time
from datetime import date, datetime, timezone

__all__ = ["POLL_SECONDS", "now", "time", "today", "utcnow"]

POLL_SECONDS = 0.25
_THREAD = "wcb-mock-clock"


class _Poller(threading.Thread):
    def __init__(self) -> None:
        super().__init__(name=_THREAD, daemon=True)
        self.anchor = None  # (simulated epoch seconds, real epoch seconds it took effect at), or None
        self._never = threading.Event()  # timed waits on it pace the polls without time.sleep
        self.refresh()

    def refresh(self) -> None:
        path = os.environ.get("WCB_FAKE_CLOCK_FILE")
        if not path:
            self.anchor = None
            return
        try:
            with open(path, "rb") as fh:
                real = os.fstat(fh.fileno()).st_mtime_ns / 1e9
                raw = fh.read()
        except OSError:
            self.anchor = None
            return
        try:
            self.anchor = (int(raw.strip()) / 1000.0, real)
        except ValueError:
            pass  # read mid-write: keep the anchor held until the next poll

    def run(self) -> None:
        while not self._never.wait(POLL_SECONDS):
            self.refresh()


_POLLER = None
_START = threading.Lock()


def _anchor():
    global _POLLER
    if _POLLER is None:
        with _START:
            if _POLLER is None:
                # One poller per process: a re-imported copy of this module finds the running one.
                running = [t for t in threading.enumerate() if t.name == _THREAD]
                if running:
                    _POLLER = running[0]
                else:
                    poller = _Poller()
                    poller.start()
                    _POLLER = poller
    return _POLLER.anchor


def _simulated(anchor) -> float:
    return anchor[0] + (_time.time() - anchor[1])


def time() -> float:
    """time.time() on the task's simulated clock."""
    anchor = _anchor()
    return _time.time() if anchor is None else _simulated(anchor)


def now(tz=None) -> datetime:
    """datetime.now(tz) on the task's simulated clock."""
    anchor = _anchor()
    return datetime.now(tz) if anchor is None else datetime.fromtimestamp(_simulated(anchor), tz)


def utcnow() -> datetime:
    """datetime.utcnow() on the task's simulated clock: naive, in UTC."""
    return now(timezone.utc).replace(tzinfo=None)


def today() -> date:
    """date.today() on the task's simulated clock."""
    anchor = _anchor()
    return date.today() if anchor is None else date.fromtimestamp(_simulated(anchor))
