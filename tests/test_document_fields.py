"""Unit tests for typed-field validation helpers."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.document_fields import (
    _field_is_phone_like,
    normalize_last4_typed_value,
    normalize_typed_field_type,
    typed_field_is_phone_like,
    validate_typed_field_value,
)


def test_normalize_last4_digits_only():
    assert normalize_last4_typed_value("1234") == "XXX-XX-1234"
    assert normalize_last4_typed_value("12") == ""
    assert normalize_last4_typed_value("XXX-XX-9876") == "XXX-XX-9876"
    assert normalize_last4_typed_value("ssn 0000") == "XXX-XX-0000"
    assert normalize_last4_typed_value("123456789") == "XXX-XX-6789"


def test_normalize_typed_field_type():
    assert normalize_typed_field_type("phone") == "phone"
    assert normalize_typed_field_type("BOGUS") == "text"
    assert normalize_typed_field_type(None) == "text"


def test_field_is_phone_like():
    assert _field_is_phone_like("phone") is True
    assert _field_is_phone_like("text", "Mobile Phone") is True
    assert _field_is_phone_like("text", "Full Name") is False
    field = SimpleNamespace(field_type="text", field_label="Work Phone", placeholder=None)
    assert typed_field_is_phone_like(field) is True
    assert typed_field_is_phone_like(None) is False


def test_validate_typed_field_value_phone_and_last4():
    ok, err = validate_typed_field_value("phone", "555-123-4567")
    assert ok and err is None
    ok, err = validate_typed_field_value("phone", "not-a-phone")
    assert not ok and err
    ok, err = validate_typed_field_value("last4", "4321")
    assert ok and err is None
    ok, err = validate_typed_field_value("last4", "12")
    assert not ok
    ok, err = validate_typed_field_value("number", "3.14")
    assert ok
    ok, err = validate_typed_field_value("number", "abc")
    assert not ok
    ok, err = validate_typed_field_value("checkbox_choice", "X")
    assert ok
    ok, err = validate_typed_field_value("checkbox_choice", "yes")
    assert not ok
    ok, err = validate_typed_field_value("text", "N/A")
    assert ok
    ok, err = validate_typed_field_value("text", "")
    assert not ok


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
