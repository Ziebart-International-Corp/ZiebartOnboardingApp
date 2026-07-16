"""Upload filename allow-lists and content sniffing."""
from __future__ import annotations

from pathlib import Path
from typing import Union

from flask import current_app


def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


def allowed_video_file(filename):
    """Check if video file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_VIDEO_EXTENSIONS']


def extension_of(filename: str) -> str:
    if not filename or '.' not in filename:
        return ''
    return filename.rsplit('.', 1)[1].lower()


def sniff_file_header(path: Union[Path, str], nbytes: int = 16) -> bytes:
    p = Path(path)
    with open(p, 'rb') as fh:
        return fh.read(nbytes)


def content_matches_extension(path: Union[Path, str], filename: str) -> bool:
    """
    Lightweight magic-byte check for common onboarding upload types.
    Returns True when unknown/unsupported types (rely on extension only).
    """
    ext = extension_of(filename)
    try:
        header = sniff_file_header(path, 16)
    except OSError:
        return False
    if ext == 'pdf':
        return header.startswith(b'%PDF')
    if ext in ('jpg', 'jpeg'):
        return header.startswith(b'\xff\xd8\xff')
    if ext == 'png':
        return header.startswith(b'\x89PNG\r\n\x1a\n')
    if ext == 'gif':
        return header.startswith(b'GIF87a') or header.startswith(b'GIF89a')
    if ext == 'webp':
        return len(header) >= 12 and header[:4] == b'RIFF' and header[8:12] == b'WEBP'
    if ext in ('doc', 'xls'):
        return header.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1')
    if ext in ('docx', 'xlsx'):
        return header.startswith(b'PK\x03\x04') or header.startswith(b'PK\x05\x06')
    if ext == 'svg':
        sample = header.lstrip().lower()
        return sample.startswith(b'<?xml') or sample.startswith(b'<svg')
    if ext == 'txt':
        return b'\x00' not in header
    return True


def document_upload_too_large(size_bytes: int) -> bool:
    max_mb = int(current_app.config.get('MAX_DOCUMENT_UPLOAD_MB') or 40)
    return size_bytes > max_mb * 1024 * 1024
