"""Flask request/response hooks, healthz, and error logging."""
from __future__ import annotations

import os
import traceback
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, redirect, request, session, url_for
from flask_login import current_user
from flask.signals import got_request_exception
from sqlalchemy import text

from admin_console_nav import (
    admin_nav_inject_block,
    build_staff_nav_items,
    is_staff_console_page,
)
from config import BASE_DIR
from services.feedback_ui import feedback_global_inject_markup
from services.help_ui import help_global_inject_markup
from services.nav_markup import (
    staff_console_dropdown_links_markup,
    user_mobile_bottom_nav_markup,
)
from services.staff_console import (
    STAFF_CONSOLE_HOME_KEY,
    STAFF_CONSOLE_QUERY_KEY,
    manager_new_hires_list_url,
    touch_staff_console_home,
)
from services.stores_scope import manager_has_permission
from services.theme import GLOBAL_METALLIC_THEME_CSS
from services.user_accounts import user_must_change_password


_HTTPS_HOSTS = frozenset({'ziebartonboarding.com', 'www.ziebartonboarding.com'})


def _request_is_https() -> bool:
    return (
        request.headers.get('X-Forwarded-Proto', '').lower() == 'https'
        or request.scheme == 'https'
        or request.is_secure
    )


def _log_exception_to_file(exc) -> None:
    try:
        log_path = BASE_DIR / 'logs' / 'error.log'
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(datetime.utcnow().isoformat() + ' EXCEPTION\n')
            f.write(''.join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
            f.write('\n')
    except Exception:
        pass


def register_app_hooks(app: Flask) -> None:
    """Attach security, injectors, auth gates, logging, and /healthz."""
    from models import db

    @app.before_request
    def configure_secure_cookies():
        is_https = _request_is_https()
        app.config['SESSION_COOKIE_SECURE'] = is_https
        app.config['PREFERRED_URL_SCHEME'] = 'https' if is_https else 'http'

    @app.before_request
    def force_https_for_production_hosts():
        if (
            os.getenv('FORCE_HTTPS', 'true').lower() == 'false'
            or request.path.startswith('/static')
            or request.path.startswith('/.well-known/acme-challenge')
        ):
            return
        host = (request.host or '').split(':')[0].lower()
        if host not in _HTTPS_HOSTS or _request_is_https():
            return
        target = request.url.replace('http://', 'https://', 1)
        return redirect(target, code=301)

    @app.after_request
    def add_hsts_for_production_hosts(response):
        host = (request.host or '').split(':')[0].lower()
        if host in _HTTPS_HOSTS and _request_is_https():
            response.headers.setdefault(
                'Strict-Transport-Security', 'max-age=31536000; includeSubDomains'
            )
        return response

    @app.before_request
    def apply_staff_console_from_query():
        try:
            if not current_user.is_authenticated:
                return
        except Exception:
            return
        sc = (request.args.get(STAFF_CONSOLE_QUERY_KEY) or '').strip().lower()
        if sc in ('admin', 'manager'):
            touch_staff_console_home(sc)

    @app.context_processor
    def inject_global_theme_css():
        from services.feedback_ui import _feedback_header_button_html
        return {
            'global_theme_css': GLOBAL_METALLIC_THEME_CSS,
            'user_mobile_bottom_nav': user_mobile_bottom_nav_markup(),
            'staff_console_dropdown_links': staff_console_dropdown_links_markup(),
            'feedback_header_button': _feedback_header_button_html(
                is_active=(request.endpoint == 'feedback')
            ),
        }

    @app.after_request
    def inject_feedback_header_button(response):
        try:
            if response.status_code != 200:
                return response
            content_type = response.content_type or ''
            if 'text/html' not in content_type:
                return response
            try:
                if not current_user.is_authenticated:
                    return response
            except Exception:
                return response
            data = response.get_data(as_text=True)
            if '</body>' not in data or 'app-feedback-header-btn' in data:
                return response
            snippet = str(feedback_global_inject_markup())
            response.set_data(data.replace('</body>', snippet + '</body>', 1))
        except Exception:
            pass
        return response

    @app.after_request
    def inject_help_header_button(response):
        try:
            if response.status_code != 200:
                return response
            content_type = response.content_type or ''
            if 'text/html' not in content_type:
                return response
            try:
                if not current_user.is_authenticated:
                    return response
            except Exception:
                return response
            data = response.get_data(as_text=True)
            if '</body>' not in data or 'app-help-header-btn' in data:
                return response
            snippet = str(help_global_inject_markup())
            response.set_data(data.replace('</body>', snippet + '</body>', 1))
        except Exception:
            pass
        return response

    @app.after_request
    def inject_admin_console_nav(response):
        try:
            if response.status_code != 200:
                return response
            content_type = response.content_type or ''
            if 'text/html' not in content_type:
                return response
            try:
                if not current_user.is_authenticated:
                    return response
                if not current_user.is_admin() and not current_user.is_manager():
                    return response
            except Exception:
                return response
            endpoint = request.endpoint
            if not is_staff_console_page(endpoint):
                return response
            data = response.get_data(as_text=True)
            if '</body>' not in data or 'adminNavSidebar' in data:
                return response
            sc = (
                request.args.get(STAFF_CONSOLE_QUERY_KEY)
                or session.get(STAFF_CONSOLE_HOME_KEY)
                or ''
            ).strip().lower()
            if sc not in ('admin', 'manager'):
                sc = 'admin' if current_user.is_admin() else 'manager'
            if endpoint == 'manager_dashboard':
                sc = 'manager'
            items = build_staff_nav_items(
                is_admin=current_user.is_admin(),
                has_permission=manager_has_permission,
                staff_console=sc,
                manager_new_hires_url=manager_new_hires_list_url(),
            )
            if not items:
                return response
            menu_title = 'Manager menu' if sc == 'manager' else 'Admin menu'
            snippet = str(admin_nav_inject_block(items, endpoint, menu_title=menu_title))
            response.set_data(data.replace('</body>', snippet + '</body>', 1))
        except Exception:
            pass
        return response

    def _on_request_exception(sender, exception, **kwargs):
        _log_exception_to_file(exception)

    got_request_exception.connect(_on_request_exception, app)

    @app.errorhandler(500)
    def internal_error(e):
        if getattr(e, 'original_exception', None):
            _log_exception_to_file(e.original_exception)
        return 'Internal Server Error', 500

    @app.before_request
    def _force_password_change_if_required():
        if request.path.startswith('/static'):
            return
        try:
            if not current_user.is_authenticated:
                return
            if request.endpoint in ('change_password', 'logout', 'login'):
                return
            if user_must_change_password(current_user.username):
                return redirect(url_for('change_password'))
        except Exception:
            pass

    @app.before_request
    def check_authentication():
        if request.path.startswith('/static'):
            return
        if request.path in (
            '/login', '/logout', '/', '/healthz',
            '/favicon.ico', '/uploads/ziebart.svg',
            '/forgot-password',
        ):
            return
        if request.path.startswith('/reset-password/'):
            return
        if not current_user.is_authenticated:
            from services.security import relative_request_path
            return redirect(url_for('login', next=relative_request_path()))

    @app.before_request
    def rate_limit_auth_posts():
        if request.method != 'POST':
            return
        path = request.path or ''
        if path not in ('/login', '/change-password', '/forgot-password') and not path.startswith('/reset-password/'):
            return
        from services.rate_limit import too_many_requests
        forwarded = (request.headers.get('X-Forwarded-For') or '').split(',')[0].strip()
        ip = forwarded or (request.remote_addr or 'unknown')
        # Forgot-password is stricter to limit email spam / token farming
        limit = 5 if path == '/forgot-password' else 10
        key = f'auth:{ip}:{path if path != "/forgot-password" else "forgot-password"}'
        if too_many_requests(key, limit=limit, window_seconds=60):
            return (
                'Too many requests. Please wait a minute and try again.',
                429,
            )

    @app.before_request
    def _assign_request_id():
        request.request_id = request.headers.get('X-Request-Id') or uuid.uuid4().hex[:12]

    @app.after_request
    def _log_request_summary(response):
        try:
            rid = getattr(request, 'request_id', '-')
            uname = ''
            try:
                if current_user.is_authenticated:
                    uname = current_user.username
            except Exception:
                pass
            app.logger.info(
                'request_id=%s method=%s path=%s status=%s user=%s',
                rid, request.method, request.path, response.status_code, uname or '-',
            )
            response.headers['X-Request-Id'] = rid
        except Exception:
            pass
        return response

    @app.route('/healthz')
    def healthz():
        checks = {'app': 'ok', 'db': 'unknown', 'uploads': 'unknown'}
        status = 200
        try:
            db.session.execute(text('SELECT 1'))
            checks['db'] = 'ok'
        except Exception as exc:
            checks['db'] = f'error:{exc.__class__.__name__}'
            status = 503
        try:
            upload = Path(app.config.get('UPLOAD_FOLDER', BASE_DIR / 'uploads'))
            upload.mkdir(parents=True, exist_ok=True)
            probe = upload / '.healthz'
            probe.write_text('ok', encoding='utf-8')
            probe.unlink(missing_ok=True)
            checks['uploads'] = 'ok'
        except Exception as exc:
            checks['uploads'] = f'error:{exc.__class__.__name__}'
            status = 503
        return jsonify(checks), status


__all__ = [
    'register_app_hooks',
    '_request_is_https',
    '_HTTPS_HOSTS',
    '_log_exception_to_file',
]
