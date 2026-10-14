"""The shared-database lock: the same flock pytest takes (tests/conftest.py)."""

import fcntl
import os
from collections.abc import Iterator
from contextlib import contextmanager

DEFAULT_LOCK_FILE = "/tmp/helphub-pytest.lock"  # noqa: S108 - single-user dev box


class LockHeld(RuntimeError):
    """Another pytest session or evaluation holds the database lock."""


@contextmanager
def hold_lock(path: str | None = None) -> Iterator[None]:
    path = path or os.environ.get("HELPHUB_PYTEST_LOCK_FILE", DEFAULT_LOCK_FILE)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        raise LockHeld("another pytest session or evaluation is running") from None
    try:
        yield
    finally:
        os.close(fd)  # closing drops the flock
