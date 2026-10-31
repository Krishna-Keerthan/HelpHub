"""scripts/check_local_db.py output format, on constructed values (no .env, no connection)."""

import importlib.util
import os
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_local_db.py"
SECRET = "s3cr3t-pw"


def load():
    spec = importlib.util.spec_from_file_location("check_local_db", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = load()


@pytest.fixture(autouse=True)
def keep_session_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """main() pops the two URLs from os.environ (dotenv_urls). Without this, they stay
    gone for the rest of the session, and the nested pytest children of
    test_session_guards.py cannot load settings when there is no .env (CI)."""
    for name in mod.VARIABLES:
        if name in os.environ:
            monkeypatch.setenv(name, os.environ[name])
        else:
            monkeypatch.delenv(name, raising=False)


def url(host: str) -> str:
    return f"postgresql+asyncpg://u:{SECRET}@{host}:5432/app"


def test_no_url_host_or_password_in_the_output() -> None:
    lines = mod.render(
        {
            "DATABASE_URL": url("db.abc.supabase.co"),
            "MIGRATION_DATABASE_URL": url("example.com"),
        },
        {"DATABASE_URL": url("127.0.0.1"), "MIGRATION_DATABASE_URL": url("postgres")},
    )
    text = "\n".join(lines)
    for leaked in (SECRET, "supabase.co", "example.com", "postgresql", "127.0.0.1"):
        assert leaked not in text


def test_ok_only_when_every_line_is_local_or_unset() -> None:
    local = url("localhost")
    assert mod.ok(mod.render({"DATABASE_URL": local}, {"DATABASE_URL": local}))
    assert not mod.ok(mod.render({"DATABASE_URL": url("example.com")}, {}))
    assert not mod.ok(mod.render({}, {"MIGRATION_DATABASE_URL": url("x.pooler.y")}))


# --- settings that fail to load, and the loader behind both guards ------------------------


class _Secret:
    def __init__(self, value: str) -> None:
        self._value = value

    def get_secret_value(self) -> str:
        return self._value


class _LeakyError(ValueError):
    pass
