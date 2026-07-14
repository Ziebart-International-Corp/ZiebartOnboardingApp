"""Welcome/finale message templates and onboarding link rendering."""
from __future__ import annotations

from markupsafe import Markup, escape

from flask import url_for
from sqlalchemy import text

from models import NewHire, db
from db.migrations_runtime import _ensure_admin_settings_table, _ensure_new_hires_finale_columns


def _app():
    import app as main
    return main


def onboarding_base_url():
    return _app().onboarding_base_url()

def get_admin_setting(key, default=''):
    """Read a value from admin_settings (returns default if missing)."""
    _ensure_admin_settings_table()
    try:
        row = db.session.execute(
            text('SELECT value FROM admin_settings WHERE [key] = :k'),
            {'k': key},
        ).fetchone()
        if row is not None and row[0] is not None:
            return str(row[0])
    except Exception:
        db.session.rollback()
    return default

def set_admin_setting(key, value):
    """Upsert a value in admin_settings."""
    _ensure_admin_settings_table()
    value = '' if value is None else str(value)
    existing = db.session.execute(
        text('SELECT [key] FROM admin_settings WHERE [key] = :k'),
        {'k': key},
    ).fetchone()
    if existing:
        db.session.execute(
            text('UPDATE admin_settings SET value = :v WHERE [key] = :k'),
            {'v': value, 'k': key},
        )
    else:
        db.session.execute(
            text('INSERT INTO admin_settings ([key], value) VALUES (:k, :v)'),
            {'k': key, 'v': value},
        )

def apply_message_template(template, **replacements):
    """Replace {placeholder} tokens in a message template."""
    result = template or ''
    for key, val in replacements.items():
        result = result.replace('{' + key + '}', str(val if val is not None else ''))
    return result

def onboarding_portal_page_url(page_key, external=False):
    """Resolve a portal page key to a URL (relative in-app or absolute for email)."""
    if page_key == 'login':
        return onboarding_login_url()
    endpoint = _app().PORTAL_PAGE_ENDPOINTS.get(page_key)
    if not endpoint:
        path = '/dashboard'
        return (onboarding_base_url() + path) if external else url_for('dashboard')
    if external:
        return url_for(endpoint, _external=True)
    return url_for(endpoint)

def resolve_onboarding_link_href(link_type, link_key):
    """Return href for a stored link token, or None if invalid."""
    link_type = (link_type or '').lower()
    if link_type == 'portal':
        return onboarding_portal_page_url(link_key, external=True)
    if link_type == 'external':
        try:
            link = ExternalLink.query.get(int(link_key))
            if link and link.url:
                return link.url
        except (TypeError, ValueError):
            pass
        return None
    if link_type == 'custom':
        url = unquote(link_key or '')
        if url.lower().startswith(('http://', 'https://')):
            return url
        return None
    return None

def normalize_legacy_onboarding_message(text):
    """Convert old {dashboard_link} placeholders to link tokens for editing/display."""
    if not text:
        return ''
    return text.replace('{dashboard_link}', '[link:portal:dashboard|Go to your dashboard]')

def _escape_message_text_with_breaks(text):
    return Markup(escape(text or '').replace('\n', '<br>'))

def render_onboarding_message_html(text, for_email=False):
    """Turn stored message text (with link tokens) into safe HTML."""
    text = normalize_legacy_onboarding_message(text or '')
    parts = []
    last = 0
    for match in _app().ONBOARDING_LINK_TOKEN_RE.finditer(text):
        if match.start() > last:
            parts.append(_escape_message_text_with_breaks(text[last:match.start()]))
        link_type, link_key, label = match.group(1), match.group(2), match.group(3)
        if link_type == 'portal' and not for_email:
            try:
                href = onboarding_portal_page_url(link_key, external=False)
            except RuntimeError:
                href = onboarding_portal_page_url(link_key, external=True)
        else:
            href = resolve_onboarding_link_href(link_type, link_key)
        if href:
            parts.append(Markup(f'<a href="{escape(href)}">{escape(label)}</a>'))
        else:
            parts.append(escape(label))
        last = match.end()
    if last < len(text):
        parts.append(_escape_message_text_with_breaks(text[last:]))
    return Markup(''.join(str(part) for part in parts))

def render_onboarding_message_plain(text):
    """Plain-text version of a message (for email text alternative)."""
    text = normalize_legacy_onboarding_message(text or '')

    def _repl(match):
        link_type, link_key, label = match.group(1), match.group(2), match.group(3)
        href = resolve_onboarding_link_href(link_type, link_key)
        if link_type == 'portal' and href:
            href = onboarding_portal_page_url(link_key, external=True)
        if href:
            return f'{label} ({href})'
        return label

    return _app().ONBOARDING_LINK_TOKEN_RE.sub(_repl, text)

def build_welcome_headline(headline, full_name, include_name):
    """Build welcome headline; optionally insert the employee name before the first !."""
    headline = (headline or '').replace('{name}', '').strip()
    if include_name and full_name:
        if '!' in headline:
            idx = headline.index('!')
            return headline[:idx] + f', {full_name}' + headline[idx:]
        return f'{headline}, {full_name}'
    return headline

def get_welcome_messages(full_name=''):
    """Headline and body for the post-login welcome screen."""
    headline_tpl = get_admin_setting('welcome_headline', _app().DEFAULT_WELCOME_HEADLINE)
    body = get_admin_setting('welcome_body', _app().DEFAULT_WELCOME_BODY)
    include_name = get_admin_setting('welcome_include_name', '1') == '1'
    if '{name}' in headline_tpl:
        include_name = True
        headline_tpl = headline_tpl.replace('{name}', '')
    headline = build_welcome_headline(headline_tpl, full_name, include_name)
    return headline, body

def maybe_apply_default_finale_message(username):
    """When onboarding is complete, apply the configured default finale message once."""
    from datetime import datetime
    from services.user_tasks import user_onboarding_is_fully_complete

    _ensure_new_hires_finale_columns()
    if not user_onboarding_is_fully_complete(username):
        return False
    new_hire = NewHire.query.filter_by(username=username).first()
    if not new_hire:
        return False
    if getattr(new_hire, 'finale_message_sent_at', None):
        return False
    message = get_admin_setting('default_finale_message', _app().DEFAULT_FINALE_MESSAGE).strip()
    if not message:
        return False
    doc_id_raw = get_admin_setting('default_finale_document_id', '').strip()
    new_hire.finale_message = message
    new_hire.finale_message_sent_at = datetime.utcnow()
    new_hire.finale_document_id = int(doc_id_raw) if doc_id_raw.isdigit() else None
    new_hire.finale_message_dismissed_at = None
    try:
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        return False


_stores_migrated = False

