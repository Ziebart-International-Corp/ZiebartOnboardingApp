"""
Onboarding App - Main Flask Application
Email + password login with Admin and User roles
"""
import os
from pathlib import Path

# Load .env before any config that uses it (this app's folder only)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / '.env', override=True)
except ImportError:
    pass

# macOS system Python often lacks hashlib.scrypt (LibreSSL); polyfill before Werkzeug auth.
from services.hashlib_scrypt import ensure_scrypt
ensure_scrypt()

from flask import Flask, render_template, render_template_string, redirect, url_for, request, session, flash, jsonify, send_file, send_from_directory, make_response, abort
from document_wizard import (
    DOCUMENT_WIZARD_MIN_FIELDS,
    apply_wizard_field_skip,
    build_wizard_fields_for_document,
    document_uses_step_wizard,
    document_wizard_eligible,
    first_incomplete_required_wizard_index,
    first_incomplete_wizard_index,
    wizard_progress_counts,
    wizard_required_steps_complete,
)
from pdf_form_wizard import (
    ACRO_PLACEHOLDER_PREFIX,
    FITZ_AVAILABLE as PDF_WIZARD_FITZ_AVAILABLE,
    TEST_FORM_SIG_PREFIX,
    acro_value_for_widget,
    analyze_pdf,
    build_filled_pdf,
    collect_acroform_import_specs as _collect_acroform_import_specs_uncached,
    count_pdf_acroform_widgets as _count_pdf_acroform_widgets_uncached,
    delete_wizard_state,
    embed_signatures_in_pdf,
    embed_typed_field_values_in_pdf,
    embed_employment_overlay_values,
    flatten_pdf_form_widgets,
    rasterize_pdf_pages,
    save_pdf_document_copy,
    extract_fields_from_layout,
    is_test_form_signature_value,
    load_wizard_state,
    new_session_id,
    normalize_test_form_signature_value,
    save_uploaded_pdf,
    save_wizard_state,
    test_form_signature_b64,
)

from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from sqlalchemy import exists, or_, and_, text, bindparam, func, select
from auth import login_required, admin_required, manager_required, User, check_user_can_login_as_admin, authenticate_by_email_password
from admin_console_nav import (
    admin_nav_inject_block,
    build_staff_nav_items,
    is_staff_console_page,
)
from models import (db, NewHire, User as UserModel, Document, ChecklistItem, NewHireChecklist,
                    TrainingVideo, QuizQuestion, QuizAnswer, UserTrainingProgress, UserQuizResponse, UserTask,
                    DocumentSignatureField, DocumentSignature, DocumentTypedField, DocumentTypedFieldValue, DocumentAssignment, UserNotification, ExternalLink, Role, AdminSetting, Store, Department, ManagerPermission, SignatureAuditLog, document_stores, role_documents, new_hire_required_training, training_video_stores)
from membership import get_token_groups, get_local_groups
from config import SECRET_KEY, SQLALCHEMY_DATABASE_URI, SQLALCHEMY_ENGINE_OPTIONS, BASE_DIR, ASANA_ACCESS_TOKEN, ASANA_CLIENT_ID, ASANA_CLIENT_SECRET, ASANA_REFRESH_TOKEN, ASANA_REDIRECT_URI, ASANA_FEEDBACK_PROJECT_GID, ASANA_FEEDBACK_SECTION_GIDS, ASANA_SECTION_GID_COMMENT, ASANA_SECTION_GID_ISSUE, ASANA_SECTION_GID_SUGGESTION, ASANA_FEEDBACK_ASSIGNEE_GID
from datetime import datetime
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.security import generate_password_hash, check_password_hash
from markupsafe import Markup, escape
from urllib.parse import unquote
from io import BytesIO
import base64
import re
import secrets
import string
from asana_feedback import (
    AsanaError,
    build_authorization_url,
    connected_user_label,
    create_feedback_task,
    exchange_authorization_code,
    generate_pkce_pair,
    refresh_access_token,
    token_expires_at,
)
try:
    from graphql_schema import schema as graphql_schema
except ImportError:
    graphql_schema = None
try:
    from pdf2image import convert_from_path
    PDF2IMAGE_AVAILABLE = True
except (ImportError, Exception):
    PDF2IMAGE_AVAILABLE = False

try:
    import fitz  # PyMuPDF
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False

try:
    from pyhanko.sign import signers, fields
    from pyhanko.sign.timestamps import HTTPTimeStamper
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa, padding
    from cryptography.hazmat.backends import default_backend
    import hashlib
    PYHANKO_AVAILABLE = True
