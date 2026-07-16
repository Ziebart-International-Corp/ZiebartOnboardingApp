"""Tests for safe redirect helpers."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.security import safe_redirect_url


def test_safe_redirect_relative_ok():
    from flask import Flask
    app = Flask(__name__)
    with app.test_request_context('/login', base_url='https://ziebartonboarding.com'):
        assert safe_redirect_url('/dashboard', '/fallback') == '/dashboard'
        assert safe_redirect_url('/tasks?x=1', '/fallback') == '/tasks?x=1'


def test_safe_redirect_rejects_external():
    from flask import Flask
    app = Flask(__name__)
    with app.test_request_context('/login', base_url='https://ziebartonboarding.com'):
        assert safe_redirect_url('https://evil.example/phish', '/fallback') == '/fallback'
        assert safe_redirect_url('//evil.example/phish', '/fallback') == '/fallback'
        assert safe_redirect_url('javascript:alert(1)', '/fallback') == '/fallback'


def test_safe_redirect_same_host_absolute():
    from flask import Flask
    app = Flask(__name__)
    with app.test_request_context('/login', base_url='https://ziebartonboarding.com'):
        assert (
            safe_redirect_url('https://ziebartonboarding.com/welcome?x=1', '/fallback')
            == '/welcome?x=1'
        )


if __name__ == '__main__':
    test_safe_redirect_relative_ok()
    print('PASS test_safe_redirect_relative_ok')
    test_safe_redirect_rejects_external()
    print('PASS test_safe_redirect_rejects_external')
    test_safe_redirect_same_host_absolute()
    print('PASS test_safe_redirect_same_host_absolute')
