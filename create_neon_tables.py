#!/usr/bin/env python3
"""
Create all tables in Neon (PostgreSQL). Run once after creating a Neon project.

Usage:
  Set DATABASE_URL to your Neon connection string (e.g. from Neon dashboard), then:
    python create_neon_tables.py

  Or: DATABASE_URL='postgresql://...' python create_neon_tables.py
  Or: use a .env file in this directory with DATABASE_URL=...
"""
import os
import sys

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Ensure DATABASE_URL is set and points to Postgres
url = os.environ.get('DATABASE_URL', '').strip()
if not url or (not url.startswith('postgresql://') and not url.startswith('postgres://')):
    print('Set DATABASE_URL to your Neon Postgres connection string (e.g. postgresql://user:pass@host/db?sslmode=require)')
    sys.exit(1)

# Load app and create tables
from app import app, db

with app.app_context():
    db.create_all()
    print('Tables created successfully in Neon.')
