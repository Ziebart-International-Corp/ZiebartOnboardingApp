"""
Configuration settings for the New Hire Application
"""
import os
from pathlib import Path

# Load .env from project root so DB_* and other vars are available (e.g. under IIS).
# override=True so .env always wins over IIS/process environment (e.g. DB_NAME).
_config_dir = Path(__file__).resolve().parent
_env_path = _config_dir / '.env'
try:
    from dotenv import load_dotenv
    load_dotenv(_env_path, override=True)
except ImportError:
    pass

# Force DB_* from .env file so IIS/env never overrides (read file directly for DB_NAME)
def _env_value(key: str, default: str = '') -> str:
    try:
        if _env_path.exists():
            with open(_env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if '=' in line and line.split('=', 1)[0].strip() == key:
                        return line.split('=', 1)[1].strip().strip('"').strip("'") or default
    except Exception:
        pass
    return os.environ.get(key, default)

# Base directory
BASE_DIR = _config_dir

# Secret key for sessions — must be unique in production (reject known default).
_DEFAULT_SECRET_KEY = 'dev-secret-key-change-in-production'
SECRET_KEY = (_env_value('SECRET_KEY') or os.environ.get('SECRET_KEY', '') or '').strip()
_allow_insecure_secret = (
    os.environ.get('ALLOW_INSECURE_SECRET_KEY', '').strip().lower() in ('1', 'true', 'yes')
)
if not SECRET_KEY or SECRET_KEY == _DEFAULT_SECRET_KEY:
    if _allow_insecure_secret:
        SECRET_KEY = SECRET_KEY or _DEFAULT_SECRET_KEY
        import warnings
        warnings.warn(
            'SECRET_KEY is missing or set to the insecure default. '
            'Set a unique SECRET_KEY in .env for production.',
            RuntimeWarning,
            stacklevel=1,
        )
    else:
        raise RuntimeError(
            'SECRET_KEY must be set to a unique non-default value in .env '
            '(or set ALLOW_INSECURE_SECRET_KEY=1 for local development only).'
        )

# Windows Domain Configuration
DOMAIN_NAME = os.environ.get('DOMAIN_NAME', 'YOURDOMAIN')  # e.g., 'CONTOSO'
DOMAIN_CONTROLLER = os.environ.get('DOMAIN_CONTROLLER', None)  # Optional: specific DC
LDAP_BASE_DN = os.environ.get('LDAP_BASE_DN', None)  # Optional: e.g., 'DC=contoso,DC=com'

# Email Configuration (read from .env file first so IIS env cannot override)
EMAIL_DOMAIN = os.environ.get('EMAIL_DOMAIN', 'ziebart.com')  # Email domain for default email addresses
MAIL_SERVER = _env_value('MAIL_SERVER') or os.environ.get('MAIL_SERVER', '')
MAIL_PORT = int(_env_value('MAIL_PORT') or os.environ.get('MAIL_PORT', '587') or 587)
MAIL_USE_TLS = (_env_value('MAIL_USE_TLS') or os.environ.get('MAIL_USE_TLS', 'true')).lower() == 'true'
MAIL_USE_SSL = (_env_value('MAIL_USE_SSL') or os.environ.get('MAIL_USE_SSL', 'false')).lower() == 'true'
MAIL_USERNAME = _env_value('MAIL_USERNAME') or os.environ.get('MAIL_USERNAME', '')
MAIL_PASSWORD = _env_value('MAIL_PASSWORD') or os.environ.get('MAIL_PASSWORD', '')
MAIL_DEFAULT_SENDER = _env_value('MAIL_DEFAULT_SENDER') or os.environ.get('MAIL_DEFAULT_SENDER', '')

# Admin Configuration
# Option 1: List of admin usernames (without domain)
ADMIN_USERS = os.environ.get('ADMIN_USERS', '').split(',') if os.environ.get('ADMIN_USERS') else []
# Option 2: AD Group for admins (if using LDAP)
ADMIN_GROUP = os.environ.get('ADMIN_GROUP', 'Domain Admins')  # AD group name

# Authentication Method
# 'windows' - Use IIS Windows Authentication headers
# 'ldap' - Use LDAP/AD queries (requires domain controller access)
AUTH_METHOD = os.environ.get('AUTH_METHOD', 'windows')

# Database (SQL Server) — read from .env file first so IIS/env cannot override
DB_SERVER = _env_value('DB_SERVER') or os.environ.get('DB_SERVER', '')
DB_PORT = _env_value('DB_PORT') or os.environ.get('DB_PORT', '42278') or '42278'
DB_NAME = _env_value('DB_NAME') or os.environ.get('DB_NAME', '')
DB_USER = _env_value('DB_USER') or os.environ.get('DB_USER', '')
DB_PASSWORD = _env_value('DB_PASSWORD') or os.environ.get('DB_PASSWORD', '')
DB_MAX_POOL_SIZE = _env_value('DB_MAX_POOL_SIZE') or os.environ.get('DB_MAX_POOL_SIZE', '300')

# SQLAlchemy connection string — SQL Server only (Neon/Postgres DATABASE_URL is ignored)
from urllib.parse import quote_plus
DB_PASSWORD_ENCODED = quote_plus(DB_PASSWORD)
_DB_DRIVER = (
    _env_value('DB_DRIVER') or os.environ.get('DB_DRIVER', '') or ''
).strip().lower()
# On macOS local dev, prefer pymssql when requested (ODBC Driver 17 is Windows/IIS default).
if not _DB_DRIVER and __import__('sys').platform == 'darwin':
    try:
        import pymssql  # noqa: F401
        _DB_DRIVER = 'pymssql'
    except ImportError:
        _DB_DRIVER = 'odbc'
if _DB_DRIVER == 'pymssql':
    SQLALCHEMY_DATABASE_URI = (
        f'mssql+pymssql://{DB_USER}:{DB_PASSWORD_ENCODED}@{DB_SERVER}:{DB_PORT}/{DB_NAME}'
    )
else:
    _odbc_driver = (
        _env_value('ODBC_DRIVER')
        or os.environ.get('ODBC_DRIVER', '')
        or 'ODBC Driver 17 for SQL Server'
    ).strip()
    _DB_TRUST = (
        _env_value('DB_TRUST_SERVER_CERTIFICATE')
        or os.environ.get('DB_TRUST_SERVER_CERTIFICATE', 'yes')
        or 'yes'
    ).strip().lower()
    if _DB_TRUST in ('1', 'true', 'yes'):
        _DB_TRUST_PARAM = 'yes'
    elif _DB_TRUST in ('0', 'false', 'no'):
        _DB_TRUST_PARAM = 'no'
    else:
        _DB_TRUST_PARAM = 'yes'
    from urllib.parse import quote_plus as _qp
    _odbc_driver_q = _qp(_odbc_driver)
    SQLALCHEMY_DATABASE_URI = (
        f'mssql+pyodbc://{DB_USER}:{DB_PASSWORD_ENCODED}@{DB_SERVER}:{DB_PORT}/{DB_NAME}'
        f'?driver={_odbc_driver_q}&TrustServerCertificate={_DB_TRUST_PARAM}&Encrypt=yes'
    )
SQLALCHEMY_TRACK_MODIFICATIONS = False
SQLALCHEMY_ENGINE_OPTIONS = {
    'pool_size': int(DB_MAX_POOL_SIZE),
    'max_overflow': 0,
    'pool_pre_ping': True,  # Verify connections before using
    'pool_recycle': 3600,   # Recycle connections after 1 hour
}

# Session Configuration
# SESSION_COOKIE_SECURE will be set dynamically based on request scheme
# When HTTPS is enabled, set this to True in app.py after checking request
SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
PERMANENT_SESSION_LIFETIME = 3600  # 1 hour

# HTTPS/Proxy Configuration
# When behind IIS with HTTPS, Flask needs to trust proxy headers (default on for IIS)
PREFERRED_URL_SCHEME = os.environ.get('PREFERRED_URL_SCHEME', 'http')  # Change to 'https' when HTTPS is enabled
PROXY_FIX = os.environ.get('PROXY_FIX', 'True').lower() == 'true'

# Feature flags
ENABLE_TEST_FORM_WIZARD = os.environ.get('ENABLE_TEST_FORM_WIZARD', 'false').lower() in (
    '1', 'true', 'yes',
)
MAX_DOCUMENT_UPLOAD_MB = int(os.environ.get('MAX_DOCUMENT_UPLOAD_MB', '40') or 40)

# IIS Windows Authentication Headers
# IIS passes authenticated user info in these headers
AUTH_USER_HEADER = 'HTTP_X_FORWARDED_USER'  # IIS may use this
LOGON_USER_HEADER = 'HTTP_X_REMOTE_USER'  # Alternative header
AUTH_TYPE_HEADER = 'HTTP_X_AUTH_TYPE'

# Asana feedback — set ASANA_ACCESS_TOKEN (PAT or service account token) + project GID in .env.
# Client id/secret are optional (only needed for OAuth refresh-token flow).
ASANA_ACCESS_TOKEN = _env_value('ASANA_ACCESS_TOKEN') or os.environ.get('ASANA_ACCESS_TOKEN', '')
ASANA_CLIENT_ID = _env_value('ASANA_CLIENT_ID') or os.environ.get('ASANA_CLIENT_ID', '')
ASANA_CLIENT_SECRET = _env_value('ASANA_CLIENT_SECRET') or os.environ.get('ASANA_CLIENT_SECRET', '')
ASANA_REFRESH_TOKEN = _env_value('ASANA_REFRESH_TOKEN') or os.environ.get('ASANA_REFRESH_TOKEN', '')
# Must match a redirect URL registered on your Asana app (leave blank to use /admin/asana/callback)
ASANA_REDIRECT_URI = _env_value('ASANA_REDIRECT_URI') or os.environ.get('ASANA_REDIRECT_URI', '')
# Project where feedback tasks are created (numeric GID from project URL in Asana)
ASANA_FEEDBACK_PROJECT_GID = _env_value('ASANA_FEEDBACK_PROJECT_GID') or os.environ.get('ASANA_FEEDBACK_PROJECT_GID', '')
# Section (list) GIDs within that project — from .../project/PROJECT_GID/list/SECTION_GID
ASANA_SECTION_GID_COMMENT = _env_value('ASANA_SECTION_GID_COMMENT') or os.environ.get('ASANA_SECTION_GID_COMMENT', '')
ASANA_SECTION_GID_ISSUE = _env_value('ASANA_SECTION_GID_ISSUE') or os.environ.get('ASANA_SECTION_GID_ISSUE', '')
ASANA_SECTION_GID_SUGGESTION = _env_value('ASANA_SECTION_GID_SUGGESTION') or os.environ.get('ASANA_SECTION_GID_SUGGESTION', '')
ASANA_FEEDBACK_SECTION_GIDS = {
    'comment': ASANA_SECTION_GID_COMMENT,
    'issue': ASANA_SECTION_GID_ISSUE,
    'suggestion': ASANA_SECTION_GID_SUGGESTION,
}
# User GID for assignee on new feedback tasks (from GET /users/{email} or Asana profile URL)
ASANA_FEEDBACK_ASSIGNEE_GID = _env_value('ASANA_FEEDBACK_ASSIGNEE_GID') or os.environ.get('ASANA_FEEDBACK_ASSIGNEE_GID', '')

