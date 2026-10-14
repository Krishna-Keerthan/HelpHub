"""Run life cycle with fakes (no database, no Elasticsearch)."""

import os
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.core.config import settings
from app.db.repositories import tenants as tenants_repo
from app.services import auth as auth_service
from eval import journal, lifecycle

TENANT = uuid.UUID(int=7)
USER = uuid.UUID(int=8)


class FakeIndices:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.deleted: list[Any] = []

    async def get(self, **kwargs: Any) -> dict[str, Any]:
        return {f"{kwargs['index'][:-1]}chunks-v1": {}}

    async def delete(self, **kwargs: Any) -> None:
        if self.fail:
            raise ConnectionError("es down")
        self.deleted.append(kwargs["index"])


class FakeEs:
    def __init__(self, fail: bool = False) -> None:
        self.indices = FakeIndices(fail)


class FakeDb:
    def __init__(self, fail_delete: bool = False) -> None:
        self.fail_delete = fail_delete
        self.deleted: list[list[uuid.UUID]] = []
        self.alive = {TENANT}

    async def register_tenant(self, data: Any, *, reserved_ok: bool = False) -> Any:
        assert reserved_ok and data.email == lifecycle.HARNESS_EMAIL
        return SimpleNamespace(tenant_id=TENANT, id=USER), "token"

    async def delete_by_ids(self, ids: list[uuid.UUID]) -> int:
        if self.fail_delete:
            raise TimeoutError("db down")
        self.deleted.append(list(ids))
        self.alive -= set(ids)
        return len(ids)

    async def existing_ids(self, ids: list[uuid.UUID]) -> set[uuid.UUID]:
        return set(ids) & self.alive

    async def id_for_slug(self, slug: str) -> uuid.UUID | None:
        return None


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> FakeDb:
    fake = FakeDb()
    monkeypatch.setattr(auth_service, "register_tenant", fake.register_tenant)
    for name in ("delete_by_ids", "existing_ids", "id_for_slug"):
        monkeypatch.setattr(tenants_repo, name, getattr(fake, name))
    monkeypatch.setattr(settings, "app_env", "local")
    return fake


async def test_successful_run_cleans_up_and_removes_the_journal(
    db: FakeDb, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path, es = tmp_path / "j.json", FakeEs()
    async with lifecycle.eval_run(es, path=path) as run:
        recorded = journal.read(path)
        assert recorded is not None and recorded.tenant_uuid() == TENANT
        assert recorded.slug == run.slug and recorded.pid == os.getpid()
        assert settings.es_index_prefix == run.prefix
    assert db.deleted == [[TENANT]] and not path.exists()
    assert es.indices.deleted == [[f"{run.prefix}chunks-v1"]]
    assert "tenant deleted=yes, indices deleted=yes" in capsys.readouterr().out


async def test_body_and_cleanup_failures_are_both_visible(
    db: FakeDb, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db.fail_delete = True
    path = tmp_path / "j.json"
    with pytest.raises(ValueError, match="body") as info:
        async with lifecycle.eval_run(FakeEs(), path=path):
            raise ValueError("body")
    assert any("TimeoutError" in note for note in info.value.__notes__)
    assert "tenant deleted=no, indices deleted=yes" in capsys.readouterr().out
    assert path.exists()  # not verified, so the journal stays for the next cleanup


async def test_cleanup_failure_alone_raises_g14(db: FakeDb, tmp_path: Path) -> None:
    db.fail_delete = True
    path = tmp_path / "j.json"
    with pytest.raises(lifecycle.CleanupFailed, match="G14"):
        async with lifecycle.eval_run(FakeEs(fail=True), path=path):  # type: ignore[arg-type]
            pass
    assert path.exists()


async def test_teardown_reports_both_errors_and_always_prints_status(
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def failing_delete(_: uuid.UUID) -> None:
        raise TimeoutError("db down")

    with pytest.raises(ConnectionError) as info:
        await lifecycle.teardown(
            keep=False,
            prefix="eval-0123456789ab-",
            tenant_id=TENANT,
            raw_es=FakeEs(fail=True),
            es=FakeEs(fail=True),
            delete_tenant=failing_delete,
        )
    assert info.value.__notes__ == ["also during cleanup: TimeoutError"]
    assert "tenant deleted=no, indices deleted=no" in capsys.readouterr().out


async def test_a_dead_pids_journal_cleans_exactly_its_recorded_ids(
    db: FakeDb, tmp_path: Path, dead_pid: int
) -> None:
    path, es = tmp_path / "j.json", FakeEs()
    journal.write(
        journal.Entry(
            "eval-0123456789ab",
            "eval-0123456789ab-",
            dead_pid,
            "2026-10-14T00:00:00+00:00",
            str(TENANT),
        ),
        path,
    )
    assert await lifecycle.startup_cleanup(es, path) is True
    assert db.deleted == [[TENANT]] and not path.exists()
    assert es.indices.deleted == [["eval-0123456789ab-chunks-v1"]]


async def test_a_live_pids_journal_is_left_alone(db: FakeDb, tmp_path: Path) -> None:
    path = tmp_path / "j.json"
    journal.write(
        journal.Entry(
            "eval-0123456789ab",
            "eval-0123456789ab-",
            os.getppid(),  # the test runner's parent: alive
            "2026-10-14T00:00:00+00:00",
            str(TENANT),
        ),
        path,
    )
    with pytest.raises(lifecycle.ActiveRun):
        await lifecycle.startup_cleanup(FakeEs(), path)
    assert db.deleted == [] and path.exists()


async def test_production_is_refused_before_anything_happens(
    db: FakeDb, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from eval import guard

    monkeypatch.setattr(settings, "app_env", "production")
    with pytest.raises(guard.ProductionRefused):
        async with lifecycle.eval_run(FakeEs(), path=tmp_path / "j.json"):
            pass
    assert db.deleted == [] and not (tmp_path / "j.json").exists()
