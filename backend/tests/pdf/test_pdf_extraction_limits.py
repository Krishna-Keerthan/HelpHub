"""PDF text extraction runs under hard limits: wall-clock timeout (worker
killed), memory limit, character cap, and no secrets in the worker."""

import asyncio
import os
import time
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import settings
from tests.conftest import MakeTenant, SeededTenant, auth_headers
from tests.helpers.pdf_helpers import text_operator_bomb, text_pdf

# ~600k text operators: a ~8 KB file that costs ~8 s of extraction CPU.
BOMB_OPERATORS = 600_000


async def _upload(client: AsyncClient, tenant: SeededTenant, data: bytes):
    return await client.post(
        "/documents/upload",
        files={"file": ("doc.pdf", data, "application/pdf")},
        headers=auth_headers(tenant),
    )


async def _document_count(owner_conn: AsyncConnection, tenant_id) -> int:
    result = await owner_conn.execute(
        text("SELECT count(*) FROM documents WHERE tenant_id = :tid"),
        {"tid": tenant_id},
    )
    count = result.scalar_one()
    await owner_conn.rollback()
    return count


def _live_pdf_workers() -> list[int]:
    """Child processes of this test process running the PDF worker."""
    me = str(os.getpid())
    workers = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            stat = (proc / "stat").read_text()
            cmdline = (proc / "cmdline").read_bytes()
        except OSError:
            continue
        ppid = stat.rsplit(")", 1)[1].split()[1]
        if ppid == me and b"pdf_worker" in cmdline:
            workers.append(int(proc.name))
    return workers


async def test_slow_pdf_is_cut_off_and_worker_killed(
    monkeypatch: pytest.MonkeyPatch,
    client: AsyncClient,
    owner_conn: AsyncConnection,
    make_tenant: MakeTenant,
) -> None:
    monkeypatch.setattr(settings, "pdf_timeout_seconds", 1.0)
    # CPU limit out of the way: only the wall-clock timeout can stop it.
    monkeypatch.setattr(settings, "pdf_cpu_seconds", 60)
    tenant = await make_tenant()
    bomb = text_operator_bomb(BOMB_OPERATORS)
    assert len(bomb) < 20_000  # tiny upload, far below the size cap

    started = time.monotonic()
    response = await _upload(client, tenant, bomb)
    elapsed = time.monotonic() - started

    assert response.status_code == 422, response.text
    assert elapsed < 4.0, f"extraction was not cut off ({elapsed:.1f}s)"
    assert await _document_count(owner_conn, tenant["id"]) == 0
    await asyncio.sleep(0.2)  # let the kernel reap it
    assert _live_pdf_workers() == []


async def test_worker_cpu_limit_is_enforced(
    monkeypatch: pytest.MonkeyPatch,
    client: AsyncClient,
    owner_conn: AsyncConnection,
    make_tenant: MakeTenant,
) -> None:
    # Wall-clock timeout out of the way: only RLIMIT_CPU can stop it.
    monkeypatch.setattr(settings, "pdf_timeout_seconds", 60.0)
    monkeypatch.setattr(settings, "pdf_cpu_seconds", 1)
    tenant = await make_tenant()

    started = time.monotonic()
    response = await _upload(client, tenant, text_operator_bomb(BOMB_OPERATORS))
    elapsed = time.monotonic() - started

    assert response.status_code == 422, response.text
    assert elapsed < 4.0, f"CPU limit did not stop the worker ({elapsed:.1f}s)"
    assert await _document_count(owner_conn, tenant["id"]) == 0


async def test_worker_memory_limit_is_enforced(
    monkeypatch: pytest.MonkeyPatch,
    client: AsyncClient,
    owner_conn: AsyncConnection,
    make_tenant: MakeTenant,
) -> None:
    # Far below what a Python interpreter plus pypdf needs: the worker must
    # fail inside its own limit, and the upload is rejected cleanly.
    monkeypatch.setattr(settings, "pdf_memory_bytes", 32 * 1024 * 1024)
    tenant = await make_tenant()

    response = await _upload(client, tenant, text_pdf("Perfectly normal text."))

    assert response.status_code == 422, response.text
    assert await _document_count(owner_conn, tenant["id"]) == 0


async def test_extraction_stops_at_first_page_over_the_limit(
    monkeypatch: pytest.MonkeyPatch,
    client: AsyncClient,
    owner_conn: AsyncConnection,
    make_tenant: MakeTenant,
) -> None:
    # 20 pages x ~0.7 s each: only stopping after page 1 finishes in time.
    monkeypatch.setattr(settings, "max_document_chars", 1000)
    monkeypatch.setattr(settings, "pdf_timeout_seconds", 5.0)
    monkeypatch.setattr(settings, "pdf_cpu_seconds", 60)
    tenant = await make_tenant()

    started = time.monotonic()
    response = await _upload(client, tenant, text_operator_bomb(50_000, pages=20))
    elapsed = time.monotonic() - started

    assert response.status_code == 413, response.text
    assert elapsed < 4.0, f"extraction continued past the limit ({elapsed:.1f}s)"
    assert await _document_count(owner_conn, tenant["id"]) == 0


async def test_extracted_text_over_document_limit_is_413(
    monkeypatch: pytest.MonkeyPatch,
    client: AsyncClient,
    owner_conn: AsyncConnection,
    make_tenant: MakeTenant,
) -> None:
    monkeypatch.setattr(settings, "max_document_chars", 50)
    tenant = await make_tenant()
    pdf = text_pdf(*(f"Page {i} has some ordinary sentence text." for i in range(20)))

    response = await _upload(client, tenant, pdf)

    assert response.status_code == 413, response.text
    assert await _document_count(owner_conn, tenant["id"]) == 0


async def test_worker_gets_no_secrets(
    monkeypatch: pytest.MonkeyPatch, client: AsyncClient, make_tenant: MakeTenant
) -> None:
    # Plant secrets in this process's environment: the worker must not see
    # them even when they are there.
    planted = {
        "DATABASE_URL": "postgresql://planted:planted-db-secret@h/db",
        "MIGRATION_DATABASE_URL": "postgresql://planted:planted-owner-secret@h/db",
        "JWT_SECRET": "planted-jwt-secret-" + "z" * 32,
    }
    for name, value in planted.items():
        monkeypatch.setenv(name, value)
    seen_envs: list[dict[str, str]] = []
    original = asyncio.create_subprocess_exec

    async def spy(*args, **kwargs):
        seen_envs.append(dict(kwargs.get("env") or {}))
        return await original(*args, **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)
    tenant = await make_tenant()

    response = await _upload(client, tenant, text_pdf("Normal text for the worker."))

    assert response.status_code == 201, response.text
    assert len(seen_envs) == 1, "PDF extraction did not run in a subprocess"
    env = seen_envs[0]
    assert set(env) <= {"PATH", "LANG"}, sorted(env)
    for value in (*planted.values(), settings.jwt_secret, settings.database_url):
        assert value not in env.values()
