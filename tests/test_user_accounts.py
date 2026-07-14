"""Unit tests for user account helpers."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.user_accounts import normalize_email
from services.rate_limit import reset_rate_limits, too_many_requests


def test_normalize_email():
    assert normalize_email("  Ada@Example.COM ") == "ada@example.com"
    assert normalize_email("") is None
    assert normalize_email(None) is None
    assert normalize_email("   ") is None


def test_rate_limit_buckets():
    reset_rate_limits()
    key = "test:unit:rate"
    for _ in range(10):
        assert too_many_requests(key, limit=10, window_seconds=60) is False
    assert too_many_requests(key, limit=10, window_seconds=60) is True
    reset_rate_limits()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
