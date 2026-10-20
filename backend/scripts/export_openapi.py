"""Write docs/api/openapi.json from the app's own schema (no server started).

    uv run python scripts/export_openapi.py          # rewrite the file
    uv run python scripts/export_openapi.py --check  # exit 1 if it differs

tests/core/test_openapi_contract.py runs the same comparison.
"""

import json
import sys
from pathlib import Path

from app.main import app

OPENAPI_PATH = Path(__file__).resolve().parents[2] / "docs" / "api" / "openapi.json"


def render() -> str:
    return (
        json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )


def main(argv: list[str]) -> int:
    text = render()
    if "--check" in argv:
        if not OPENAPI_PATH.is_file() or OPENAPI_PATH.read_text() != text:
            print(f"{OPENAPI_PATH} is out of date; run scripts/export_openapi.py")
            return 1
        return 0
    OPENAPI_PATH.parent.mkdir(parents=True, exist_ok=True)
    OPENAPI_PATH.write_text(text)
    print(f"wrote {OPENAPI_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
