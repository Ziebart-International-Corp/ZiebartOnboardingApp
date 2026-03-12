"""Load env from project root and expose DB URL for data_api."""
import os
import sys
from pathlib import Path

# Project root = parent of data_api
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Load .env from project root
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env')
except ImportError:
    pass

_database_url = os.environ.get('DATABASE_URL', '').strip()
if _database_url and (_database_url.startswith('postgresql://') or _database_url.startswith('postgres://')):
    DATABASE_URI = _database_url
    IS_POSTGRES = True
else:
    IS_POSTGRES = False
    from urllib.parse import quote_plus
    DB_SERVER = os.environ.get('DB_SERVER', '')
    DB_PORT = os.environ.get('DB_PORT', '42278')
    DB_NAME = os.environ.get('DB_NAME', '')
    DB_USER = os.environ.get('DB_USER', '')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', '')
    DB_PASSWORD_ENCODED = quote_plus(DB_PASSWORD)
    DATABASE_URI = (
        f'mssql+pyodbc://{DB_USER}:{DB_PASSWORD_ENCODED}@{DB_SERVER}:{DB_PORT}/{DB_NAME}'
        f'?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes'
    )

try:
    IS_POSTGRES
except NameError:
    IS_POSTGRES = False

API_KEY = os.environ.get('DATA_API_KEY', '').strip()  # Optional: require X-API-Key header
