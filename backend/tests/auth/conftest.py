from collections.abc import Iterator

import pytest

from app.core.config import settings


@pytest.fixture
def registration_open(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Public registration is off by default; tests of that route opt in."""
    monkeypatch.setattr(settings, "allow_public_registration", True)
    yield
