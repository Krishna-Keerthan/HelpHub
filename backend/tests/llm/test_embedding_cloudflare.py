"""CloudflareEmbeddingProvider over httpx.MockTransport: body, batching, retries, errors."""

import json
import logging

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import settings
from app.services import embeddings_cloudflare as cf
from app.services.embeddings import EmbeddingError, EmbeddingUnavailableError

# gate-allow: secret fake values used only by this test
ACCOUNT = "ACCOUNT-ID-FAKE"
TOKEN = "TOKEN-FAKE"
TEXT = "PRIVATE-DOCUMENT-TEXT"


@pytest.fixture(autouse=True)
def creds_and_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    monkeypatch.setattr(settings, "cloudflare_account_id", SecretStr(ACCOUNT))
    monkeypatch.setattr(settings, "cloudflare_api_token", SecretStr(TOKEN))
    monkeypatch.setattr(cf, "neurons_total", 0.0)
    delays: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        delays.append(seconds)

    monkeypatch.setattr(cf, "_sleep", fake_sleep)
    return delays


def ok(request: httpx.Request, neurons: str | None = "1.5") -> httpx.Response:
    texts = json.loads(request.content)["text"]
    headers = {"cf-ai-neurons": neurons} if neurons is not None else {}
    return httpx.Response(
        200,
        json={"result": {"data": [[0.1] * 384 for _ in texts]}, "success": True},
        headers=headers,
    )


def provider(handler) -> tuple[cf.CloudflareEmbeddingProvider, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(wrapped),
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    return cf.CloudflareEmbeddingProvider(client), seen


async def test_body_carries_cls_pooling_and_texts() -> None:
    p, seen = provider(ok)
    vectors = await p.embed_passages(["a", "b"])
    body = json.loads(seen[0].content)
    assert body == {"text": ["a", "b"], "pooling": "cls"}
    assert len(vectors) == 2 and len(vectors[0]) == 384
    assert seen[0].url.path.endswith("/ai/run/@cf/baai/bge-small-en-v1.5")
    assert seen[0].headers["authorization"] == f"Bearer {TOKEN}"


async def test_query_also_sends_cls_pooling() -> None:
    p, seen = provider(ok)
    await p.embed_query("q")
    assert json.loads(seen[0].content) == {"text": ["q"], "pooling": "cls"}


async def test_batches_are_capped_and_order_is_kept() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        texts = json.loads(request.content)["text"]
        data = [[float(t)] + [0.0] * 383 for t in texts]
        return httpx.Response(200, json={"result": {"data": data}})

    p, seen = provider(handler)
    texts = [str(i) for i in range(cf.CLOUDFLARE_BATCH_SIZE * 2 + 1)]
    vectors = await p.embed_passages(texts)
    assert [len(json.loads(r.content)["text"]) for r in seen] == [
        cf.CLOUDFLARE_BATCH_SIZE,
        cf.CLOUDFLARE_BATCH_SIZE,
        1,
    ]
    assert [v[0] for v in vectors] == [float(i) for i in range(len(texts))]
    assert cf.CLOUDFLARE_BATCH_SIZE < 5000


@pytest.mark.parametrize("status", [429, 500, 503])
async def test_retries_on_429_and_5xx_then_succeeds(
    status: int, creds_and_sleep: list[float]
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status) if calls < 3 else ok(request)

    p, seen = provider(handler)
    assert len(await p.embed_query("q")) == 384
    assert len(seen) == 3 and len(creds_and_sleep) == 2


@pytest.mark.parametrize("status", [429, 500])
async def test_gives_up_after_two_retries(status: int) -> None:
    p, seen = provider(lambda r: httpx.Response(status, text=TEXT))
    with pytest.raises(EmbeddingUnavailableError):
        await p.embed_query("q")
    assert len(seen) == 3


@pytest.mark.parametrize("status", [400, 401, 403, 404])
async def test_other_4xx_is_not_retried(status: int) -> None:
    p, seen = provider(lambda r: httpx.Response(status, text=TEXT))
    with pytest.raises(EmbeddingUnavailableError):
        await p.embed_query("q")
    assert len(seen) == 1


async def test_retry_after_header_is_honoured_up_to_the_cap(
    creds_and_sleep: list[float],
) -> None:
    p, _ = provider(lambda r: httpx.Response(429, headers={"retry-after": "99"}))
    with pytest.raises(EmbeddingUnavailableError):
        await p.embed_query("q")
    assert creds_and_sleep == [cf.MAX_RETRY_AFTER_SECONDS] * 2


async def test_network_errors_and_timeouts_are_retried_then_generic() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout(f"{TEXT} {ACCOUNT}", request=request)

    p, seen = provider(handler)
    with pytest.raises(EmbeddingUnavailableError) as info:
        await p.embed_query("q")
    assert len(seen) == 3
    assert info.value.__cause__ is None and info.value.__suppress_context__ is False
    assert str(info.value) == "embedding provider unavailable"


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"success": True}),
        httpx.Response(200, json={"result": {"data": [[0.1] * 383]}}),
        httpx.Response(200, json={"result": {"data": []}}),
    ],
)
async def test_bad_payload_is_generic_unavailable(response: httpx.Response) -> None:
    p, _ = provider(lambda r: response)
    with pytest.raises(EmbeddingUnavailableError):
        await p.embed_query("q")


def test_unavailable_is_an_embedding_error_with_a_fixed_message() -> None:
    assert issubclass(EmbeddingUnavailableError, EmbeddingError)
    assert str(EmbeddingUnavailableError()) == "embedding provider unavailable"


async def test_no_secret_or_text_in_errors_or_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    p, _ = provider(lambda r: httpx.Response(500, text=f"{TEXT} {ACCOUNT} {TOKEN}"))
    with pytest.raises(EmbeddingUnavailableError) as info:
        await p.embed_passages([TEXT])
    everything = caplog.text + repr(info.value) + str(info.value)
    for secret in (TEXT, ACCOUNT, TOKEN):
        assert secret not in everything


async def test_neurons_header_is_logged_and_summed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="app.services.embeddings_cloudflare")
    p, _ = provider(lambda r: ok(r, "2.5"))
    await p.embed_passages([TEXT, "b"])
    await p.embed_query("q")
    assert cf.neurons_total == 5.0
    assert "texts=2 neurons=2.5" in caplog.text
    assert TEXT not in caplog.text


async def test_missing_neurons_header_is_tolerated(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="app.services.embeddings_cloudflare")
    p, _ = provider(lambda r: ok(r, None))
    await p.embed_query("q")
    assert cf.neurons_total == 0.0
    assert "neurons=-" in caplog.text


def test_cloudflare_provider_requires_credentials() -> None:
    from app.core.config import Settings

    with pytest.raises(ValueError, match="CLOUDFLARE_ACCOUNT_ID"):
        Settings(
            _env_file=None,
            database_url="postgresql+asyncpg://x/x",
            jwt_secret="x" * 40,
            embedding_provider="cloudflare",
            cloudflare_account_id="",
            cloudflare_api_token="",
        )
