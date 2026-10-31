"""Session-level guards in tests/conftest.py: the single-session lock and the
leftover-reloptions reset. Both run a real nested pytest in a subprocess."""

import os
import subprocess
import sys
from pathlib import Path

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
