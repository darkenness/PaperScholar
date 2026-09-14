#!/bin/sh
set -eu

# Bootstrap databases created by the pre-Alembic create_all startup, then run
# the real Alembic upgrade using the same DATABASE_URL as the application.
python - <<'PY'
import asyncio
from sqlalchemy import inspect, text

from alembic import command
from alembic.config import Config
from app.config import settings
from app.core.database import Base, engine


async def bootstrap_if_unversioned():
    async with engine.begin() as connection:
        tables = await connection.run_sync(lambda sync: set(inspect(sync).get_table_names()))
        if "alembic_version" not in tables:
            await connection.run_sync(Base.metadata.create_all)
            await connection.execute(
                text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
            )
    await engine.dispose()


asyncio.run(bootstrap_if_unversioned())

config = Config("alembic.ini")
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)


async def has_empty_version_table():
    from sqlalchemy.ext.asyncio import create_async_engine

    probe = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    async with probe.connect() as connection:
        def check(sync):
            if "alembic_version" not in inspect(sync).get_table_names():
                return False
            return sync.execute(text("SELECT COUNT(*) FROM alembic_version")).scalar_one() == 0

        result = await connection.run_sync(check)
    await probe.dispose()
    return result


if asyncio.run(has_empty_version_table()):
    command.stamp(config, "head")
command.upgrade(config, "head")
PY

if [ "${RELOAD:-false}" = "true" ]; then
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
