"""Shared rate limiting — file-backed so IIS FastCGI workers share buckets."""
from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

from config import BASE_DIR

_lock = threading.Lock()
_hits: dict[str, deque[float]] = defaultdict(deque)

_RATE_DIR = Path(os.environ.get('RATE_LIMIT_DIR') or (BASE_DIR / 'logs' / 'rate_limits'))


def _safe_key(key: str) -> str:
    return ''.join(c if c.isalnum() or c in '-_.' else '_' for c in key)[:180]


def _file_path(key: str) -> Path:
    return _RATE_DIR / f'{_safe_key(key)}.json'


def _load_hits(path: Path, now: float, window_seconds: int) -> list[float]:
    try:
        raw = json.loads(path.read_text(encoding='utf-8'))
        hits = [float(x) for x in (raw.get('hits') or [])]
    except Exception:
        hits = []
    return [t for t in hits if (now - t) <= window_seconds]


def _save_hits(path: Path, hits: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps({'hits': hits}), encoding='utf-8')
    tmp.replace(path)


def too_many_requests(key: str, limit: int = 10, window_seconds: int = 60) -> bool:
    """
    Return True if this key has already hit `limit` events inside the window.
    On False, records the current hit.

    Uses a shared file under logs/rate_limits so multiple IIS workers share state.
    Falls back to in-process memory if the file store is unavailable.
    """
    now = time.time()
    try:
        path = _file_path(key)
        with _lock:
            hits = _load_hits(path, now, window_seconds)
            if len(hits) >= limit:
                return True
            hits.append(now)
            _save_hits(path, hits)
            return False
    except Exception:
        # In-process fallback (single worker)
        mono = time.monotonic()
        with _lock:
            q = _hits[key]
            while q and (mono - q[0]) > window_seconds:
                q.popleft()
            if len(q) >= limit:
                return True
            q.append(mono)
            return False


def reset_rate_limits() -> None:
    """Test helper: clear memory buckets and on-disk files."""
    with _lock:
        _hits.clear()
        try:
            if _RATE_DIR.exists():
                for p in _RATE_DIR.glob('*.json'):
                    try:
                        p.unlink()
                    except OSError:
                        pass
        except OSError:
            pass
