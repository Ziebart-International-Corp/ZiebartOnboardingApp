#!/usr/bin/env bash
# Local Mac launcher: wires project-local ODBC/OpenSSL and starts Flask.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "$ROOT/venv/bin/activate"

UODBC="$ROOT/.odbc/brew_unixodbc/unixodbc/2.3.14"
LT="$ROOT/.odbc/brew_libtool/libtool/2.5.4"
SSL="$ROOT/.odbc/brew_openssl/openssl@3/3.6.3"
FAKE="$ROOT/.odbc/brewfake"

export DYLD_LIBRARY_PATH="$UODBC/lib:$LT/lib:$SSL/lib:$FAKE/lib:${DYLD_LIBRARY_PATH:-}"
export ODBCSYSINI="$UODBC/etc"
export ODBCINSTINI="$UODBC/etc/odbcinst.ini"
export ODBCINI="$UODBC/etc/odbc.ini"
# Required for ODBC Driver 18 + OpenSSL 3 against this SQL Server
export OPENSSL_CONF="${OPENSSL_CONF:-$ROOT/.odbc/openssl_sql.cnf}"
if [[ -f "$SSL/etc/openssl@3/cert.pem" ]]; then
  export SSL_CERT_FILE="${SSL_CERT_FILE:-$SSL/etc/openssl@3/cert.pem}"
fi

export DB_DRIVER="${DB_DRIVER:-odbc}"
# Absolute dylib path so Driver Manager does not depend on odbcinst name lookup
export ODBC_DRIVER="${ODBC_DRIVER:-$FAKE/lib/libmsodbcsql.18.dylib}"
export FLASK_DEBUG="${FLASK_DEBUG:-1}"
export FORCE_HTTPS="${FORCE_HTTPS:-false}"
export PROXY_FIX="${PROXY_FIX:-false}"
export PORT="${PORT:-5001}"
# DB works with OPENSSL_CONF above; only set SKIP_STARTUP_MIGRATIONS=1 if needed
export SKIP_STARTUP_MIGRATIONS="${SKIP_STARTUP_MIGRATIONS:-0}"

echo "Starting onboarding app at http://127.0.0.1:${PORT} ..."
exec python -c "import os; from app import app; app.run(debug=os.getenv('FLASK_DEBUG','1').lower() in ('1','true','yes'), host='127.0.0.1', port=int(os.getenv('PORT','5001')), use_reloader=False)"
