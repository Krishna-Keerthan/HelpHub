"""Create and remove the evaluation's throw-away tenant and Elasticsearch indices.

Everything the harness deletes is identified by an id or index name that the
run itself recorded in the journal (see ``eval.journal``); there is no deletion
by pattern here. Cleanup errors are collected, never swallowed: they are
attached to the run's own exception, or raised as ``CleanupFailed``.
"""

import secrets
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.db.repositories import tenants as tenants_repo
from app.schemas.auth import RegisterRequest
from app.services import auth as auth_service
from app.services import es_index
from eval import guard, journal

HARNESS_EMAIL_SUFFIX = "@eval-harness.example.com"
HARNESS_EMAIL = f"admin{HARNESS_EMAIL_SUFFIX}"

DeleteTenant = Callable[[uuid.UUID], Awaitable[None]]
VerifyTenant = Callable[[uuid.UUID], Awaitable[bool]]


class CleanupFailed(RuntimeError):
    """Cleanup left resources behind (G14)."""


class ActiveRun(RuntimeError):
    """The journal belongs to a run that is still alive."""


@dataclass
class CleanupStatus:
    tenant_deleted: bool
    indices_deleted: bool
    errors: list[BaseException] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.tenant_deleted and self.indices_deleted and not self.errors

    def line(self) -> str:
        yes = {True: "yes", False: "no"}
        return (
            f"cleanup: tenant deleted={yes[self.tenant_deleted]}, "
            f"indices deleted={yes[self.indices_deleted]}"
        )


@dataclass
class EvalRun:
    slug: str
    prefix: str
    tenant_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None


async def _delete_tenant(tenant_id: uuid.UUID) -> None:
    await tenants_repo.delete_by_ids([tenant_id])


async def _tenant_gone(tenant_id: uuid.UUID) -> bool:
    return tenant_id not in await tenants_repo.existing_ids([tenant_id])


async def remove_run(
    *,
    prefix: str,
    tenant_id: uuid.UUID | None,
    es: Any,
    delete_tenant: DeleteTenant | None = None,
    verify_tenant: VerifyTenant | None = None,
) -> CleanupStatus:
    """Remove the run's indices, then its tenant; each step runs regardless of
    the other. Returns what happened and every error that occurred."""
    status = CleanupStatus(tenant_deleted=tenant_id is None, indices_deleted=False)
    try:
        found = await es.indices.get(
            index=f"{prefix}*", ignore_unavailable=True, allow_no_indices=True
        )
        if found:
            await es.indices.delete(index=list(found), ignore_unavailable=True)
        status.indices_deleted = True
    except Exception as exc:  # noqa: BLE001 - collected, re-raised by the caller
        status.errors.append(exc)
    if tenant_id is not None:
        try:
            await (delete_tenant or _delete_tenant)(tenant_id)
            status.tenant_deleted = verify_tenant is None or await verify_tenant(
                tenant_id
            )
        except Exception as exc:  # noqa: BLE001
            status.errors.append(exc)
    return status


async def teardown(
    *,
    keep: bool,
    prefix: str,
    tenant_id: uuid.UUID | None,
    raw_es: Any,
    es: Any,
    delete_tenant: DeleteTenant | None = None,
    verify_tenant: VerifyTenant | None = None,
) -> CleanupStatus:
    """Cleanup with a status line that is always printed. With several errors the
    first is raised and the others are attached to it as notes."""
    if keep:
        print(f"--keep: tenant {tenant_id}, prefix {prefix} retained")
        return CleanupStatus(tenant_deleted=True, indices_deleted=True)
    del raw_es  # every call goes through the one guarded client
    status = await remove_run(
        prefix=prefix,
        tenant_id=tenant_id,
        es=es,
        delete_tenant=delete_tenant,
        verify_tenant=verify_tenant,
    )
    print(status.line())
    if status.errors:
        first, *others = status.errors
        for other in others:
            first.add_note(f"also during cleanup: {type(other).__name__}")
        raise first
    return status


