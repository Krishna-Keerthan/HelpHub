"""scripts/gate_checks.py: gate-allow format, secret scan, AR register, stamp."""

import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "gate_checks", ROOT / "scripts" / "gate_checks.py"
)
assert _spec is not None and _spec.loader is not None
gc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gc)

# Built piecewise so this file contains no literal marker or token.
ALLOW = "# gate" + "-allow:"
FAKE_TOKENS = {
    "gsk_": "gsk" + "_" + "a1B2c3D4e5F6g7H8i9J0",
    "sk-": "sk" + "-" + "a1B2c3D4e5F6g7H8i9J0k1L2",
    "AKIA": "AK" + "IA" + "ABCDEFGHIJKLMNOP",
    "eyJ": "ey" + "J" + "hbGciOiJIUzI1NiJ9",
    "BEGIN": "-----" + "BEGIN PRIVATE KEY-----",
}
REGISTER = "docs/review/accepted-risks.md"
URL_VALUE = "postgresql://" + "u:pw@host/db-long-enough"
LONG = "abcdefghijklmnopqrstuvwxyz"  # 26 chars: long enough to be flagged


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    return tmp_path


def _register(*ids: int) -> str:
    return "| ID | Risk |\n|---|---|\n" + "".join(f"| AR-{i:02d} | r |\n" for i in ids)


# --- gate-allow format ---------------------------------------------------------


# --- secret scan ---------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        f'API_KEY = "{LONG}"',
        f"client_secret: '{LONG}'",
        f'password = "{LONG}-staple"',
        f'db_dsn = "{URL_VALUE}"',
        f'refresh_token="{LONG[:20]}"',
    ],
)
def test_long_literal_assignments_are_flagged(tmp_path: Path, line: str) -> None:
    root = _repo(tmp_path, {"app.py": line + "\n"})
    findings = gc.secrets(root)
    assert findings == ["app.py:1: secret-assignment"]


@pytest.mark.parametrize(
    "line",
    [
        'api_key = "short"',
        'password = "abcdefghijklmnopq"',  # 17 chars
        "token = create_access_token(claims)",
        'name = "abcdefghijklmnopqrstuvwxyz"',  # not a secret-looking name
        'JWT_SECRET_PLACEHOLDER = "change-me-generate-with-openssl-rand-hex-32"',
    ],
)
def test_short_expression_or_placeholder_is_not_flagged(
    tmp_path: Path, line: str
) -> None:
    assert gc.secrets(_repo(tmp_path, {"app.py": line + "\n"})) == []


@pytest.mark.parametrize("name", FAKE_TOKENS)
def test_token_patterns_are_flagged_without_echoing_the_value(
    tmp_path: Path, name: str
) -> None:
    root = _repo(tmp_path, {"notes.md": f"see {FAKE_TOKENS[name]} here\n"})
    findings = gc.secrets(root)
    assert findings == [f"notes.md:1: token-pattern {name}"]
    assert FAKE_TOKENS[name] not in findings[0]


def test_allow_marker_with_secret_rule_silences_a_hit(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        {
            "a.py": f'{ALLOW} secret fake value for this test\nPASSWORD = "{LONG}"\n',
            "b.py": f'PASSWORD = "{LONG}"  {ALLOW} secret fake value for this test\n',
            "c.py": f'{ALLOW} str-exc wrong rule for a secret\nPASSWORD = "{LONG}"\n',
            "d.py": f'{ALLOW} secret short\nPASSWORD = "{LONG}"\n',
        },
    )
    assert gc.secrets(root) == [
        "c.py:2: secret-assignment",
        "d.py:2: secret-assignment",
    ]


def test_dotenv_and_lockfiles_are_not_scanned(tmp_path: Path) -> None:
    line = f'API_KEY = "{LONG}"\n'
    root = _repo(tmp_path, {".env": line, "uv.lock": line})
    assert gc.secrets(root) == []


# --- accepted-risk register ----------------------------------------------------


def test_clean_register_passes(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        {REGISTER: _register(1, 2, 3), "plan.md": "see AR-02 and AR-03\n"},
    )
    assert gc.ar_register(root) == []


def test_duplicate_gap_and_order_are_flagged(tmp_path: Path) -> None:
    cases = {
        "dup": (_register(1, 2, 2), "duplicate AR-02"),
        "gap": (_register(1, 2, 4), "missing [3]"),
        "order": (_register(1, 3, 2), "not in ascending order"),
    }
    for name, (text, expected) in cases.items():
        directory = tmp_path / name
        directory.mkdir()
        problems = gc.ar_register(_repo(directory, {REGISTER: text}))
        assert any(expected in p for p in problems), (name, problems)


def test_reference_to_a_missing_id_is_flagged(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        {REGISTER: _register(1, 2), "docs/plan.md": "ok AR-01\nbad AR-07 here\n"},
    )
    assert gc.ar_register(root) == ["docs/plan.md:2: reference to unknown AR-07"]


def test_real_repo_register_and_secrets_are_clean() -> None:
    assert gc.ar_register(ROOT) == []
    assert gc.secrets(ROOT) == []
    assert gc.allows(ROOT) == []


# --- report stamp --------------------------------------------------------------


# --- untracked files -----------------------------------------------------------


# --- exec-modes: directly executed scripts must be 100755 in git ------------------------
