"""Smoke tests for NewHireApp modernization baseline.

Run:  .\\.venv\\Scripts\\python.exe -m pytest tests/test_smoke.py -q
  or:  .\\.venv\\Scripts\\python.exe tests/test_smoke.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_import_app_registers_routes():
    import app as main

    rules = list(main.app.url_map.iter_rules())
    endpoints = {r.endpoint for r in rules}
    assert len(rules) >= 157
    for required in (
        "login",
        "view_documents",
        "document_wizard_save_field",
        "admin_dashboard",
        "healthz",
        "sign_document",
    ):
        assert required in endpoints, f"missing endpoint {required}"


def test_healthz():
    import app as main

    client = main.app.test_client()
    resp = client.get("/healthz")
    assert resp.status_code in (200, 503)
    data = resp.get_json()
    assert "app" in data and data["app"] == "ok"
    assert "db" in data
    assert "uploads" in data


def test_services_reexported():
    import app as main

    assert callable(main.send_email)
    assert callable(main._persist_signed_pdf_copy)
    assert callable(main._finalize_document_completion)
    assert callable(main._ensure_stores_and_store_id)
    assert callable(main.documents_for_user_files)
    assert callable(main._asana_is_connected)
    assert callable(main.get_admin_setting)
    assert callable(main.is_pure_manager)
    assert callable(main.user_sign_document_url)
    assert callable(main.collect_acroform_import_specs)
    assert callable(main.normalize_email)
    assert callable(main.user_mobile_bottom_nav_markup)
    assert callable(main.register_app_hooks)
    assert isinstance(main.GLOBAL_METALLIC_THEME_CSS, str) and len(main.GLOBAL_METALLIC_THEME_CSS) > 100
    assert "serve_ziebart_logo" in main.app.view_functions
    assert "serve_favicon" in main.app.view_functions
    assert "admin_jobs" in main.app.view_functions
    from services.jobs import enqueue_or_persist_signed_pdf
    assert callable(enqueue_or_persist_signed_pdf)


def test_acroform_cache_helpers():
    import app as main

    assert callable(main.collect_acroform_import_specs)
    assert callable(main.count_pdf_acroform_widgets)


if __name__ == "__main__":
    # Minimal runner without pytest dependency
    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
    raise SystemExit(1 if failures else 0)
