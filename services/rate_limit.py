"""Simple in-process rate limiting (no Redis)."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

_lock = threading.Lock()
_hits: dict[str, deque[float]] = defaultdict(deque)


def too_many_requests(key: str, limit: int = 10, window_seconds: int = 60) -> bool:
    """
    Return True if this key has already hit `limit` events inside the window.
    On False, records the current hit.
    """
    now = time.monotonic()
    with _lock:
        q = _hits[key]
        while q and (now - q[0]) > window_seconds:
            q.popleft()
        if len(q) >= limit:
            return True
        q.append(now)
        return False


def reset_rate_limits() -> None:
    """Test helper: clear all buckets."""
    with _lock:
        _hits.clear()
