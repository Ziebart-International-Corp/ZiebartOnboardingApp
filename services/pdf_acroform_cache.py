"""Cached AcroForm layout scans (path/mtime/size keyed)."""
from __future__ import annotations

import os

from pdf_form_wizard import (
    collect_acroform_import_specs as _collect_acroform_import_specs_uncached,
    count_pdf_acroform_widgets as _count_pdf_acroform_widgets_uncached,
)

_ACROFORM_SPECS_CACHE: dict = {}
_ACROFORM_COUNT_CACHE: dict = {}


def _pdf_cache_key(pdf_path: str):
    try:
        st = os.stat(pdf_path)
        return (os.path.abspath(pdf_path), st.st_mtime_ns, st.st_size)
    except OSError:
        return (os.path.abspath(pdf_path), 0, 0)


def collect_acroform_import_specs(pdf_path: str):
    key = _pdf_cache_key(pdf_path)
    cached = _ACROFORM_SPECS_CACHE.get(key)
    if cached is not None:
        return cached
    specs = _collect_acroform_import_specs_uncached(pdf_path)
    if len(_ACROFORM_SPECS_CACHE) > 64:
        _ACROFORM_SPECS_CACHE.clear()
    _ACROFORM_SPECS_CACHE[key] = specs
    return specs


def count_pdf_acroform_widgets(pdf_path: str) -> int:
    key = _pdf_cache_key(pdf_path)
    if key in _ACROFORM_COUNT_CACHE:
        return _ACROFORM_COUNT_CACHE[key]
    n = _count_pdf_acroform_widgets_uncached(pdf_path)
    if len(_ACROFORM_COUNT_CACHE) > 128:
        _ACROFORM_COUNT_CACHE.clear()
    _ACROFORM_COUNT_CACHE[key] = n
    return n
