"""User-facing error helpers — never leak exception details to clients."""
from __future__ import annotations

from typing import Optional

from flask import current_app, flash, jsonify


GENERIC_ERROR = 'Something went wrong. Please try again.'


def log_exception(exc: BaseException, context: str = '') -> None:
    """Log full exception with traceback."""
    try:
        if context:
            current_app.logger.exception('%s', context, exc_info=exc)
        else:
            current_app.logger.exception('Unhandled error', exc_info=exc)
    except Exception:
        pass


def flash_error(public_message: str, exc: Optional[BaseException] = None) -> None:
    """Flash a safe message; log the real exception when provided."""
    if exc is not None:
        log_exception(exc, public_message)
    flash(public_message or GENERIC_ERROR, 'error')


def json_error(
    public_message: str = GENERIC_ERROR,
    status: int = 500,
    exc: Optional[BaseException] = None,
    **extra,
):
    """JSON error payload without exception text."""
    if exc is not None:
        log_exception(exc, public_message)
    payload = {
        'success': False,
        'error': public_message or GENERIC_ERROR,
        'message': public_message or GENERIC_ERROR,
    }
    payload.update(extra)
    return jsonify(payload), status
