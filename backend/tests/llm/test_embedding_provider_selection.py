"""settings.embedding_provider picks the process-wide provider."""

import pytest
from pydantic import SecretStr

from app.core.config import settings
from app.services import embeddings
from app.services.embeddings_cloudflare import CloudflareEmbeddingProvider


@pytest.fixture(autouse=True)
def fresh_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(embeddings, "_provider", None)


def test_cloudflare_setting_selects_the_hosted_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "embedding_provider", "cloudflare")
    monkeypatch.setattr(settings, "cloudflare_account_id", SecretStr("a"))
    monkeypatch.setattr(settings, "cloudflare_api_token", SecretStr("t"))
    provider = embeddings.default_provider()
    assert isinstance(provider, CloudflareEmbeddingProvider)
    assert embeddings.default_provider() is provider  # one per process
