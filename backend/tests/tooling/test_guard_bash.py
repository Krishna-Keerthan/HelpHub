"""Table-driven tests for .claude/hooks/guard_bash.py (best-effort command guard)."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[3] / ".claude" / "hooks" / "guard_bash.py"
_spec = importlib.util.spec_from_file_location("guard_bash", HOOK)
assert _spec is not None and _spec.loader is not None
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)

REPO = str(guard.REPO_ROOT)

BLOCKED = [
    "docker compose down -v",
    "docker compose down --volumes",
    "docker compose down --remove-orphans -v",
    "docker-compose down -v",
    "cd x && docker compose down --volumes",
    "docker volume rm helphub_pgdata",
    "docker volume prune -f",
    "docker system prune --volumes",
    "docker system prune",
    "docker system prune -af",
    "docker system  prune --all --volumes",
    "docker volume remove helphub_pgdata",
    "docker volume remove",
    "docker volume rm -f helphub_pgdata",
    "docker volume prune",
    "docker volume prune --all",
    "docker --context x volume rm v",
    "docker-compose volume rm v",
    "docker compose down -fv",
    "docker compose down -vf",
    "docker compose down --rmi all --volumes",
    "echo hi; docker volume rm v",
    "true && docker system prune",
    'bash -c "docker volume rm v"',
    "echo 'unterminated",
    'git commit -m "unterminated',
    "git push --force",
    "git push -f origin main",
    "git push origin main --force",
    "git push --force-with-lease",
    "git push origin +main",
    "git reset --hard",
    "git reset --hard HEAD~3",
    "git clean -fd",
    "git clean -fdx",
    "git clean -f",
    "git clean --force",
    "git commit --no-verify -m x",
    "git commit -m x --no-verify",
    "git commit -n -m x",
    "git push --no-verify",
    "rm -rf /",
    "rm -rf /*",
    "rm -rf ~",
    "rm -rf ~/",
    "rm -rf $HOME",
    "rm -rf ${HOME}/",
    "rm -fr /home/krish",
    f"rm -rf {REPO}",
    f"rm -rf {REPO}/",
    "rm -rf .",
    "rm -rf *",
    "rm -rf ..",
    "rm -r -f /",
    "sudo rm -rf /",
    "rm --recursive --force /",
    "rm -rf --no-preserve-root /",
    "psql -c 'DROP DATABASE helphub'",
    'docker compose exec postgres psql -U x -c "drop database helphub"',
    "echo ok && docker compose down -v",
    "cat .env",
    "cat ./.env",
    "cat backend/.env",
    "cat ../.env",
    "head -n 3 .env",
    "tail .env",
    "less .env",
    "sed -n 1p .env",
    "awk '{print}' .env",
    "grep JWT .env",
    "rg SECRET .env",
    "source .env",
    ". .env",
    "set -a; source .env; set +a",
    "cat .env.local",
    "cat < .env",
    "cat <.env",
    "python -c \"print(open('.env').read())\"",
    "python3 -c 'import pathlib; print(pathlib.Path(\".env\").read_text())'",
    "uv run python -c \"open('.env')\"",
    "bash <<EOF\ndocker compose down -v\nEOF",
    "cat <<'EOF' | bash\ndocker compose down -v\nEOF",
    "bash -c 'cat .env'",
    'bash -c "git push --force"',
    "cat nonexistent && cat .env",
    "cat 'unterminated .env",
]

ALLOWED = [
    "ls -la",
    "git status --short",
    "git diff HEAD~1",
    "git log --oneline -5",
    "git add .",
    "git add -A",
    "git add .env.example",
    'git commit -m "Day 5 commit 5b"',
    'git commit -m "mention git reset --hard and --no-verify and DROP DATABASE"',
    "git commit -m \"$(cat <<'EOF'\nfix rm -rf / docs\nEOF\n)\"",
    "git commit --amend --no-edit",
    "git push",
    "git push origin main",
    "git push -u origin feature",
    "git push --dry-run",
    "git reset HEAD file.py",
    "git reset --soft HEAD~1",
    "git clean -n",
    "git clean --dry-run",
    "git switch main",
    "git branch -D calibration/seeded",
    "git stash push -m x",
    "uv run pytest",
    "uv run pytest -q -m 'slow or not slow' -rfsx",
    "uv run pytest tests/auth -k drop_database",
    "uv run ruff check .",
    "uv run ruff format app/main.py",
    "uv run alembic upgrade head",
    "uv run alembic downgrade base",
    "uv run alembic check",
    "docker compose up -d",
    "docker compose ps",
    "docker compose down",
    "docker compose logs postgres",
    "docker compose exec postgres psql -U owner -c 'select 1'",
    "docker volume ls",
    "docker ps",
    "rm -rf node_modules",
    "rm -rf ./build",
    "rm -rf /tmp/scratch",
    f"rm -rf {REPO}/backend/.pytest_cache",
    "rm file.txt",
    "rm -f /tmp/x.log",
    "cat .env.example",
    "cat docs/review/context.md",
    "cat backend/app/core/config.py",
    "grep -rn get_session app/",
    "grep -n environment docs/x.md",
    "head -n 5 README.md",
    "sed -n 1,5p CLAUDE.md",
    "python -c 'print(1)'",
    "python3 scripts/gate.py",
    "ls -a | grep env_example",
    "echo '.env is ignored by git'",
    "cat .environment",
    "ssh-keygen -t ed25519",
    "scripts/gate.sh --full",
    "psql -c 'select 1'",
    "curl -s localhost:9200",
    "cat <<'EOF'\nit's fine; docker volume rm v\nEOF",
    "python3 - <<'PY'\nprint(\"don't\")\nPY",
    "cat > f.py <<'EOF'\nx = 'git reset --hard'\nEOF\nuv run pytest",
    "cat > f <<'EOF'\nit's a file; don't 'quote' me: docker compose down -v\nEOF",
    "git commit -m \"$(cat <<'EOF'\nfix: don't drop it's data\n\nbody mentions docker compose down -v\nEOF\n)\"",
    "docker volume inspect helphub_pgdata",
    "docker system df",
    "docker system info",
    "docker image prune -f",
    "",
]


@pytest.mark.parametrize("command", BLOCKED)
def test_blocked(command: str) -> None:
    assert guard.check(command) is not None, command


@pytest.mark.parametrize("command", ALLOWED)
def test_allowed(command: str) -> None:
    assert guard.check(command) is None, (command, guard.check(command))


def _run(payload: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_exit_code_2_and_stderr_reason_when_blocked() -> None:
    result = _run(json.dumps({"tool_input": {"command": "git reset --hard"}}))
    assert result.returncode == 2
    assert "reset --hard" in result.stderr
    assert result.stdout == ""


def test_exit_code_0_and_silent_when_allowed() -> None:
    result = _run(json.dumps({"tool_input": {"command": "uv run pytest"}}))
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


@pytest.mark.parametrize(
    "payload",
    ["not json", "", "[]", '"a string"', "null", '{"tool_input": "x"}',
     '{"tool_input": {"command": 5}}'],
)  # fmt: skip
def test_unreadable_input_fails_closed(payload: str) -> None:
    result = _run(payload)
    assert result.returncode == 2
    assert "guard_bash" in result.stderr
    assert result.stdout == ""


def test_unparseable_command_is_blocked_with_exit_2() -> None:
    result = _run(json.dumps({"tool_input": {"command": "echo 'oops"}}))
    assert result.returncode == 2
    assert "unparseable" in result.stderr


def test_missing_command_is_allowed() -> None:
    assert _run(json.dumps({"tool_input": {}})).returncode == 0
