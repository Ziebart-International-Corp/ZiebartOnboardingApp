"""Unit tests for pure wizard step helpers."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from document_wizard import (
    first_incomplete_required_wizard_index,
    wizard_progress_counts,
    wizard_required_steps_complete,
)


def test_wizard_progress_counts():
    steps = [
        {"required": True, "filled": True},
        {"required": True, "filled": False},
        {"required": False, "filled": False},
    ]
    done, total = wizard_progress_counts(steps)
    assert done == 1 and total == 3


def test_wizard_required_steps_complete():
    steps = [
        {"required": True, "filled": True},
        {"required": False, "filled": False},
        {"required": True, "filled": True},
    ]
    assert wizard_required_steps_complete(steps) is True
    steps[2]["filled"] = False
    assert wizard_required_steps_complete(steps) is False


def test_first_incomplete_required_wizard_index():
    steps = [
        {"required": False, "filled": False},
        {"required": True, "filled": True},
        {"required": True, "filled": False},
        {"required": True, "filled": False},
    ]
    assert first_incomplete_required_wizard_index(steps) == 2
    for s in steps:
        s["filled"] = True
    assert first_incomplete_required_wizard_index(steps) == max(0, len(steps) - 1)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
