"""With EMBEDDING_PROVIDER=cloudflare the local model stack is never imported."""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]

SCRIPT = textwrap.dedent(
    """
    import sys
    from app.main import app
    from app.services.embeddings import default_provider, warm_up_default_provider
    import asyncio
    from app.core.config import settings
    assert settings.embedding_provider == "cloudflare"
    provider = default_provider()
    assert type(provider).__name__ == "CloudflareEmbeddingProvider"
    leaked = sorted(m for m in ("fastembed", "onnxruntime") if m in sys.modules)
    print("LEAKED", leaked)
    """
)


def test_cloudflare_provider_never_imports_fastembed_or_onnxruntime() -> None:
    env = {
        **os.environ,
        "EMBEDDING_PROVIDER": "cloudflare",
        # gate-allow: secret fake values used only by this test
        "CLOUDFLARE_ACCOUNT_ID": "x",
        "CLOUDFLARE_API_TOKEN": "x",
    }
    result = subprocess.run(  # noqa: S603 (fixed argv, no shell)
        [sys.executable, "-I", "-c", SCRIPT],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-500:]
    assert "LEAKED []" in result.stdout
