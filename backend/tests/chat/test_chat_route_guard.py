"""Slow routes must not hold a DB session: CLAUDE.md forbids TenantSession there."""

import re
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2] / "app"
FORBIDDEN = re.compile(r"\b(TenantSession|CurrentUser|AdminUser|get_tenant_session)\b")


def test_chat_stream_route_uses_no_session_dependency() -> None:
    lines = (APP_DIR / "api" / "chat.py").read_text().splitlines()
    # Comments may name the forbidden dependencies; code may not use them.
    source = "\n".join(line.split("#", 1)[0] for line in lines)
    assert FORBIDDEN.findall(source) == []
    assert "CurrentPrincipal" in source