async def clean_entry(entry: journal.Entry, es: Any) -> CleanupStatus:
    """Clean exactly what a (stale) journal records."""
    tenant_id = entry.tenant_uuid() or await tenants_repo.id_for_slug(entry.slug)
    status = await teardown(
        keep=False,
        prefix=entry.es_prefix,
        tenant_id=tenant_id,
        raw_es=es,
        es=es,
        verify_tenant=_tenant_gone,
    )
    return status


async def startup_cleanup(es: Any, path: Path) -> bool:
    """Clean a crashed run's recorded resources. Returns True when it did."""
    entry = journal.read(path)
    if entry is None:
        return False
    if journal.pid_alive(entry.pid):
        raise ActiveRun(f"journal belongs to a live run (pid {entry.pid})")
    print(f"stale journal from pid {entry.pid}: cleaning its recorded ids")
    status = await clean_entry(entry, es)
    if not status.ok:
        raise CleanupFailed(f"G14: stale journal not cleaned ({status.line()})")
    journal.remove(path)
    return True


@asynccontextmanager
async def eval_run(
    es: Any, *, keep: bool = False, path: Path = journal.JOURNAL_PATH
) -> AsyncIterator[EvalRun]:
    """Own ES prefix, journal and tenant for one run; always cleaned up."""
    guard.assert_not_production()
    await startup_cleanup(es, path)
    token = uuid.uuid4().hex[:12]
    run = EvalRun(slug=f"eval-{token}", prefix=f"eval-{token}-")
    previous_prefix = settings.es_index_prefix
    settings.es_index_prefix = run.prefix
    es_index.reset_ensure_cache()
    body_error: BaseException | None = None
    try:
        guard.assert_eval_prefix()
        entry = journal.new_entry(run.slug, run.prefix)
        journal.write(entry, path)
        user, _ = await auth_service.register_tenant(
            RegisterRequest(
                tenant_name=run.slug,
                tenant_slug=run.slug,
                email=HARNESS_EMAIL,
                password=secrets.token_urlsafe(24),
            ),
            reserved_ok=True,
        )
        run.tenant_id, run.user_id = user.tenant_id, user.id
        journal.write(
            journal.Entry(
                entry.slug,
                entry.es_prefix,
                entry.pid,
                entry.started_at,
                str(user.tenant_id),
            ),
            path,
        )
        yield run
    except BaseException as exc:
        body_error = exc
        raise
    finally:
        try:
            tenant_id = run.tenant_id
            if tenant_id is None and not keep:  # creation may have half-succeeded
                tenant_id = await tenants_repo.id_for_slug(run.slug)
            status = await teardown(
                keep=keep,
                prefix=run.prefix,
                tenant_id=tenant_id,
                raw_es=es,
                es=es,
                verify_tenant=_tenant_gone,
            )
            if status.ok and not keep:
                journal.remove(path)
        except BaseException as cleanup_error:
            if body_error is not None:
                body_error.add_note(
                    f"cleanup also failed: {type(cleanup_error).__name__}"
                )
            else:
                raise CleanupFailed(
                    f"G14: eval cleanup failed ({type(cleanup_error).__name__})"
                ) from cleanup_error
        finally:
            es_index.reset_ensure_cache()
            settings.es_index_prefix = previous_prefix


async def scoped_leaks(
    es: Any, prefix: str, tenant_ids: Sequence[uuid.UUID]
) -> dict[str, int]:
    """Leftovers of exactly this run (tenant ids and index prefix)."""
    found = await es.indices.get(
        index=f"{prefix}*", ignore_unavailable=True, allow_no_indices=True
    )
    return {
        "run tenants": len(await tenants_repo.existing_ids(list(tenant_ids))),
        "run indices": len(found),
    }


async def global_counts(es: Any) -> dict[str, int]:
    """Informational only: every eval- tenant and index, whatever its origin."""
    found = await es.indices.get(
        index="eval-*", ignore_unavailable=True, allow_no_indices=True
    )
    return {
        "eval tenants (all)": await tenants_repo.count_slug_prefix("eval-"),
        "eval indices (all)": len(found),
    }
