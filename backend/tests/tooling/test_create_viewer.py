"""scripts/create_viewer.py against a fake API: creates once, idempotent, counts only."""

import importlib.util
import json
from pathlib import Path

import httpx
import pytest

REAL_CLIENT = httpx.Client  # before any test patches it
SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
VIEWER_PASSWORD = "FAKE-viewer-password-1"  # gate-allow: secret fake test value


def load(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "create_viewer", SCRIPTS / "create_viewer.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(
    monkeypatch: pytest.MonkeyPatch,
    users: list[dict],
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str, list[dict]]:
    mod = load(monkeypatch)
    monkeypatch.setattr(
        mod,
        "read_settings",
        lambda: {
            "BASE_URL": "http://fake",
            "TENANT_SLUG": "t",
            "EMAIL": "admin@x.test",
            "PASSWORD": "p",
        },
    )
    monkeypatch.setenv("VIEWER_EMAIL", "Viewer@X.test")
    monkeypatch.setenv("VIEWER_PASSWORD", VIEWER_PASSWORD)
    posted: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/login":
            return httpx.Response(200, json={"access_token": "t"})
        if request.method == "GET":
            return httpx.Response(200, json=users)
        body = json.loads(request.content)
        posted.append(body)
        users.append({"email": body["email"], "role": body["role"]})
        return httpx.Response(201, json={})

    monkeypatch.setattr(
        mod.httpx,
        "Client",
        lambda **kw: REAL_CLIENT(transport=httpx.MockTransport(handler), **kw),
    )
    code = mod.main()
    return code, capsys.readouterr().out, posted


def test_creates_a_viewer_once(monkeypatch, capsys) -> None:
    users: list[dict] = []
    code, out, posted = run(monkeypatch, users, capsys)
    assert code == 0 and "created=1 existing=0 conflicts=0" in out
    assert posted == [
        {"email": "viewer@x.test", "password": VIEWER_PASSWORD, "role": "viewer"}
    ]
    code, out, posted = run(monkeypatch, users, capsys)
    assert code == 0 and "created=0 existing=1 conflicts=0" in out
    assert posted == []


def test_output_never_contains_secrets(monkeypatch, capsys) -> None:
    _, out, _ = run(monkeypatch, [], capsys)
    for secret in (VIEWER_PASSWORD, "viewer@x.test", "http://"):
        assert secret not in out


def test_existing_non_viewer_is_a_conflict(monkeypatch, capsys) -> None:
    code, out, posted = run(
        monkeypatch, [{"email": "viewer@x.test", "role": "admin"}], capsys
    )
    assert code == 1 and "conflicts=1" in out and posted == []
