"""Static guards: worker isolation, tenant-bound statements, no planner flags."""

import re
import subprocess
import sys
import uuid
from pathlib import Path

from sqlalchemy.dialects import postgresql

from app.db.repositories import chunks as chunks_repo

APP_DIR = Path(__file__).resolve().parents[2] / "app"
BACKEND = APP_DIR.parent


def test_pdf_worker_does_not_import_app_config_or_db_drivers() -> None:
    code = (
        "import sys, app.services.pdf_worker;"
        "bad = [m for m in sys.modules if m in ('app.core.config','asyncpg',"
        "'sqlalchemy') or m == 'app.db' or m.startswith(('app.db.','sqlalchemy.','asyncpg.'))];"
        "print(','.join(sorted(bad)))"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", code],
        cwd=BACKEND,
        env={"PYTHONPATH": str(BACKEND), "PATH": ""},
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == ""


def test_chunk_list_statement_is_bound_to_tenant_id() -> None:
    tenant_id, document_id = uuid.uuid4(), uuid.uuid4()
    statement = chunks_repo.list_for_document_statement(
        tenant_id, document_id, limit=10, offset=0
    )
    compiled = statement.compile(dialect=postgresql.dialect())
    assert "chunks.tenant_id = " in str(compiled)
    assert tenant_id in compiled.params.values()


def test_no_planner_flags_in_app_source() -> None:
    pattern = re.compile(
        r"enable_sort|enable_bitmapscan|enable_seqscan|enable_indexscan"
    )
    offenders = [
        str(path.relative_to(APP_DIR))
        for path in APP_DIR.rglob("*.py")
        if pattern.search(path.read_text())
    ]
    assert offenders == []
