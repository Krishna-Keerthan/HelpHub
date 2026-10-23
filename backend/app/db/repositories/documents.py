import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import Select, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.db.models import Document

# Named in migration 0004; ON CONFLICT targets it by name so a rename fails loudly.
CONTENT_HASH_CONSTRAINT = "uq_documents_tenant_id_content_hash"


@dataclass(frozen=True)
class NewDocument:
    title: str
    raw_text: str
    content_hash: str
    created_by: uuid.UUID


async def insert_if_absent(
    session: AsyncSession, tenant_id: uuid.UUID, new: NewDocument
) -> Document | None:
    """Insert a PENDING document; None if the tenant already has this hash."""
    stmt = (
        pg_insert(Document)
        .values(
            tenant_id=tenant_id,
            title=new.title,
            raw_text=new.raw_text,
            content_hash=new.content_hash,
            created_by=new.created_by,
        )
        .on_conflict_do_nothing(constraint=CONTENT_HASH_CONSTRAINT)
        .returning(Document)
    )
    return (await session.scalars(stmt)).one_or_none()


async def get(
    session: AsyncSession, tenant_id: uuid.UUID, document_id: uuid.UUID
) -> Document | None:
    result = await session.scalars(
        select(Document).where(
            Document.tenant_id == tenant_id, Document.id == document_id
        )
    )
    return result.one_or_none()


async def get_by_hash(
    session: AsyncSession, tenant_id: uuid.UUID, content_hash: str
) -> Document | None:
    result = await session.scalars(
        select(Document).where(
            Document.tenant_id == tenant_id, Document.content_hash == content_hash
        )
    )
    return result.one_or_none()


async def get_for_update(
    session: AsyncSession, tenant_id: uuid.UUID, document_id: uuid.UUID
) -> Document | None:
    """Lock the document row until the end of the transaction.

    populate_existing: under READ COMMITTED a waiter must see the row as the
    lock holder committed it, not a stale copy from the identity map.
    """
    result = await session.scalars(
        select(Document)
        .where(Document.tenant_id == tenant_id, Document.id == document_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return result.one_or_none()


async def set_status(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    status: str,
    *,
    error: str | None = None,
) -> Document | None:
    """Set status and error; returns the refreshed row (None if not visible).

    updated_at is set explicitly: the ORM onupdate does not fire for Core-style
    UPDATE statements.
    """
    result = await session.scalars(
        update(Document)
        .where(Document.tenant_id == tenant_id, Document.id == document_id)
        .values(status=status, error=error, updated_at=func.now())
        .returning(Document)
        .execution_options(synchronize_session=False, populate_existing=True)
    )
    return result.one_or_none()


async def list_for_tenant(
    session: AsyncSession, tenant_id: uuid.UUID, *, limit: int, offset: int
) -> list[Document]:
    """Newest first; raw_text is never loaded."""
    result = await session.scalars(
        select(Document)
        .options(defer(Document.raw_text, raiseload=True))
        .where(Document.tenant_id == tenant_id)
        .order_by(Document.created_at.desc(), Document.id)
        .limit(limit)
        .offset(offset)
    )
    return list(result)


def titles_statement(
    tenant_id: uuid.UUID, document_ids: Sequence[uuid.UUID]
) -> Select[tuple[uuid.UUID, str]]:
    return select(Document.id, Document.title).where(
        Document.tenant_id == tenant_id, Document.id.in_(document_ids)
    )


async def titles_for(
    session: AsyncSession, tenant_id: uuid.UUID, document_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, str]:
    if not document_ids:
        return {}
    rows = await session.execute(titles_statement(tenant_id, document_ids))
    return {doc_id: title for doc_id, title in rows}


async def get_metadata(
    session: AsyncSession, tenant_id: uuid.UUID, document_id: uuid.UUID
) -> Document | None:
    """Like ``get`` but raw_text is never loaded."""
    result = await session.scalars(
        select(Document)
        .options(defer(Document.raw_text, raiseload=True))
        .where(Document.tenant_id == tenant_id, Document.id == document_id)
    )
    return result.one_or_none()


async def delete_document(
    session: AsyncSession, tenant_id: uuid.UUID, document_id: uuid.UUID
) -> bool:
    """Delete one document (chunks cascade); False if not visible."""
    result = await session.execute(
        delete(Document).where(
            Document.tenant_id == tenant_id, Document.id == document_id
        )
    )
    return result.rowcount == 1
