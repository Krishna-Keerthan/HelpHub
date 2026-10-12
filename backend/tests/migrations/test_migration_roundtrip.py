"""upgrade head -> downgrade base -> upgrade head on a scratch database."""

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings

BACKEND = Path(__file__).resolve().parents[2]


def _url_for(url: str, database: str) -> str:
    return make_url(url).set(database=database).render_as_string(hide_password=False)


def _alembic(env: dict[str, str], *args: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    # stderr can carry driver messages; show only the last lines on failure.
    tail = "\n".join((result.stdout + result.stderr).splitlines()[-15:])
    assert result.returncode == 0, f"alembic {' '.join(args)} failed:\n{tail}"


@pytest.mark.slow
async def test_upgrade_downgrade_upgrade_roundtrip() -> None:
    name = f"helphub_migtest_{uuid.uuid4().hex}"
    owner_url = settings.migration_database_url
    admin = create_async_engine(
        owner_url, poolclass=NullPool, isolation_level="AUTOCOMMIT"
    )
    env = {
        **os.environ,
        "MIGRATION_DATABASE_URL": _url_for(owner_url, name),
        "DATABASE_URL": _url_for(settings.database_url, name),
    }
    scratch: object | None = None
    try:
        async with admin.connect() as conn:
            await conn.execute(text(f'CREATE DATABASE "{name}"'))
        scratch = create_async_engine(
            env["MIGRATION_DATABASE_URL"], poolclass=NullPool
        )

        _alembic(env, "upgrade", "head")
        _alembic(env, "downgrade", "base")

        async with scratch.connect() as conn:  # type: ignore[attr-defined]
            tables = (
                (
                    await conn.execute(
                        text(
                            "SELECT tablename FROM pg_tables "
                            "WHERE schemaname = 'public' ORDER BY 1"
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert list(tables) == ["alembic_version"]

        _alembic(env, "upgrade", "head")
        _alembic(env, "check")
    finally:
        if scratch is not None:
            await scratch.dispose()  # type: ignore[attr-defined]
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await admin.dispose()
