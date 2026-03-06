"""
Configuration settings for the New Hire Application
"""
import os
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).parent

# Load .env from project root so DATABASE_URL etc. are set
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / '.env')
except ImportError:
    pass

# Secret key for sessions (change in production!)
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Windows Domain Configuration
DOMAIN_NAME = os.environ.get('DOMAIN_NAME', 'YOURDOMAIN')  # e.g., 'CONTOSO'
DOMAIN_CONTROLLER = os.environ.get('DOMAIN_CONTROLLER', None)  # Optional: specific DC
LDAP_BASE_DN = os.environ.get('LDAP_BASE_DN', None)  # Optional: e.g., 'DC=contoso,DC=com'

# Email Configuration
EMAIL_DOMAIN = os.environ.get('EMAIL_DOMAIN', 'ziebart.com')  # Email domain for default email addresses
MAIL_SERVER = os.environ.get('MAIL_SERVER', '')
MAIL_PORT = int(os.environ.get('MAIL_PORT', '587'))
MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'false').lower() == 'true'
MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', '')

# Admin Configuration
# Option 1: List of admin usernames (without domain)
ADMIN_USERS = os.environ.get('ADMIN_USERS', '').split(',') if os.environ.get('ADMIN_USERS') else []
# Option 2: AD Group for admins (if using LDAP)
ADMIN_GROUP = os.environ.get('ADMIN_GROUP', 'Domain Admins')  # AD group name

# Authentication Method
# 'windows' - Use IIS Windows Authentication headers
# 'ldap' - Use LDAP/AD queries (requires domain controller access)
AUTH_METHOD = os.environ.get('AUTH_METHOD', 'windows')

# Database: SQL Server (ZiebartOnboarding) by default via DB_* env vars.
# Optionally set DATABASE_URL to a Postgres URL (e.g. Neon) to use PostgreSQL instead.
DB_SERVER = os.environ.get('DB_SERVER', 'roadrunner')
DB_PORT = os.environ.get('DB_PORT', '42278')
DB_NAME = os.environ.get('DB_NAME', 'NewHireApp')
DB_USER = os.environ.get('DB_USER', 'Developer')
DB_PASSWORD = os.environ.get('DB_PASSWORD', '1Shot@OneKill')
DB_MAX_POOL_SIZE = os.environ.get('DB_MAX_POOL_SIZE', '300')

_database_url = os.environ.get('DATABASE_URL', '').strip()
if _database_url and (_database_url.startswith('postgresql://') or _database_url.startswith('postgres://')):
    SQLALCHEMY_DATABASE_URI = _database_url
    IS_POSTGRES = True
else:
    from urllib.parse import quote_plus
    DB_PASSWORD_ENCODED = quote_plus(DB_PASSWORD)
    SQLALCHEMY_DATABASE_URI = (
        f'mssql+pyodbc://{DB_USER}:{DB_PASSWORD_ENCODED}@{DB_SERVER}:{DB_PORT}/{DB_NAME}'
        f'?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes'
    )
    IS_POSTGRES = False

SQLALCHEMY_TRACK_MODIFICATIONS = False
SQLALCHEMY_ENGINE_OPTIONS = {
    'pool_size': 10 if (_database_url and (_database_url.startswith('postgresql://') or _database_url.startswith('postgres://'))) else int(DB_MAX_POOL_SIZE),
    'max_overflow': 0,
    'pool_pre_ping': True,
    'pool_recycle': 3600,
}

# Session Configuration
# SESSION_COOKIE_SECURE will be set dynamically based on request scheme
# When HTTPS is enabled, set this to True in app.py after checking request
SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
PERMANENT_SESSION_LIFETIME = 3600  # 1 hour

# HTTPS/Proxy Configuration
# When behind IIS with HTTPS, Flask needs to trust proxy headers
PREFERRED_URL_SCHEME = os.environ.get('PREFERRED_URL_SCHEME', 'http')  # Change to 'https' when HTTPS is enabled
PROXY_FIX = os.environ.get('PROXY_FIX', 'False').lower() == 'true'  # Enable if behind reverse proxy

# IIS Windows Authentication Headers
# IIS passes authenticated user info in these headers
AUTH_USER_HEADER = 'HTTP_X_FORWARDED_USER'  # IIS may use this
LOGON_USER_HEADER = 'HTTP_X_REMOTE_USER'  # Alternative header
AUTH_TYPE_HEADER = 'HTTP_X_AUTH_TYPE'

