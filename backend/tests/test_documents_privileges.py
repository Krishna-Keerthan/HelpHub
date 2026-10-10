import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


@pytest.mark.parametrize("table", ["documents", "chunks"])
@pytest.mark.parametrize("privilege", ["SELECT", "INSERT", "UPDATE", "DELETE"])
async def test_app_role_has_document_table_privileges(
    owner_conn: AsyncConnection, table: str, privilege: str
) -> None:
    result = await owner_conn.execute(
        text("SELECT has_table_privilege('helphub_app', :table, :privilege)"),
        {"table": f"public.{table}", "privilege": privilege},
    )
    assert result.scalar_one() is True, f"helphub_app lacks {privilege} on {table}"
