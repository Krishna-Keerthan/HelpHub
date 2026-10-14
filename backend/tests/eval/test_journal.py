"""The active-run journal: atomic writes, strict reads, pid liveness."""

import json
import os
from pathlib import Path

import pytest

from eval import journal

ENTRY = journal.Entry(
    slug="eval-0123456789ab",
    es_prefix="eval-0123456789ab-",
    pid=4242,
    started_at="2026-10-14T00:00:00+00:00",
    tenant_id="00000000-0000-0000-0000-000000000007",
)


def test_round_trip_leaves_no_temporary_file(tmp_path: Path) -> None:
    path = tmp_path / "results" / ".eval-active.json"
    journal.write(ENTRY, path)
    assert journal.read(path) == ENTRY
    assert [p.name for p in path.parent.iterdir()] == [".eval-active.json"]
    journal.write(journal.Entry(**{**ENTRY.__dict__, "tenant_id": None}), path)
    assert journal.read(path) is not None
    journal.remove(path)
    journal.remove(path)  # removing twice is fine
    assert journal.read(path) is None


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        "{}",
        json.dumps({**ENTRY.__dict__, "slug": "eval-corp"}),
        json.dumps({**ENTRY.__dict__, "es_prefix": "chunks"}),
        json.dumps({**ENTRY.__dict__, "tenant_id": "nope"}),
    ],
)
def test_an_untrustworthy_journal_is_an_error(tmp_path: Path, content: str) -> None:
    path = tmp_path / "j.json"
    path.write_text(content)
    with pytest.raises(journal.JournalError):
        journal.read(path)


def test_pid_liveness(dead_pid: int) -> None:
    assert journal.pid_alive(os.getpid())
    assert not journal.pid_alive(dead_pid)
    assert not journal.pid_alive(0)
