"""scripts/smoke_live.py against a fake API: success path, a failing step, no secrets printed."""

import importlib.util
import json
from pathlib import Path

import httpx
import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "smoke_live.py"
# gate-allow: secret fake values used only by this test
PASSWORD = "FAKE-PASSWORD-VALUE-123"
ACCESS = "FAKE-ACCESS-TOKEN-VALUE"
REFRESH = "FAKE-REFRESH-TOKEN-VALUE"


def load():
    spec = importlib.util.spec_from_file_location("smoke_live", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_api(*, search_hits: bool = True, final_event: str = "done"):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/auth/login":
            return httpx.Response(
                200, json={"access_token": ACCESS, "refresh_token": REFRESH}
            )
        if path == "/documents" and request.method == "POST":
            return httpx.Response(201, json={"id": "doc-1", "status": "READY"})
        if path == "/documents/doc-1" and request.method == "GET":
            return httpx.Response(200, json={"id": "doc-1", "status": "READY"})
        if path == "/search":
            hits = [{"document_id": "doc-1"}] if search_hits else []
            return httpx.Response(200, json=hits)
        if path == "/chat/stream":
            body = (
                'event: sources\ndata: {"sources": []}\n\n'
                'event: token\ndata: {"text": "SECRET-ANSWER-TEXT"}\n\n'
                f"event: {final_event}\ndata: {json.dumps({'status': 'complete'})}\n\n"
            )
            return httpx.Response(
                200, headers={"content-type": "text/event-stream"}, text=body
            )
        if path == "/documents/doc-1" and request.method == "DELETE":
            return httpx.Response(204)
        if path == "/auth/logout":
            return httpx.Response(204)
        return httpx.Response(404)

    return handler


def run(monkeypatch: pytest.MonkeyPatch, handler) -> int:
    module = load()
    real_client = httpx.Client
    monkeypatch.setattr(
        module.httpx,
        "Client",
        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
    )
    return module.run("http://api.test", "acme", "a@b.test", PASSWORD)


def test_all_steps_pass_and_nothing_secret_is_printed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(monkeypatch, fake_api()) == 0
    out = capsys.readouterr().out
    for step in (
        "login",
        "upload",
        "wait_ready",
        "search",
        "chat_stream",
        "delete",
        "logout",
    ):
        assert step in out
    assert "SMOKE OK" in out
    for secret in (PASSWORD, ACCESS, REFRESH, "SECRET-ANSWER-TEXT"):
        assert secret not in out


def test_a_missing_search_hit_fails_with_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(monkeypatch, fake_api(search_hits=False)) == 1
    out = capsys.readouterr().out
    assert "SMOKE FAILED" in out
    assert "chat_stream" not in out  # stops at the first failure


def test_a_stream_that_ends_in_error_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(monkeypatch, fake_api(final_event="error")) == 1
    assert "stream did not end with done" in capsys.readouterr().out


def test_missing_environment_variable_exits_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BASE_URL", raising=False)
    with pytest.raises(SystemExit) as info:
        load().main()
    assert info.value.code == 2
