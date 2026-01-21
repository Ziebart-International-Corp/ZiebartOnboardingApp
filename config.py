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

# Database (SQL Server)
# Connection string format: Server=server,port;Database=dbname;User Id=user;Password=pass
DB_SERVER = os.environ.get('DB_SERVER', 'roadrunner')
DB_PORT = os.environ.get('DB_PORT', '42278')
DB_NAME = os.environ.get('DB_NAME', 'NewHireApp')
DB_USER = os.environ.get('DB_USER', 'Developer')
DB_PASSWORD = os.environ.get('DB_PASSWORD', '1Shot@OneKill')
DB_MAX_POOL_SIZE = os.environ.get('DB_MAX_POOL_SIZE', '300')

# SQLAlchemy connection string for SQL Server
# Using pyodbc driver (requires ODBC Driver for SQL Server)
from urllib.parse import quote_plus
DB_PASSWORD_ENCODED = quote_plus(DB_PASSWORD)
# Connection string format: mssql+pyodbc://user:password@server:port/database?driver=ODBC+Driver+18+for+SQL+Server
# URL encode the driver name: ODBC Driver 18 for SQL Server -> ODBC+Driver+18+for+SQL+Server
SQLALCHEMY_DATABASE_URI = os.environ.get(
    'DATABASE_URL',
    f'mssql+pyodbc://{DB_USER}:{DB_PASSWORD_ENCODED}@{DB_SERVER}:{DB_PORT}/{DB_NAME}?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes'
)
SQLALCHEMY_TRACK_MODIFICATIONS = False
SQLALCHEMY_ENGINE_OPTIONS = {
    'pool_size': int(DB_MAX_POOL_SIZE),
    'max_overflow': 0,
    'pool_pre_ping': True,  # Verify connections before using
    'pool_recycle': 3600,   # Recycle connections after 1 hour
}

# Session Configuration
SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
PERMANENT_SESSION_LIFETIME = 3600  # 1 hour

# IIS Windows Authentication Headers
# IIS passes authenticated user info in these headers
AUTH_USER_HEADER = 'HTTP_X_FORWARDED_USER'  # IIS may use this
LOGON_USER_HEADER = 'HTTP_X_REMOTE_USER'  # Alternative header
AUTH_TYPE_HEADER = 'HTTP_X_AUTH_TYPE'

