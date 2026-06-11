"""Asana OAuth and feedback task helpers (stdlib HTTP only)."""
import base64
import hashlib
import json
import mimetypes
import secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Any, Optional

ASANA_AUTHORIZE_URL = 'https://app.asana.com/-/oauth_authorize'
ASANA_TOKEN_URL = 'https://app.asana.com/-/oauth_token'
ASANA_API_BASE = 'https://app.asana.com/api/1.0'
# Register these scopes on your Asana app (Developer Console → OAuth → Permission scopes).
DEFAULT_SCOPES = 'tasks:write attachments:write projects:read'

FEEDBACK_TYPE_LABELS = {
    'comment': 'Comment',
    'issue': 'Issue',
    'suggestion': 'Suggestion',
}


class AsanaError(Exception):
    """Raised when the Asana API returns an error."""


def generate_pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for OAuth PKCE (S256)."""
    verifier = secrets.token_urlsafe(48)[:128]
    digest = hashlib.sha256(verifier.encode('ascii')).digest()
    challenge = base64.urlsafe_b64encode(digest).decode('ascii').rstrip('=')
    return verifier, challenge


def build_authorization_url(
    client_id: str,
    redirect_uri: str,
    state: str,
    code_challenge: str,
    scopes: str = DEFAULT_SCOPES,
) -> str:
    params = {
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'state': state,
        'code_challenge_method': 'S256',
        'code_challenge': code_challenge,
        'scope': scopes,
    }
    return ASANA_AUTHORIZE_URL + '?' + urllib.parse.urlencode(params)


def _form_post(url: str, data: dict[str, str]) -> dict[str, Any]:
    body = urllib.parse.urlencode(data).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=body,
        method='POST',
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')
        raise AsanaError(f'Asana token request failed ({exc.code}): {detail}') from exc


def exchange_authorization_code(
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    code: str,
    code_verifier: str,
) -> dict[str, Any]:
    return _form_post(
        ASANA_TOKEN_URL,
        {
            'grant_type': 'authorization_code',
            'client_id': client_id,
            'client_secret': client_secret,
            'redirect_uri': redirect_uri,
            'code': code,
            'code_verifier': code_verifier,
        },
    )


def refresh_access_token(
    client_id: str,
    client_secret: str,
    refresh_token: str,
) -> dict[str, Any]:
    return _form_post(
        ASANA_TOKEN_URL,
        {
            'grant_type': 'refresh_token',
            'client_id': client_id,
            'client_secret': client_secret,
            'refresh_token': refresh_token,
        },
    )


def _api_json(
    method: str,
    path: str,
    access_token: str,
    payload: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    url = ASANA_API_BASE + path
    data = None
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Accept': 'application/json',
    }
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json; charset=UTF-8'
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode('utf-8')
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')
        raise AsanaError(f'Asana API {method} {path} failed ({exc.code}): {detail}') from exc


def _multipart_attach(
    access_token: str,
    task_gid: str,
    file_path,
    filename: str,
) -> dict[str, Any]:
    content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
    file_bytes = file_path.read_bytes() if hasattr(file_path, 'read_bytes') else open(file_path, 'rb').read()
    boundary = f'----AsanaBoundary{secrets.token_hex(12)}'
    lines: list[bytes] = []

    def add_field(name: str, value: str) -> None:
        lines.append(f'--{boundary}\r\n'.encode())
        lines.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        lines.append(value.encode('utf-8'))
        lines.append(b'\r\n')

    add_field('parent', task_gid)
    lines.append(f'--{boundary}\r\n'.encode())
    lines.append(
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode()
    )
    lines.append(f'Content-Type: {content_type}\r\n\r\n'.encode())
    lines.append(file_bytes)
    lines.append(b'\r\n')
    lines.append(f'--{boundary}--\r\n'.encode())
    body = b''.join(lines)

    req = urllib.request.Request(
        ASANA_API_BASE + '/attachments',
        data=body,
        method='POST',
        headers={
            'Authorization': f'Bearer {access_token}',
            'Content-Type': f'multipart/form-data; boundary={boundary}',
            'Accept': 'application/json',
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')
        raise AsanaError(f'Asana attachment upload failed ({exc.code}): {detail}') from exc


def build_feedback_task_name(feedback_type: str, title: str, description: str) -> str:
    label = FEEDBACK_TYPE_LABELS.get(feedback_type, 'Feedback')
    summary = (title or description or 'New feedback').strip()
    if len(summary) > 120:
        summary = summary[:117] + '...'
    return f'[Onboarding App] {label}: {summary}'


def build_feedback_task_notes(form_data: dict[str, Any]) -> str:
    label = FEEDBACK_TYPE_LABELS.get(form_data.get('feedback_type'), 'Feedback')
    parts = [
        f'Type: {label}',
        f'From: {form_data.get("full_name") or form_data.get("username") or "Unknown"}',
    ]
    if form_data.get('email'):
        parts.append(f'Email: {form_data["email"]}')
    if form_data.get('username'):
        parts.append(f'Username: {form_data["username"]}')
    if form_data.get('page_url'):
        parts.append(f'Page: {form_data["page_url"]}')
    parts.append('')
    parts.append(form_data.get('description') or '')
    return '\n'.join(parts)


def create_feedback_task(
    access_token: str,
    project_gid: str,
    form_data: dict[str, Any],
    photo_path=None,
    photo_filename: Optional[str] = None,
    section_gid: Optional[str] = None,
    assignee_gid: Optional[str] = None,
) -> str:
    """Create an Asana task (and optional attachment). Returns task GID."""
    name = build_feedback_task_name(
        form_data.get('feedback_type') or 'comment',
        form_data.get('title') or '',
        form_data.get('description') or '',
    )
    notes = build_feedback_task_notes(form_data)
    task_data: dict[str, Any] = {
        'name': name,
        'notes': notes,
        'projects': [project_gid],
    }
    assignee = (assignee_gid or '').strip()
    if assignee:
        task_data['assignee'] = assignee
    section = (section_gid or '').strip()
    if section:
        task_data['memberships'] = [{'project': project_gid, 'section': section}]
    response = _api_json(
        'POST',
        '/tasks',
        access_token,
        {'data': task_data},
    )
    task_gid = (response.get('data') or {}).get('gid')
    if not task_gid:
        raise AsanaError('Asana did not return a task id.')
    if photo_path and photo_filename:
        _multipart_attach(access_token, task_gid, photo_path, photo_filename)
    return task_gid


def token_expires_at(expires_in: int) -> str:
    """UTC ISO timestamp when access token expires (with small buffer)."""
    when = datetime.utcnow() + timedelta(seconds=max(0, int(expires_in) - 120))
    return when.isoformat() + 'Z'


def connected_user_label(token_payload: dict[str, Any]) -> str:
    data = token_payload.get('data') or {}
    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip()
    if name and email:
        return f'{name} ({email})'
    return name or email or 'Connected'
