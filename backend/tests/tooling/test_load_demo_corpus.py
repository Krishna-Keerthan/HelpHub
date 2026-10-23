"""scripts/load_demo_corpus.py against a fake API: skips INDEX.md, idempotent by title, counts only."""

import importlib.util
from pathlib import Path

import httpx
import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "load_demo_corpus.py"


def load():
    spec = importlib.util.spec_from_file_location("load_demo_corpus", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = load()


def test_corpus_files_exclude_index(tmp_path: Path) -> None:
    (tmp_path / "INDEX.md").write_text("# index")
    (tmp_path / "b.md").write_text("# b")
    (tmp_path / "a.md").write_text("# a")
    (tmp_path / "notes.txt").write_text("x")
    assert [p.name for p in mod.corpus_files(tmp_path)] == ["a.md", "b.md"]


def test_environment_overrides_creds_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    creds = tmp_path / "creds"
    creds.write_text(
        "BASE_URL=http://file\nTENANT_SLUG=t\nEMAIL=e@x.test\nPASSWORD='p'\n"
    )
    for key in mod.KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("BASE_URL", "http://env")
    values = mod.read_settings(creds)
    assert values["BASE_URL"] == "http://env"
    assert values["PASSWORD"] == "p"


def test_missing_settings_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for key in mod.KEYS:
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(SystemExit):
        mod.read_settings(tmp_path / "absent")


def test_second_run_uploads_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    for name in ("a", "b"):
        (corpus / f"{name}.md").write_text(f"# {name}\nbody")
    monkeypatch.setattr(mod, "CORPUS", corpus)
    monkeypatch.setattr(
        mod,
        "read_settings",
        lambda: {
            "BASE_URL": "http://fake",
            "TENANT_SLUG": "t",
            "EMAIL": "e@x.test",
            "PASSWORD": "p",
        },
    )
    docs: dict[str, str] = {}
    uploads: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/auth/login":
            return httpx.Response(200, json={"access_token": "t", "refresh_token": "r"})
        if path == "/documents/upload":
            title = "a" if b'name="title"\r\n\r\na' in request.content else "b"
            uploads.append(title)
            docs[title] = f"id-{title}"
            return httpx.Response(201, json={"id": docs[title], "status": "READY"})
        if path == "/documents":
            return httpx.Response(
                200, json=[{"title": t, "id": i} for t, i in docs.items()]
            )
        return httpx.Response(200, json={"status": "READY"})

    real = httpx.Client
    monkeypatch.setattr(
        mod.httpx,
        "Client",
        lambda **kw: real(transport=httpx.MockTransport(handler), **kw),
    )
    assert mod.main() == 0
    assert sorted(uploads) == ["a", "b"]
    assert mod.main() == 0
    assert len(uploads) == 2
    out = capsys.readouterr().out
    assert "uploaded=2 skipped=0" in out
    assert "uploaded=0 skipped=2" in out
    assert "http://" not in out
