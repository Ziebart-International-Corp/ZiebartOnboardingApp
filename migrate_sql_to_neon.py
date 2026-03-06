#!/usr/bin/env python3
"""
Migrate all tables and data from ZiebartOnboarding (SQL Server) to Neon (PostgreSQL).

Source: SQL Server - set DB_SERVER, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD in .env (or .env.example).
Destination: Neon - set DATABASE_URL to your Neon Postgres URL in .env (e.g. from Neon dashboard).

Run from project root with venv active (needs both pyodbc and psycopg2):
  python migrate_sql_to_neon.py

Before running: create a Neon project at https://neon.tech and put the connection string in .env as DATABASE_URL.
"""
import os
import sys
from pathlib import Path
from urllib.parse import quote_plus

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / '.env')
    # Also try next-app/.env for DATABASE_URL if you keep it there
    load_dotenv(Path(__file__).parent / 'next-app' / '.env')
except ImportError:
    pass

# Source: SQL Server (ZiebartOnboarding)
SOURCE_SERVER = os.environ.get('DB_SERVER', 'iBartConnect.com')
SOURCE_PORT = os.environ.get('DB_PORT', '42278')
SOURCE_NAME = os.environ.get('DB_NAME', 'ZiebartOnboarding')
SOURCE_USER = os.environ.get('DB_USER', 'developer2')
SOURCE_PASSWORD = os.environ.get('DB_PASSWORD', '')

# Destination: Neon (PostgreSQL)
NEON_URL = os.environ.get('DATABASE_URL', '').strip()
if not NEON_URL or (not NEON_URL.startswith('postgresql://') and not NEON_URL.startswith('postgres://')):
    print('Set DATABASE_URL in .env to your Neon connection string (postgresql://user:pass@host/db?sslmode=require)')
    sys.exit(1)

if not SOURCE_PASSWORD:
    print('Set DB_PASSWORD (and DB_SERVER, DB_NAME, DB_USER if needed) in .env for the SQL Server source.')
    sys.exit(1)

def _mssql_uri(server, port, db_name, user, password):
    enc = quote_plus(password)
    return (
        f'mssql+pyodbc://{user}:{enc}@{server}:{port}/{db_name}'
        f'?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes'
    )

source_uri = _mssql_uri(SOURCE_SERVER, SOURCE_PORT, SOURCE_NAME, SOURCE_USER, SOURCE_PASSWORD)

print(f'Source (SQL Server): {SOURCE_SERVER}:{SOURCE_PORT}/{SOURCE_NAME}')
print(f'Dest (Neon):        {NEON_URL.split("@")[1].split("/")[0] if "@" in NEON_URL else "Neon"}')
print()

from sqlalchemy import create_engine, text
from models import db

def _has_serial(table):
    """Postgres: table has a single auto-increment PK (we'll set sequence after insert)."""
    pk = table.primary_key
    if not pk or len(pk.columns) != 1:
        return False
    return getattr(pk.columns[0], 'autoincrement', False)

def main():
    source_engine = create_engine(source_uri)
    dest_engine = create_engine(NEON_URL)

    # 1) Create all tables in Neon from models
    print('Creating tables in Neon...')
    db.metadata.create_all(dest_engine)
    print('Tables created.')

    tables = list(db.metadata.sorted_tables)
    print(f'Copying data for {len(tables)} tables...')

    for table in tables:
        name = table.name
        model_cols = [c.name for c in table.c]
        if not model_cols:
            continue
        use_serial = _has_serial(table)
        pk_col = table.primary_key.columns[0].name if (table.primary_key and len(table.primary_key.columns) == 1) else None

        # Columns that exist on SQL Server source
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
        col_list_sql = ', '.join(f'[{c}]' for c in cols)

        with source_engine.connect() as src_conn:
            try:
                rows = src_conn.execute(text(f'SELECT {col_list_sql} FROM [{name}]')).fetchall()
            except Exception as e:
                print(f'  Skip {name}: {e}')
                continue

        if not rows:
            print(f'  {name}: 0 rows')
            continue

        with dest_engine.connect() as dest_conn:
            try:
                stmt = table.insert()
                for row in rows:
                    try:
                        dest_conn.execute(stmt, dict(zip(cols, row)))
                    except Exception as e:
                        print(f'  {name} insert warning: {e}')
                dest_conn.commit()
                # Postgres: set sequence so next INSERT gets correct id
                if use_serial and pk_col:
                    try:
                        dest_conn.execute(text(
                            f"SELECT setval(pg_get_serial_sequence(:t, :pk), COALESCE((SELECT MAX({pk_col}) FROM {name}), 1))"
                        ), {'t': name, 'pk': pk_col})
                        dest_conn.commit()
                    except Exception:
                        pass
            except Exception as e:
                print(f'  {name} error: {e}')

        print(f'  {name}: {len(rows)} rows')

    print('Done. Neon is ready. Set DATABASE_URL in Vercel (and locally for the app) to use it.')

if __name__ == '__main__':
    main()
