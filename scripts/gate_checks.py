#!/usr/bin/env python3
"""Deterministic repo checks used by scripts/gate.sh (stdlib only).

Usage: gate_checks.py [--root DIR] {allows|secrets|ar-register|stamp REPORT}
Findings print as ``path:line: rule`` and never echo a matched secret value.
Exit code: 0 clean, 1 findings.
"""

import argparse
import datetime
import re
import subprocess
import sys
from pathlib import Path

ALLOW_MARKER = re.compile(r"#\s*gate-allow\b")
ALLOW_VALID = re.compile(
    r"#\s*gate-allow:\s+(?P<rule>[a-z0-9-]+)\s+(?P<reason>.{10,})$"
)
PLACEHOLDERS = {"change-me-generate-with-openssl-rand-hex-32"}  # documented, public

_NAME = r"[\w.-]*(?:key|secret|token|password|passwd|dsn)[\w.-]*"
QUOTED_ASSIGN = re.compile(
    rf"""\b{_NAME}["']?\s*[:=]\s*[bf]?["'](?P<val>[^"'\n]{{20,}})["']""", re.IGNORECASE
)
# Unquoted KEY=value: env-style files only (in code it is an expression).
BARE_ASSIGN = re.compile(
    rf"^\s*(?:export\s+)?{_NAME}\s*[=:]\s*(?P<val>[^\s'\"#$(){{}}]{{20,}})\s*$",
    re.IGNORECASE,
)
BARE_SUFFIXES = {".example", ".yaml", ".yml", ".sh", ".env"}
TOKEN_PATTERNS = {
    "gsk_": re.compile(r"\bgsk_[A-Za-z0-9]{10,}"),
    "sk-": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    "AKIA": re.compile(r"\bAKIA[0-9A-Z]{12,}"),
    "eyJ": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}"),
    # gate-allow: secret pattern definition, no secret
    "BEGIN": re.compile(r"-----BEGIN"),
}
SKIP_SUFFIXES = {".lock", ".png", ".jpg", ".pdf", ".ico", ".gz"}
SKIP_NAMES = {".env", "uv.lock"}  # .env is never read; the lock holds hashes only
AR_ROW = re.compile(r"^\|\s*(AR-\d+)\s*\|")
AR_REF = re.compile(r"\bAR-\d+\b")
REGISTER = "docs/review/accepted-risks.md"


def tracked(root: Path) -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True
    ).stdout
    return [Path(p.decode()) for p in out.split(b"\0") if p]


def _lines(root: Path, rel: Path) -> list[str] | None:
    if rel.name in SKIP_NAMES or rel.suffix in SKIP_SUFFIXES:
        return None
    try:
        return (root / rel).read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, OSError):
        return None


def collect_allows(root: Path) -> tuple[list[str], list[str]]:
    """(one line per valid gate-allow, findings for malformed ones)."""
    listing: list[str] = []
    problems: list[str] = []
    for rel in tracked(root):
        if rel.suffix != ".py" or rel.name == "gate_checks.py":  # defines the marker
            continue
        for n, line in enumerate(_lines(root, rel) or [], 1):
            if not ALLOW_MARKER.search(line):
                continue
            match = ALLOW_VALID.search(line.strip()[line.strip().index("#") :])
            if match:
                listing.append(f"allow {rel}:{n} [{match['rule']}] {match['reason']}")
            else:
                problems.append(
                    f"{rel}:{n}: malformed gate-allow "
                    "(want '# gate-allow: <rule-id> <reason of 10+ chars>')"
                )
    return listing, problems


def allows(root: Path) -> list[str]:
    """Print every gate-allow; return the malformed ones."""
    listing, problems = collect_allows(root)
    print("\n".join(listing))
    return problems


def _allowed(lines: list[str], index: int, rule: str) -> bool:
    for j in (index, index - 1):
        if j < 0:
            continue
        match = ALLOW_VALID.search(
            lines[j].strip()[max(lines[j].strip().find("#"), 0) :]
        )
        if match and match["rule"] == rule:
            return True
    return False


def secrets(root: Path) -> list[str]:
    found: list[str] = []
    for rel in tracked(root):
        lines = _lines(root, rel)
        if lines is None:
            continue
        for i, line in enumerate(lines):
            hit = None
            regexes = [QUOTED_ASSIGN]
            if rel.suffix in BARE_SUFFIXES:
                regexes.append(BARE_ASSIGN)
            for regex in regexes:
                match = regex.search(line)
                if match and match["val"] not in PLACEHOLDERS:
                    hit = "secret-assignment"
            for name, regex in TOKEN_PATTERNS.items():
                if regex.search(line):
                    hit = f"token-pattern {name}"
            if hit and not _allowed(lines, i, "secret"):
                found.append(f"{rel}:{i + 1}: {hit}")
    return found


def ar_register(root: Path) -> list[str]:
    problems: list[str] = []
    register = root / REGISTER
    ids = [
        m[1] for line in register.read_text().splitlines() if (m := AR_ROW.match(line))
    ]
    if not ids:
        return [f"{REGISTER}: no AR rows found"]
    for pos, ar in enumerate(ids):
        if ids.count(ar) > 1 and ids.index(ar) == pos:
            problems.append(f"{REGISTER}: duplicate {ar}")
    numbers = sorted({int(a[3:]) for a in ids})
    # Sequential: 1..max, except ids deleted as resolved are tolerated only at the
    # low end (never reused), so the sequence must be gap-free from its minimum.
    expected = list(range(numbers[0], numbers[-1] + 1))
    if numbers != expected:
        missing = sorted(set(expected) - set(numbers))
        problems.append(f"{REGISTER}: gap in sequence, missing {missing}")
    if [int(a[3:]) for a in ids] != sorted(int(a[3:]) for a in ids):
        problems.append(f"{REGISTER}: ids are not in ascending order")
    known = set(ids)
    for rel in tracked(root):
        if str(rel) == REGISTER:
            continue
        for n, line in enumerate(_lines(root, rel) or [], 1):
            for ref in AR_REF.findall(line):
                if ref not in known:
                    problems.append(f"{rel}:{n}: reference to unknown {ref}")
    return problems


def stamp(root: Path, report: Path) -> None:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True
    ).stdout.strip()
    now = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    report.write_text(
        f"gate-report commit={head or 'none'} time={now} dirty={'yes' if dirty else 'no'}\n"
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("check", choices=["allows", "secrets", "ar-register", "stamp"])
    parser.add_argument("report", nargs="?", type=Path)
    args = parser.parse_args(argv)
    if args.check == "stamp":
        stamp(args.root, args.report)
        return 0
    if args.check == "allows":  # problems first: the gate shows only the head
        listing, problems = collect_allows(args.root)
        print("\n".join([*problems, *listing]))
        return 1 if problems else 0
    problems = {"secrets": secrets, "ar-register": ar_register}[args.check](args.root)
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
