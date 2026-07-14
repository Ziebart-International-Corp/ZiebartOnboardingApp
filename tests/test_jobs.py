"""Unit tests for job helper predicates (no DB)."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.jobs import can_retry_job, job_is_stuck, MAX_JOB_ATTEMPTS


def test_can_retry_job():
    assert can_retry_job(0) is True
    assert can_retry_job(MAX_JOB_ATTEMPTS - 1) is True
    assert can_retry_job(MAX_JOB_ATTEMPTS) is False
    assert can_retry_job(None) is True


def test_job_is_stuck():
    now = datetime(2026, 7, 13, 12, 0, 0)
    fresh = now - timedelta(minutes=5)
    old = now - timedelta(minutes=20)
    assert job_is_stuck(fresh, now=now, stuck_after_minutes=15) is False
    assert job_is_stuck(old, now=now, stuck_after_minutes=15) is True
    assert job_is_stuck(None, now=now) is True


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