except ImportError:
    PYHANKO_AVAILABLE = False

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = SQLALCHEMY_ENGINE_OPTIONS
app.config['UPLOAD_FOLDER'] = BASE_DIR / 'uploads'
app.config['VIDEO_UPLOAD_FOLDER'] = BASE_DIR / 'uploads' / 'videos'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # hard ceiling (videos); docs use MAX_DOCUMENT_UPLOAD_MB
from config import MAX_DOCUMENT_UPLOAD_MB, ENABLE_TEST_FORM_WIZARD, PROXY_FIX
app.config['MAX_DOCUMENT_UPLOAD_MB'] = MAX_DOCUMENT_UPLOAD_MB
app.config['ENABLE_TEST_FORM_WIZARD'] = ENABLE_TEST_FORM_WIZARD
app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt', 'jpg', 'jpeg', 'png', 'gif', 'svg'}
app.config['ALLOWED_VIDEO_EXTENSIONS'] = {'mp4', 'webm', 'ogg', 'mov', 'avi'}
app.config['FEEDBACK_UPLOAD_FOLDER'] = BASE_DIR / 'uploads' / 'feedback'
app.config['FEEDBACK_ALLOWED_IMAGE_EXTENSIONS'] = {'jpg', 'jpeg', 'png', 'gif', 'webp'}

if PROXY_FIX:
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
FEEDBACK_TYPES = (
    ('comment', 'General comment'),
    ('issue', 'Report an issue'),
    ('suggestion', 'Suggest an improvement'),
)

# HTTPS/Security Configuration
# Enable secure cookies when HTTPS is available (detected via request headers)
# IIS passes X-Forwarded-Proto header when HTTPS is enabled
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 hour

DEFAULT_WELCOME_HEADLINE = 'Welcome to Ziebart International Corporation! Congratulations on your new role!'
DEFAULT_WELCOME_BODY = (
    'We are honored to have you join the team and are committed to supporting your success from day one.'
)
DEFAULT_FINALE_MESSAGE = (
    'Congratulations on completing all of your onboarding tasks! '
    'Your team appreciates your effort getting through everything. '
    'If you have any questions, reach out to your manager.'
)
DEFAULT_ALL_TASKS_EMAIL_SUBJECT = 'Congratulations — you completed all onboarding tasks'
DEFAULT_ALL_TASKS_EMAIL_BODY = (
    'Hello,\n\n'
    'Congratulations! You have completed all of your assigned onboarding tasks, '
    'including any required training.\n\n'
    'You can sign in anytime to review your work or any messages from your team:\n'
    '[link:portal:dashboard|Go to your dashboard]\n\n'
    'Thank you,\n'
    'Onboarding Team'
)

ONBOARDING_LINK_TOKEN_RE = __import__('re').compile(
    r'\[link:([^:\]|]+):([^|\]]+)\|([^\]]+)\]'
)

ONBOARDING_PORTAL_PAGES = [
    ('dashboard', 'Dashboard'),
    ('tasks', 'Tasks'),
    ('documents', 'Documents'),
    ('videos', 'Videos'),
    ('profile', 'Profile'),
    ('login', 'Login'),
]

PORTAL_PAGE_ENDPOINTS = {
    'dashboard': 'dashboard',
    'tasks': 'user_tasks',
    'documents': 'view_documents',
    'videos': 'list_training_videos',
    'profile': 'profile',
}

# --- Mail + extensions bootstrap ---
from services.mail import (
    _get_mail_server, _get_mail_user, _get_mail_password,
    send_email, _html_to_plain_fallback, generate_temporary_password,
    send_password_reset_email, send_onboarding_welcome_email, send_email_with_attachment,
)
try:
    from flask_mail import Mail, Message
    app.config['MAIL_SERVER'] = _get_mail_server()
    app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT') or os.getenv('EMAIL_PORT', '587'))
    app.config['MAIL_USE_TLS'] = (os.getenv('MAIL_USE_TLS') or os.getenv('EMAIL_USE_SSL', 'true')).lower() == 'true'
    app.config['MAIL_USE_SSL'] = (os.getenv('MAIL_USE_SSL') or 'false').lower() == 'true'
    app.config['MAIL_USERNAME'] = _get_mail_user()
    app.config['MAIL_PASSWORD'] = _get_mail_password()
    app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER') or _get_mail_user()
    mail = Mail(app)
    _socketlabs_user = os.getenv('SOCKETLABS_USERNAME', '')
    _socketlabs_pwd = os.getenv('SOCKETLABS_PASSWORD', '')
    MAIL_AVAILABLE = bool(
        (app.config['MAIL_USERNAME'] and app.config['MAIL_PASSWORD']) or
        (_socketlabs_user and _socketlabs_pwd)
    )
except Exception:
    mail = None
    MAIL_AVAILABLE = False

# Initialize extensions
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

from services.mail import bind_mail
bind_mail(mail, MAIL_AVAILABLE)

