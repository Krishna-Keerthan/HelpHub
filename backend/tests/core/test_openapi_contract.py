"""docs/api/openapi.json is the frontend contract: it must match the app."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "export_openapi.py"


def _load():
    spec = importlib.util.spec_from_file_location("export_openapi", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_openapi_matches_the_app() -> None:
    module = _load()
    assert module.OPENAPI_PATH.is_file(), "run scripts/export_openapi.py"
    assert module.OPENAPI_PATH.read_text() == module.render(), (
        "docs/api/openapi.json is stale; run: uv run python scripts/export_openapi.py"
    )


def test_stream_route_is_in_the_contract() -> None:
    schema = _load().app.openapi()
    assert "/chat/stream" in schema["paths"]
