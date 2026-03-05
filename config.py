"""
Configuration settings for the New Hire Application
"""
import os
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).parent

# Secret key for sessions (change in production!)
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Windows Domain Configuration
DOMAIN_NAME = os.environ.get('DOMAIN_NAME', 'YOURDOMAIN')  # e.g., 'CONTOSO'
DOMAIN_CONTROLLER = os.environ.get('DOMAIN_CONTROLLER', None)  # Optional: specific DC
LDAP_BASE_DN = os.environ.get('LDAP_BASE_DN', None)  # Optional: e.g., 'DC=contoso,DC=com'

# Email Configuration
EMAIL_DOMAIN = os.environ.get('EMAIL_DOMAIN', 'ziebart.com')  # Email domain for default email addresses

# Admin Configuration
# Option 1: List of admin usernames (without domain)
ADMIN_USERS = os.environ.get('ADMIN_USERS', '').split(',') if os.environ.get('ADMIN_USERS') else []
# Option 2: AD Group for admins (if using LDAP)
ADMIN_GROUP = os.environ.get('ADMIN_GROUP', 'Domain Admins')  # AD group name

# Authentication Method
# 'windows' - Use IIS Windows Authentication headers
# 'ldap' - Use LDAP/AD queries (requires domain controller access)
AUTH_METHOD = os.environ.get('AUTH_METHOD', 'windows')

# Database (CockroachDB / PostgreSQL)
# Set DATABASE_URL for CockroachDB, e.g.:
# postgresql://user:password@host:26257/dbname?sslmode=verify-full
DB_SERVER = os.environ.get('DB_SERVER', '')
DB_PORT = os.environ.get('DB_PORT', '26257')
DB_NAME = os.environ.get('DB_NAME', 'ziebartonboarding')
DB_USER = os.environ.get('DB_USER', '')
DB_PASSWORD = os.environ.get('DB_PASSWORD', '')
DB_MAX_POOL_SIZE = os.environ.get('DB_MAX_POOL_SIZE', '300')

from urllib.parse import quote_plus
_db_password_encoded = quote_plus(DB_PASSWORD) if DB_PASSWORD else ''
# Prefer DATABASE_URL (CockroachDB/PostgreSQL). Otherwise build from parts.
SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or (
    f'postgresql://{DB_USER}:{_db_password_encoded}@{DB_SERVER}:{DB_PORT}/{DB_NAME}?sslmode=verify-full'
    if (DB_SERVER and DB_USER) else ''
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
# When behind IIS with HTTPS, Flask needs to trust proxy headers
PREFERRED_URL_SCHEME = os.environ.get('PREFERRED_URL_SCHEME', 'http')  # Change to 'https' when HTTPS is enabled
PROXY_FIX = os.environ.get('PROXY_FIX', 'False').lower() == 'true'  # Enable if behind reverse proxy

# IIS Windows Authentication Headers
# IIS passes authenticated user info in these headers
AUTH_USER_HEADER = 'HTTP_X_FORWARDED_USER'  # IIS may use this
LOGON_USER_HEADER = 'HTTP_X_REMOTE_USER'  # Alternative header
AUTH_TYPE_HEADER = 'HTTP_X_AUTH_TYPE'

