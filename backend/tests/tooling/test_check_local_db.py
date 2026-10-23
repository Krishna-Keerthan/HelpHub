"""scripts/check_local_db.py output format, on constructed values (no .env, no connection)."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_local_db.py"
SECRET = "s3cr3t-pw"


def load():
    spec = importlib.util.spec_from_file_location("check_local_db", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = load()


def url(host: str) -> str:
    return f"postgresql+asyncpg://u:{SECRET}@{host}:5432/app"


def test_four_lines_in_the_fixed_format() -> None:
    lines = mod.render(
        {"DATABASE_URL": None, "MIGRATION_DATABASE_URL": url("localhost")},
        {
            "DATABASE_URL": url("aws-0.pooler.supabase.com"),
            "MIGRATION_DATABASE_URL": url("example.com"),
        },
    )
    assert lines == [
        "DATABASE_URL (environment): unset",
        "MIGRATION_DATABASE_URL (environment): local",
        "DATABASE_URL (.env only): hosted",
        "MIGRATION_DATABASE_URL (.env only): other",
    ]


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

import sys
import types

import pytest

from tests.helpers import db_guard


class _Secret:
    def __init__(self, value: str) -> None:
        self._value = value

    def get_secret_value(self) -> str:
        return self._value


def _fake_config(monkeypatch: pytest.MonkeyPatch, *, database, migration=None) -> None:
    settings = types.SimpleNamespace(
        database_dsn=_Secret(database),
        migration_database_dsn=_Secret(migration) if migration is not None else None,
    )
    module = types.ModuleType("app.core.config")
    module.settings = settings  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "app.core.config", module)


class _LeakyError(ValueError):
    pass


def _failing_config(monkeypatch: pytest.MonkeyPatch) -> None:
    class Failing(types.ModuleType):
        def __getattr__(self, name: str):
            raise _LeakyError(f"bad value {url('leak.example.com')}")

    monkeypatch.setitem(sys.modules, "app.core.config", Failing("app.core.config"))


def test_render_marks_both_env_lines_error_when_settings_failed() -> None:
    lines = mod.render({"DATABASE_URL": None}, None)
    assert lines == [
        "DATABASE_URL (environment): unset",
        "MIGRATION_DATABASE_URL (environment): unset",
        "DATABASE_URL (.env only): error",
        "MIGRATION_DATABASE_URL (.env only): error",
    ]
    assert not mod.ok(lines)


def test_settings_failure_prints_class_only_and_exits_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _failing_config(monkeypatch)
    assert mod.main() == 1
    captured = capsys.readouterr()
    assert captured.out.count("(.env only): error") == 2
    assert "_LeakyError" in captured.err
    for text in (captured.out, captured.err):
        assert "leak.example.com" not in text and SECRET not in text


def test_guard_refuses_on_settings_failure_without_a_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _failing_config(monkeypatch)
    message = db_guard.current_refusal()
    assert message and "_LeakyError" in message and "settings failed" in message
    assert "leak.example.com" not in message and SECRET not in message


@pytest.mark.parametrize(
    ("database", "migration", "expected", "exit_code"),
    [
        (url("localhost"), url("127.0.0.1"), ["local", "local"], 0),
        (url("db.x.supabase.co"), url("localhost"), ["hosted", "local"], 1),
        (url("example.com"), url("localhost"), ["other", "local"], 1),
        (url("localhost"), None, ["local", "unset"], 0),
        ("", None, ["unset", "unset"], 0),
    ],
)
def test_resolved_settings_cases(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    database: str,
    migration: str | None,
    expected: list[str],
    exit_code: int,
) -> None:
    _fake_config(monkeypatch, database=database, migration=migration)
    assert mod.main() == exit_code
    out = capsys.readouterr().out.splitlines()
    assert [line.rsplit(": ", 1)[1] for line in out[2:]] == expected
    assert SECRET not in "\n".join(out)
    refusal = db_guard.current_refusal()
    assert (refusal is None) == (exit_code == 0 and "unset" not in expected)
