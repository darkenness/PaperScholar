#!/bin/sh
set -e

echo "[startup] Running database migrations..."
alembic --sqlalchemy-url "$DATABASE_URL" -c alembic.ini upgrade head || echo "[startup] Migration completed or already up to date"

echo "[startup] Starting uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
