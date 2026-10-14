"""Standalone cleanup: dry run by default, candidates only, explicit ids."""

import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest

from app.core.config import settings
from app.db.repositories import tenants as tenants_repo
from eval import cleanup, guard, journal, lifecycle, run_eval, validate

SUFFIX = lifecycle.HARNESS_EMAIL_SUFFIX
Make = Callable[..., Awaitable[uuid.UUID]]


class FakeIndices:
    def __init__(self) -> None:
        self.deleted: list[Any] = []

    async def get(self, **kwargs: Any) -> dict[str, Any]:
        return {}

    async def delete(self, **kwargs: Any) -> None:
        self.deleted.append(kwargs["index"])


class FakeEs:
    def __init__(self) -> None:
        self.indices = FakeIndices()


def _slug() -> str:
    return f"eval-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def only(monkeypatch: pytest.MonkeyPatch) -> Callable[[set[uuid.UUID]], None]:
    """Restrict the candidates to the test's own tenants (the database may hold
    other leftovers), and skip index discovery."""

    def _only(ids: set[uuid.UUID]) -> None:
        real = cleanup.candidates

        async def filtered() -> list[tenants_repo.TenantRef]:
            return [c for c in await real() if c.id in ids]

        async def no_indices(_: Any) -> list[str]:
            return []

        monkeypatch.setattr(cleanup, "candidates", filtered)
        monkeypatch.setattr(cleanup, "stale_run_indices", no_indices)

    return _only


async def test_dry_run_deletes_nothing(
    make: Make, only: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a = await make(_slug(), [f"admin{SUFFIX}"])
    only({a})
    summary = await cleanup.cleanup(FakeEs(), yes=False, path=tmp_path / "j.json")
    assert summary.tenants_removed == 0
    assert str(a) in capsys.readouterr().out  # listed
    assert await tenants_repo.existing_ids([a]) == {a}


async def test_yes_deletes_only_candidates(
    make: Make, only: Any, tmp_path: Path
) -> None:
    candidate = await make(_slug(), [f"admin{SUFFIX}"])
    normal_user = await make("eval-corp", ["admin@acme.example.com"])
    foreign_user = await make(_slug(), [f"admin{SUFFIX}", "x@acme.example.com"])
    young = await make(_slug(), [f"admin{SUFFIX}"], age_minutes=1)
    only({candidate, normal_user, foreign_user, young})
    summary = await cleanup.cleanup(FakeEs(), yes=True, path=tmp_path / "j.json")
    assert summary.tenants_removed == 1 and summary.failures == []
    assert await tenants_repo.existing_ids(
        [candidate, normal_user, foreign_user, young]
    ) == {normal_user, foreign_user, young}


async def test_a_failing_tenant_does_not_hide_the_others(
    make: Make, only: Any, tmp_path: Path
) -> None:
    a = await make(_slug(), [f"admin{SUFFIX}"])
    b = await make(_slug(), [f"admin{SUFFIX}"])
    only({a, b})

    async def flaky(ids: list[uuid.UUID]) -> int:
        if ids == [a]:
            raise TimeoutError("db down")
        return await tenants_repo.delete_by_ids(ids)

    summary = await cleanup.cleanup(
        FakeEs(), yes=True, path=tmp_path / "j.json", delete_ids=flaky
    )
    assert summary.tenants_removed == 1
    assert summary.failures == [f"tenant {a}: TimeoutError"]
    assert await tenants_repo.existing_ids([a, b]) == {a}


async def test_journal_path_deletes_exactly_the_recorded_id(
    make: Make, tmp_path: Path, dead_pid: int
) -> None:
    recorded = await make(_slug(), [f"admin{SUFFIX}"], age_minutes=1)
    bystander = await make(_slug(), [f"admin{SUFFIX}"])  # a candidate, not recorded
    path = tmp_path / "j.json"
    journal.write(
        journal.Entry(
            "eval-0123456789ab",
            "eval-0123456789ab-",
            dead_pid,
            "2026-10-14T00:00:00+00:00",
            str(recorded),
        ),
        path,
    )
    assert await lifecycle.startup_cleanup(FakeEs(), path) is True
    assert await tenants_repo.existing_ids([recorded, bystander]) == {bystander}
    assert not path.exists()


@pytest.mark.parametrize("entry", [cleanup.main, run_eval.main, validate.main])
def test_entry_points_refuse_production(
    entry: Callable[[], int], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr("sys.argv", ["x"])
    assert entry() == 2
    with pytest.raises(guard.ProductionRefused):
        guard.assert_not_production()
