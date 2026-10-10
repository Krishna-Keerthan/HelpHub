"""PostToolUse hook: ruff-format Python files Claude edits under backend/.

Format only, no `ruff check --fix`: autofix would delete an import Claude has
just added in one edit and only uses in the next. Linting stays an explicit
step (`uv run ruff check .`).

Exit codes: 0 = done or nothing to do; 2 = ruff could not format the file
(usually a syntax error), reported back to Claude via stderr.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(f"format hook: unreadable hook input: {exc}", file=sys.stderr)
        return 1  # non-blocking: shown to the user, not fed to Claude

    path = data.get("tool_input", {}).get("file_path", "")
    if not path.endswith(".py"):
        return 0

    project = Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")).resolve()
    backend = project / "backend"
    target = Path(path).resolve()
    # Only repo code: never touch scratch files or other projects' files.
    if not target.is_relative_to(backend) or not target.is_file():
        return 0

    # The venv's ruff directly; fall back to uv on a fresh clone without one.
    ruff = backend / ".venv" / "bin" / "ruff"
    if ruff.exists():
        cmd = [str(ruff), "format", str(target)]
    elif shutil.which("uv"):
        cmd = ["uv", "run", "--project", str(backend), "ruff", "format", str(target)]
    else:
        print("format hook: neither backend/.venv nor uv found", file=sys.stderr)
        return 1

    # cwd=backend so ruff picks up backend/pyproject.toml.
    result = subprocess.run(cmd, cwd=backend, capture_output=True, text=True)
    if result.returncode != 0:
        print(
            f"ruff format failed for {target}:\n{result.stderr or result.stdout}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