from db.migrations_runtime import (
    _ensure_users_access_revoked_at_column, _ensure_users_role_column,
    _ensure_users_domain_column, _ensure_users_last_login_column,
    _ensure_users_must_change_password_column, _ensure_users_saved_signature_columns,
    _ensure_document_signatures_savedflag_column, _ensure_signature_audit_logs_table,
    _ensure_new_hires_finale_columns, _ensure_admin_settings_table,
    _ensure_stores_and_store_id, _ensure_departments_table,
    _ensure_document_typed_field_columns, _ensure_user_task_order_columns,
    _ensure_help_tables, _ensure_password_reset_schema, _run_users_migration_if_needed,
)


@login_manager.user_loader
def load_user(user_id):
    """Load user from session (user_id is username)."""
    try:
        user_record = UserModel.query.filter_by(username=user_id).first()
    except Exception:
        db.session.rollback()
        _ensure_users_access_revoked_at_column()
        _ensure_users_role_column()
        _ensure_users_domain_column()
        _ensure_users_last_login_column()
        _ensure_users_saved_signature_columns()
        try:
            user_record = UserModel.query.filter_by(username=user_id).first()
        except Exception:
            return None
    if not user_record:
        return None
    return User(
        user_record.username,
        getattr(user_record, 'domain', None),
        getattr(user_record, 'role', None) or 'user'
    )


# --- Re-exports from services/db (blueprint-compatible names on app module) ---
from services.stores_scope import (
    get_current_user_store_id, documents_visible_to_store_query,
    documents_assignable_to_store_query, _document_has_assignable_fields_filter,
    _stores_for_document, _attach_document_store_lists, document_visible_to_store,
    training_videos_visible_to_store_query, _stores_for_training_video,
    _attach_training_video_store_lists, training_video_visible_to_store,
    training_videos_for_store_detail, documents_for_user_files, manager_has_permission,
    MANAGER_PERMISSION_KEYS,
)
from services.wizard import (
    _document_wizard_index_key, _document_wizard_has_dependents_key,
    _document_wizard_overlay_key, _document_wizard_emp_parts_key,
    _document_wizard_emp_acks_key, _user_can_fill_document,
    _document_wizard_user_defaults, _load_document_wizard_steps,
    _wizard_persist_typed, _persist_typed_field_for_user,
    _persist_signature_for_user, _finalize_document_completion,
)
from services.documents_pdf import (
    _signed_pdf_download_filename, _typed_signature_text_for_document,
    _completed_document_cards_for_user, _send_built_user_pdf,
    _document_is_fillable_pdf, _document_pdf_path, resolve_document_file_path,
    _pdf_field_name_from_placeholder, _render_completed_pdf_viewer,
    _render_completed_pdf_print_page, embed_signature_in_pdf, calculate_pdf_hash,
    sign_pdf_cryptographically, _build_signed_pdf_copy_for_user,
    _persist_signed_pdf_copy, _create_signature_audit_log,
)
from services.asana_app import (
    _asana_redirect_uri, _asana_oauth_configured, _asana_env_token_configured,
    _asana_feedback_ready, _asana_store_tokens, _asana_get_access_token,
    _asana_is_connected, _asana_clear_tokens, _create_asana_feedback_task,
    _save_feedback_submission,
)



# --- Additional service re-exports ---
from services.staff_console import (
    touch_staff_console_home, staff_console_home_url, uses_manager_new_hires_home, uses_manager_console_scope,
    document_manage_requires_store_scope, staff_store_scope_id, is_pure_manager, can_assign_extra_tasks,
    assign_task_link_context, assign_task_url, new_hire_details_link_context, view_new_hire_details_url,
    new_hire_details_back_url, redirect_new_hire_details, build_user_display_and_store_maps, manager_new_hires_list_url,
    staff_header_display_name, _access_revoke_calendar_date, _staff_can_view_user_documents, _staff_new_hire_details_url,
    _assign_task_redirect, _manager_can_act_on_new_hire,
)
from services.document_urls import (
    _document_configured_field_count, user_sign_document_url, user_document_wizard_url, user_sign_document_classic_url,
    user_document_completed_print_url, user_document_completed_view_url, onboarding_base_url, onboarding_tasks_url,
    onboarding_login_url,
)
from services.onboarding_messages import (
    get_admin_setting, set_admin_setting, apply_message_template, onboarding_portal_page_url,
    resolve_onboarding_link_href, normalize_legacy_onboarding_message, _escape_message_text_with_breaks, render_onboarding_message_html,
    render_onboarding_message_plain, build_welcome_headline, get_welcome_messages, maybe_apply_default_finale_message,
)
from services.document_fields import (
    normalize_last4_typed_value, typed_field_is_phone_like, _field_is_phone_like, _import_acroform_fields_for_document,
    _try_auto_import_acroform_fields, clear_choice_group_selections_except, normalize_typed_field_type, validate_typed_field_value,
    is_signature_field_signed, is_typed_field_filled, document_fully_completed_for_user, _mark_document_assignment_complete_if_ready,
)
from services.user_tasks import (
    get_visible_ordered_user_tasks, training_video_id_from_task, training_video_ids_from_user_tasks, attach_training_video_ids_to_tasks,
    dashboard_onboarding_work, user_onboarding_is_fully_complete, maybe_send_all_tasks_completed_email, reset_onboarding_completion_state,
    clear_all_tasks_completed_email_sent,
)
from services.document_admin import (
    _delete_user_tasks_for_document, _orphaned_document_user_tasks_query, count_orphaned_document_user_tasks, cleanup_orphaned_document_user_tasks,
    _signature_fields_redirect, _drop_field_editor_noise_flashes, _purge_training_video_dependencies,
)
from services.uploads_allowed import (
    allowed_file, allowed_video_file,
)

