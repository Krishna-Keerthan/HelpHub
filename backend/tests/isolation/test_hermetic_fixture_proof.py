"""The hermetic fixture must refuse a dirty graph instead of testing on it.

An old snapshot held by another backend stops VACUUM from removing a dead
tuple; vacuum_chunks() must then fail and name the holder in its evidence.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from tests.conftest import SeededTenant, insert_chunk, insert_document
from tests.isolation.conftest import vacuum_chunks


async def test_vacuum_chunks_fails_with_evidence_while_a_snapshot_is_held(
    owner_conn: AsyncConnection, two_tenants_seeded: dict[str, SeededTenant]
) -> None:
    ta = two_tenants_seeded["tenant_a"]
    doc = await insert_document(owner_conn, ta["id"], created_by=ta["user_id"])
    chunk_id = await insert_chunk(owner_conn, ta["id"], doc, chunk_index=0)
    await owner_conn.commit()
    await vacuum_chunks()  # clean start

    holder = create_async_engine(settings.migration_database_url, poolclass=NullPool)
    try:
        async with holder.connect() as snapshot:
            await snapshot.execute(
                text("SET application_name = 'proof_snapshot_holder'")
            )
            await snapshot.execute(text("SELECT count(*) FROM chunks"))  # old snapshot
            # A dead tuple that the old snapshot still needs.
            await owner_conn.execute(
                text("UPDATE chunks SET chunk_index = 1 WHERE id = :id"),
                {"id": chunk_id},
            )
            await owner_conn.commit()
            with pytest.raises(pytest.fail.Exception) as excinfo:
                await vacuum_chunks()
            message = str(excinfo.value)
            assert "n_dead_tup=" in message
            assert "proof_snapshot_holder" in message
            assert "idle in transaction" in message
            assert "vacuum_verbose" in message
            await snapshot.rollback()
    finally:
        await holder.dispose()
    await vacuum_chunks()  # snapshot gone: the same call now proves a clean table
