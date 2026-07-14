"""Flask-bound Asana OAuth + feedback submission wrappers."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from flask import current_app, url_for

from models import db
import config
from asana_feedback import (
    AsanaError,
    connected_user_label,
    create_feedback_task,
    refresh_access_token,
    token_expires_at,
)

ASANA_REDIRECT_URI = getattr(config, "ASANA_REDIRECT_URI", "") or os.getenv("ASANA_REDIRECT_URI", "")
ASANA_CLIENT_ID = getattr(config, "ASANA_CLIENT_ID", "") or os.getenv("ASANA_CLIENT_ID", "")
ASANA_CLIENT_SECRET = getattr(config, "ASANA_CLIENT_SECRET", "") or os.getenv("ASANA_CLIENT_SECRET", "")
ASANA_ACCESS_TOKEN = getattr(config, "ASANA_ACCESS_TOKEN", "") or os.getenv("ASANA_ACCESS_TOKEN", "")
ASANA_REFRESH_TOKEN = getattr(config, "ASANA_REFRESH_TOKEN", "") or os.getenv("ASANA_REFRESH_TOKEN", "")
ASANA_FEEDBACK_PROJECT_GID = getattr(config, "ASANA_FEEDBACK_PROJECT_GID", "") or os.getenv("ASANA_FEEDBACK_PROJECT_GID", "")
ASANA_SECTION_GID_COMMENT = getattr(config, "ASANA_SECTION_GID_COMMENT", None)
ASANA_SECTION_GID_ISSUE = getattr(config, "ASANA_SECTION_GID_ISSUE", None)
ASANA_SECTION_GID_SUGGESTION = getattr(config, "ASANA_SECTION_GID_SUGGESTION", None)
ASANA_FEEDBACK_ASSIGNEE_GID = getattr(config, "ASANA_FEEDBACK_ASSIGNEE_GID", None)


def get_admin_setting(key, default=""):
    import app as main
    return main.get_admin_setting(key, default)


def set_admin_setting(key, value):
    import app as main
    return main.set_admin_setting(key, value)


def _asana_redirect_uri():
    if ASANA_REDIRECT_URI:
        return ASANA_REDIRECT_URI.strip()
    return url_for('asana_oauth_callback', _external=True)


def _asana_oauth_configured():
    return bool(ASANA_CLIENT_ID and ASANA_CLIENT_SECRET)


def _asana_env_token_configured():
    return bool((ASANA_ACCESS_TOKEN or '').strip())


def _asana_feedback_ready():
    """True when feedback can create Asana tasks (env token or OAuth tokens + project GID)."""
    if not ASANA_FEEDBACK_PROJECT_GID:
        return False
    if _asana_env_token_configured():
        return True
    if not _asana_oauth_configured():
        return False
    return bool(
        (ASANA_REFRESH_TOKEN or '').strip()
        or get_admin_setting('asana_refresh_token')
        or get_admin_setting('asana_access_token')
    )


def _asana_store_tokens(token_payload):
    access = token_payload.get('access_token') or ''
    refresh = token_payload.get('refresh_token') or ''
    expires_in = int(token_payload.get('expires_in') or 3600)
    set_admin_setting('asana_access_token', access)
    if refresh:
        set_admin_setting('asana_refresh_token', refresh)
    set_admin_setting('asana_token_expires_at', token_expires_at(expires_in))
    set_admin_setting('asana_connected_user', connected_user_label(token_payload))
    db.session.commit()


def _asana_get_access_token():
    """Return a valid Asana bearer token (.env PAT first, else OAuth refresh)."""
    env_token = (ASANA_ACCESS_TOKEN or '').strip()
    if env_token:
        return env_token
    if not _asana_oauth_configured():
        return None
    access = get_admin_setting('asana_access_token')
    expires_raw = get_admin_setting('asana_token_expires_at')
    if access and expires_raw:
        try:
            expires_dt = datetime.fromisoformat(expires_raw.replace('Z', '+00:00'))
            if datetime.utcnow().replace(tzinfo=expires_dt.tzinfo) < expires_dt:
                return access
        except Exception:
            if access:
                return access
    refresh = (ASANA_REFRESH_TOKEN or '').strip() or get_admin_setting('asana_refresh_token')
    if not refresh:
        return None
    try:
        payload = refresh_access_token(ASANA_CLIENT_ID, ASANA_CLIENT_SECRET, refresh)
    except AsanaError:
        return None
    _asana_store_tokens(payload)
    return payload.get('access_token') or None


def _asana_is_connected():
    if _asana_env_token_configured():
        return True
    return bool(get_admin_setting('asana_refresh_token') or get_admin_setting('asana_access_token'))


def _asana_clear_tokens():
    for key in (
        'asana_access_token',
        'asana_refresh_token',
        'asana_token_expires_at',
        'asana_connected_user',
    ):
        set_admin_setting(key, '')
    db.session.commit()


def _create_asana_feedback_task(form_data, photo_path=None, photo_filename=None):
    if not ASANA_FEEDBACK_PROJECT_GID:
        raise AsanaError('ASANA_FEEDBACK_PROJECT_GID is not set in .env.')
    access_token = _asana_get_access_token()
    if not access_token:
        raise AsanaError(
            'Asana is not configured. Set ASANA_ACCESS_TOKEN in .env '
            '(personal access token or service account token from Asana).'
        )
    return create_feedback_task(
        access_token,
        ASANA_FEEDBACK_PROJECT_GID,
        form_data,
        photo_path=photo_path,
        photo_filename=photo_filename,
        section_gid=ASANA_FEEDBACK_SECTION_GIDS.get(form_data.get('feedback_type') or 'comment'),
        assignee_gid=ASANA_FEEDBACK_ASSIGNEE_GID,
    )


def _save_feedback_submission(form_data, photo_file=None):
    """Persist feedback locally and create an Asana task when connected."""
    import json
    upload_dir = current_app.config['FEEDBACK_UPLOAD_FOLDER']
    upload_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    safe_user = re.sub(r'[^a-zA-Z0-9_-]+', '_', form_data.get('username') or 'user')[:40]
    base_name = f'{ts}_{safe_user}'
    photo_filename = None
    photo_path = None
    if photo_file and photo_file.filename:
        if not _feedback_allowed_image(photo_file.filename):
            raise ValueError('Photo must be a JPG, PNG, GIF, or WebP image.')
        ext = photo_file.filename.rsplit('.', 1)[1].lower()
        photo_filename = secure_filename(f'{base_name}.{ext}')
        photo_path = upload_dir / photo_filename
        photo_file.save(photo_path)
    asana_task_id = None
    asana_error = None
    try:
        asana_task_id = _create_asana_feedback_task(form_data, photo_path=photo_path, photo_filename=photo_filename)
    except AsanaError as exc:
        asana_error = str(exc)
        current_app.logger.warning('Asana feedback task failed: %s', exc)
    except Exception as exc:
        asana_error = str(exc)
        _log_exception_to_file(exc)
    payload = {
        'submitted_at': datetime.utcnow().isoformat() + 'Z',
        **form_data,
        'photo_filename': photo_filename,
        'asana_task_id': asana_task_id,
        'asana_error': asana_error,
    }
    json_path = upload_dir / f'{base_name}.json'
    with open(json_path, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    return json_path, asana_task_id, asana_error

