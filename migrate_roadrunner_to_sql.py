#!/usr/bin/env python3
"""
Migrate all tables and data from roadrunner (NewHireApp) to ZiebartOnboarding on iBartConnect SQL Server.

Source: roadrunner / NewHireApp (or set SOURCE_DB_SERVER, SOURCE_DB_NAME, etc. in .env)
Destination: from .env.example (DB_SERVER=iBartConnect.com, DB_NAME=ZiebartOnboarding, etc.)

Run from project root with venv active:
  python migrate_roadrunner_to_sql.py

Requires: pyodbc, SQLAlchemy, python-dotenv; ODBC Driver 18 for SQL Server.
"""
import os
import sys
from pathlib import Path
from urllib.parse import quote_plus

# Load .env first (source may be there)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / '.env')
except ImportError:
    pass

# Parse .env.example for destination (uncommented KEY=VALUE lines)
_root = Path(__file__).resolve().parent
_env_example = _root / '.env.example'
_dest = {}
if _env_example.exists():
    for line in _env_example.read_text(encoding='utf-8', errors='replace').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' in line:
            k, _, v = line.partition('=')
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k.startswith('DB_'):
                _dest[k] = v

# Source: defaults to roadrunner/NewHireApp
SOURCE_SERVER = os.environ.get('SOURCE_DB_SERVER') or os.environ.get('DB_SERVER') or 'roadrunner'
SOURCE_PORT = os.environ.get('SOURCE_DB_PORT') or os.environ.get('DB_PORT') or '42278'
SOURCE_NAME = os.environ.get('SOURCE_DB_NAME') or os.environ.get('DB_NAME') or 'NewHireApp'
SOURCE_USER = os.environ.get('SOURCE_DB_USER') or os.environ.get('DB_USER') or 'Developer'
SOURCE_PASSWORD = os.environ.get('SOURCE_DB_PASSWORD') or os.environ.get('DB_PASSWORD') or '1Shot@OneKill'

# Destination: from .env.example (or DEST_* env vars)
DEST_SERVER = os.environ.get('DEST_DB_SERVER') or _dest.get('DB_SERVER', '')
DEST_PORT = os.environ.get('DEST_DB_PORT') or _dest.get('DB_PORT', '42278')
DEST_NAME = os.environ.get('DEST_DB_NAME') or _dest.get('DB_NAME', '')
DEST_USER = os.environ.get('DEST_DB_USER') or _dest.get('DB_USER', '')
DEST_PASSWORD = os.environ.get('DEST_DB_PASSWORD') or _dest.get('DB_PASSWORD', '')

if not DEST_SERVER or not DEST_NAME or not DEST_USER or not DEST_PASSWORD:
    print('Destination not fully set. Ensure .env.example has DB_SERVER, DB_NAME, DB_USER, DB_PASSWORD (uncommented).')
    sys.exit(1)

def _mssql_uri(server, port, db_name, user, password):
    enc = quote_plus(password)
    return (
        f'mssql+pyodbc://{user}:{enc}@{server}:{port}/{db_name}'
        f'?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes'
    )

source_uri = _mssql_uri(SOURCE_SERVER, SOURCE_PORT, SOURCE_NAME, SOURCE_USER, SOURCE_PASSWORD)
dest_uri = _mssql_uri(DEST_SERVER, DEST_PORT, DEST_NAME, DEST_USER, DEST_PASSWORD)

print(f'Source:  {SOURCE_SERVER}:{SOURCE_PORT}/{SOURCE_NAME}')
print(f'Dest:    {DEST_SERVER}:{DEST_PORT}/{DEST_NAME}')
print()

# Import after env is set so we don't trigger app config
from sqlalchemy import create_engine, text

# Use models metadata without loading Flask app config
from models import db

# Tables that have IDENTITY in SQL Server - need IDENTITY_INSERT (association tables have composite PK, no identity)
def _has_identity(table):
    pk = table.primary_key
    if not pk or len(pk.columns) != 1:
        return False
    return getattr(pk.columns[0], 'autoincrement', False)

def main():
    source_engine = create_engine(source_uri)
    dest_engine = create_engine(dest_uri)

    # 1) Create all tables on destination from models
    print('Creating tables on destination...')
    db.metadata.create_all(dest_engine)
    print('Tables created.')

    # 2) Copy data in dependency order (metadata.sorted_tables)
    # SQLAlchemy sorted_tables: dependency order (no-FK tables first)
    tables = list(db.metadata.sorted_tables)
    print(f'Copying data for {len(tables)} tables...')

    for table in tables:
        name = table.name
        model_cols = [c.name for c in table.c]
        if not model_cols:
            continue
        use_identity = _has_identity(table)

        # Get columns that exist on source (source may have fewer columns from older migrations)
        with source_engine.connect() as src_conn:
            try:
                src_cols = src_conn.execute(text(
                    "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = :t"
                ), {'t': name}).fetchall()
                src_col_set = {r[0] for r in src_cols}
            except Exception as e:
                print(f'  Skip {name}: {e}')
                continue
        cols = [c for c in model_cols if c in src_col_set]
        if not cols:
            print(f'  Skip {name}: no matching columns')
            continue
        col_list = ', '.join(f'[{c}]' for c in cols)

        with source_engine.connect() as src_conn:
            try:
                rows = src_conn.execute(text(f'SELECT {col_list} FROM [{name}]')).fetchall()
            except Exception as e:
                print(f'  Skip {name}: {e}')
                continue

        if not rows:
            print(f'  {name}: 0 rows')
            continue

        with dest_engine.connect() as dest_conn:
            if use_identity:
                dest_conn.execute(text(f'SET IDENTITY_INSERT [{name}] ON'))
                dest_conn.commit()
            try:
                stmt = table.insert()
                for row in rows:
                    try:
                        dest_conn.execute(stmt, dict(zip(cols, row)))
                    except Exception as e:
                        print(f'  {name} insert warning: {e}')
                dest_conn.commit()
            finally:
                if use_identity:
                    dest_conn.execute(text(f'SET IDENTITY_INSERT [{name}] OFF'))
                    dest_conn.commit()

        print(f'  {name}: {len(rows)} rows')

    print('Done.')

if __name__ == '__main__':
    main()