app.template_global()(is_pure_manager)
app.template_global()(manager_new_hires_list_url)
app.template_global()(staff_console_home_url)
app.template_global()(staff_store_scope_id)
app.template_global()(view_new_hire_details_url)
app.template_global()(new_hire_details_back_url)
app.template_global()(assign_task_url)
app.template_global()(user_sign_document_url)
app.template_global()(user_document_wizard_url)
app.template_global()(user_sign_document_classic_url)
app.template_global()(user_document_completed_view_url)
app.template_global()(user_document_completed_print_url)


from services.document_fields import (
    TYPED_FIELD_PHONE_REGEX, TYPED_FIELD_PHONE_PATTERN_HTML, TYPED_FIELD_PHONE_REGEX_JS,
    TYPED_FIELD_LAST4_PREFIX, TYPED_FIELD_LAST4_REGEX, TYPED_FIELD_LAST4_REGEX_JS,
    ALLOWED_TYPED_FIELD_TYPES, TYPED_FIELD_TYPE_CHOICES, FIELD_EDITOR_TYPE_CHOICES,
)
from services.staff_console import STAFF_CONSOLE_HOME_KEY, STAFF_CONSOLE_QUERY_KEY


# --- Wave-2 service re-exports ---
from services.feedback_ui import (
    _feedback_header_button_html, feedback_global_inject_markup,
    _feedback_allowed_image, _feedback_user_display_context,
)
from services.user_accounts import (
    get_email_for_username, normalize_email, email_in_use_by_other_user,
    user_must_change_password, update_last_login, resolve_department_from_form,
)
from services.domain_groups import (
    get_user_domain_groups_via_netapi, get_user_domain_groups_via_ldap, get_user_domain_groups,
)
from services.test_form import (
    _test_form_wizard_state, _test_form_wizard_save, _test_form_field_is_last4,
    _test_form_last4_digits, _refresh_test_form_field_positions,
)
from services.pdf_acroform_cache import (
    _pdf_cache_key, collect_acroform_import_specs, count_pdf_acroform_widgets,
)
from services.nav_markup import (
    user_mobile_bottom_nav_markup, staff_console_dropdown_links_markup,
)


# Re-bind markup helpers as Jinja globals / after_request (moved implementations)
app.template_global()(user_mobile_bottom_nav_markup)
app.template_global()(staff_console_dropdown_links_markup)

from services.theme import GLOBAL_METALLIC_THEME_CSS
from services.app_hooks import (
    register_app_hooks, _request_is_https, _HTTPS_HOSTS, _log_exception_to_file,
)
from blueprints import register_blueprints
from blueprints import static_files as static_files_bp
from services.csrf_protect import init_csrf
static_files_bp.register(app)
init_csrf(app)
register_app_hooks(app)
register_blueprints(app)

try:
    from services.jobs import ensure_jobs_table, start_worker, recover_stuck_jobs
    with app.app_context():
        _run_users_migration_if_needed()
except Exception:
    app.logger.exception('startup schema migration failed')
    if os.getenv('SKIP_STARTUP_MIGRATIONS', '').lower() not in ('1', 'true', 'yes'):
        raise
    app.logger.warning('Continuing without migrations (SKIP_STARTUP_MIGRATIONS set)')

try:
    from services.jobs import ensure_jobs_table, start_worker, recover_stuck_jobs
    with app.app_context():
        ensure_jobs_table()
        recover_stuck_jobs()
    start_worker(app)
except Exception:
    app.logger.exception('background job worker failed to start')
    if os.getenv('SKIP_STARTUP_MIGRATIONS', '').lower() not in ('1', 'true', 'yes'):
        pass  # worker is optional; migrations already handled above

application = app

if __name__ == '__main__':
    # Local development only — never run with debug in production
    _debug = os.getenv('FLASK_DEBUG', 'false').lower() in ('1', 'true', 'yes')
    app.run(debug=_debug, host='0.0.0.0', port=5000)
