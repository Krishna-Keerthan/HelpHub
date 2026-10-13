"""Session-level guards in tests/conftest.py: the single-session lock and the
leftover-reloptions reset. Both run a real nested pytest in a subprocess."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings

BACKEND = Path(__file__).resolve().parents[2]
TRIVIAL = "tests/tooling/trivial_target.py"


def _run_nested(extra_env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != "HELPHUB_PYTEST_LOCK_HOLDER"}
    env.update(extra_env)
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", TRIVIAL],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_second_session_is_refused_while_the_lock_is_held() -> None:
    # This session already holds the default lock; a nested one must be refused.
    result = _run_nested({})
    assert result.returncode != 0
    assert "another pytest session is running (shared database)" in (
        result.stdout + result.stderr
    )


def test_lock_holder_env_with_a_live_pid_lets_the_hunt_run_its_children() -> None:
    result = _run_nested({"HELPHUB_PYTEST_LOCK_HOLDER": str(os.getppid())})
    assert result.returncode == 0, result.stdout + result.stderr


async def _set_and_read_reloptions(set_option: bool) -> list[str] | None:
    engine = create_async_engine(
        settings.migration_database_url,
        poolclass=NullPool,
        isolation_level="AUTOCOMMIT",
    )
    try:
        async with engine.connect() as conn:
            if set_option:
                await conn.execute(
                    text("ALTER TABLE chunks SET (autovacuum_enabled = false)")
                )
            return (
                await conn.execute(
                    text(
                        "SELECT reloptions FROM pg_class "
                        "WHERE oid = 'public.chunks'::regclass"
                    )
                )
            ).scalar_one()
    finally:
        await engine.dispose()


async def test_session_start_resets_leftover_autovacuum_option(tmp_path: Path) -> None:
    try:
        assert await _set_and_read_reloptions(True) == ["autovacuum_enabled=false"]
        result = await asyncio.to_thread(
            _run_nested, {"HELPHUB_PYTEST_LOCK_FILE": str(tmp_path / "other.lock")}
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "leftover reloptions" in result.stderr
        assert await _set_and_read_reloptions(False) is None
    finally:
        engine = create_async_engine(
            settings.migration_database_url,
            poolclass=NullPool,
            isolation_level="AUTOCOMMIT",
        )
        async with engine.connect() as conn:
            await conn.execute(text("ALTER TABLE chunks RESET (autovacuum_enabled)"))
        await engine.dispose()
