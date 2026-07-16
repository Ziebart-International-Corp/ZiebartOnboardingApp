"""Tests for upload content sniffing."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flask import Flask

from services.uploads_allowed import content_matches_extension, document_upload_too_large


def test_pdf_magic_bytes():
    app = Flask(__name__)
    app.config['MAX_DOCUMENT_UPLOAD_MB'] = 40
    with app.app_context(), tempfile.TemporaryDirectory() as td:
        p = Path(td) / 'x.pdf'
        p.write_bytes(b'%PDF-1.7\n%....')
        assert content_matches_extension(p, 'x.pdf') is True
        p.write_bytes(b'not a pdf')
        assert content_matches_extension(p, 'x.pdf') is False


def test_png_magic_bytes():
    app = Flask(__name__)
    with app.app_context(), tempfile.TemporaryDirectory() as td:
        p = Path(td) / 'x.png'
        p.write_bytes(b'\x89PNG\r\n\x1a\n' + b'\x00' * 8)
        assert content_matches_extension(p, 'x.png') is True


def test_document_size_limit():
    app = Flask(__name__)
    app.config['MAX_DOCUMENT_UPLOAD_MB'] = 1
    with app.app_context():
        assert document_upload_too_large(500_000) is False
        assert document_upload_too_large(2_000_000) is True


if __name__ == '__main__':
    test_pdf_magic_bytes()
    print('PASS test_pdf_magic_bytes')
    test_png_magic_bytes()
    print('PASS test_png_magic_bytes')
    test_document_size_limit()
    print('PASS test_document_size_limit')
