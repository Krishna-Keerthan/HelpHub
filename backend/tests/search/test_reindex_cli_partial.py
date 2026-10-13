"""--allow-partial only skips the pre-swap abort; the CLI must still report the
failed documents and exit non-zero, so a partial rebuild cannot look green."""

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from app.services import reindex

CLI_PATH = Path(__file__).resolve().parents[2] / "scripts" / "reindex.py"


def load_cli() -> ModuleType:
    spec = importlib.util.spec_from_file_location("reindex_cli_under_test", CLI_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def cli(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    module = load_cli()

    async def no_close() -> None:
        return None

    monkeypatch.setattr(module, "get_es", lambda: object())
    monkeypatch.setattr(module, "close_es", no_close)
    return module


async def test_allow_partial_with_failures_exits_nonzero_and_prints_the_count(
    cli: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: dict[str, Any] = {}

    async def partial(
        es: object, *, allow_partial: bool = False
    ) -> reindex.ReindexSummary:
        seen["allow_partial"] = allow_partial
        return reindex.ReindexSummary(documents=3, indexed=2, failed=1)

    monkeypatch.setattr(cli.reindex, "reindex_all", partial)
    code = await cli.main(cli.parse_args(["--all", "--allow-partial"]))

    assert seen["allow_partial"] is True
    assert code == 1
    assert "documents=3 indexed=2 failed=1" in capsys.readouterr().out


async def test_default_run_aborts_with_exit_3(
    cli: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def incomplete(es: object, *, allow_partial: bool = False) -> None:
        assert allow_partial is False
        raise reindex.ReindexIncompleteError(
            reindex.ReindexSummary(documents=3, indexed=2, failed=1)
        )

    monkeypatch.setattr(cli.reindex, "reindex_all", incomplete)
    code = await cli.main(cli.parse_args(["--all"]))

    assert code == 3
    assert "alias not swapped" in capsys.readouterr().err


async def test_clean_run_exits_zero(
    cli: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def clean(
        es: object, *, allow_partial: bool = False
    ) -> reindex.ReindexSummary:
        return reindex.ReindexSummary(documents=2, indexed=2, failed=0)

    monkeypatch.setattr(cli.reindex, "reindex_all", clean)
    assert await cli.main(cli.parse_args(["--all", "--allow-partial"])) == 0
    assert "failed=0" in capsys.readouterr().out
