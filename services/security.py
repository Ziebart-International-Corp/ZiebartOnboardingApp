"""Shared security helpers (safe redirects, etc.)."""
from __future__ import annotations

from urllib.parse import urlparse

from flask import request, url_for


def safe_redirect_url(target, fallback=None):
    """
    Return a same-origin relative URL suitable for redirects / hrefs.

    Rejects protocol-relative URLs (//evil), off-site absolute URLs, and
    javascript:/data: schemes. Absolute same-host URLs are reduced to path+query.
    """
    if fallback is None:
        fallback = url_for('dashboard')
    if not target or not isinstance(target, str):
        return fallback
    target = target.strip()
    if not target:
        return fallback
    lowered = target.lower()
    if lowered.startswith(('javascript:', 'data:', 'vbscript:')):
        return fallback
    # Relative path on this app (not protocol-relative)
    if target.startswith('/') and not target.startswith('//'):
        return target
    try:
        ref = urlparse(request.host_url)
        parsed = urlparse(target)
        if parsed.scheme and parsed.scheme not in ('http', 'https'):
            return fallback
        if parsed.netloc and parsed.netloc.lower() == (ref.netloc or '').lower():
            path = parsed.path or '/'
            if parsed.query:
                path = f'{path}?{parsed.query}'
            return path
    except Exception:
        pass
    return fallback


def relative_request_path():
    """Current request path + query as a relative URL (for login ?next=)."""
    path = request.full_path or request.path or '/'
    if path.endswith('?'):
        path = path[:-1]
    return path or '/'
