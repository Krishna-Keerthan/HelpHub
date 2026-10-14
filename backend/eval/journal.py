"""The active-run journal: what the evaluation created, so cleanup can delete
exactly that and nothing else.

``eval/results/.eval-active.json`` (gitignored) is written atomically as soon as
the run's names exist, updated once the tenant id is known, and removed only
after cleanup was verified. A journal whose pid is no longer alive belongs to a
crashed run; its recorded ids are the only things a later run cleans up.
"""

import contextlib
import json
import os
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
JOURNAL_PATH = EVAL_DIR / "results" / ".eval-active.json"
SLUG_RE = re.compile(r"^eval-[0-9a-f]{12}$")
PREFIX_RE = re.compile(r"^eval-[0-9a-f]{12}-$")


class JournalError(RuntimeError):
    """The journal exists but cannot be trusted; nothing is deleted from it."""


@dataclass(frozen=True)
class Entry:
    slug: str
    es_prefix: str
    pid: int
    started_at: str
    tenant_id: str | None = None

    def tenant_uuid(self) -> uuid.UUID | None:
        return uuid.UUID(self.tenant_id) if self.tenant_id else None


def new_entry(slug: str, prefix: str) -> Entry:
    return Entry(slug, prefix, os.getpid(), datetime.now(UTC).isoformat())


def write(entry: Entry, path: Path = JOURNAL_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    with tmp.open("w") as handle:
        handle.write(json.dumps(asdict(entry), sort_keys=True))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def read(path: Path = JOURNAL_PATH) -> Entry | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        entry = Entry(
            slug=str(data["slug"]),
            es_prefix=str(data["es_prefix"]),
            pid=int(data["pid"]),
            started_at=str(data["started_at"]),
            tenant_id=None if data.get("tenant_id") is None else str(data["tenant_id"]),
        )
        entry.tenant_uuid()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise JournalError(f"unreadable journal ({type(exc).__name__})") from None
    if not SLUG_RE.match(entry.slug) or not PREFIX_RE.match(entry.es_prefix):
        raise JournalError("journal names are outside the eval- run format")
    return entry


def remove(path: Path = JOURNAL_PATH) -> None:
    with contextlib.suppress(FileNotFoundError):
        path.unlink()


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
