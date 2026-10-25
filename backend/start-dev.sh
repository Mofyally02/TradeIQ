#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [[ -n "${VIRTUAL_ENV:-}" && -x "$VIRTUAL_ENV/bin/python" ]]; then
  PYTHON_BIN="$VIRTUAL_ENV/bin/python"
elif [[ -x .venv/bin/python ]]; then
  PYTHON_BIN=".venv/bin/python"
else
  echo "Backend virtual environment not found. Create it and install dependencies:" >&2
  echo "  python3 -m venv .venv && .venv/bin/python -m pip install -e '.[dev]'" >&2
  exit 1
fi

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required to start PostgreSQL. Install it or start PostgreSQL manually." >&2
  exit 1
fi

if ! command -v pg_isready >/dev/null 2>&1 || ! command -v psql >/dev/null 2>&1; then
  echo "PostgreSQL client tools are missing. Install PostgreSQL 14 with: brew install postgresql@14" >&2
  exit 1
fi

if ! pg_isready -d postgres >/dev/null 2>&1; then
  brew services start postgresql@14

  for _ in {1..30}; do
    if pg_isready -d postgres >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
fi

if ! pg_isready -d postgres >/dev/null 2>&1; then
  echo "PostgreSQL did not become ready. Check its Homebrew service with: brew services list" >&2
  exit 1
fi

if [[ "$(psql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = 'tradeiq'")" != "1" ]]; then
  createdb tradeiq
fi

export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg:///tradeiq}"

"$PYTHON_BIN" -m alembic upgrade head
exec "$PYTHON_BIN" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
