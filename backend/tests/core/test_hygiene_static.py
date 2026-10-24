"""Static guards: worker isolation, tenant-bound statements, no planner flags."""

import re
import subprocess
import sys
from pathlib import Path

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
