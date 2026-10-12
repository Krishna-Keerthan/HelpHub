#!/usr/bin/env bash
# Deterministic review gate. Fail-fast; one summary line per step on the terminal,
# details in /tmp/gate-report.txt. Usage: scripts/gate.sh [--full]
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT=/tmp/gate-report.txt
FULL=0
[[ "${1:-}" == "--full" ]] && FULL=1
cd "$ROOT/backend" || exit 2
: > "$REPORT"

fail() { # name, detail-file
  echo "FAIL  $1  (details: $REPORT)"
  head -n 8 "$2" | cut -c1-160
  exit 1
}

# step <name> <command...>: run, append output to the report, fail-fast.
step() {
  local name=$1 out
  shift
  out=$(mktemp)
  { echo "=== $name ==="; echo "\$ $*"; } >> "$REPORT"
  if "$@" > "$out" 2>&1; then
    cat "$out" >> "$REPORT"
    echo "ok    $name"
    rm -f "$out"
  else
    cat "$out" >> "$REPORT"
    fail "$name" "$out"
  fi
}

# hits <pattern> <path...>: "file:line:text" for each match of the ERE in .py
# files, except lines marked "gate-allow" on the same or the previous line.
hits() {
  local pattern=$1
  shift
  find "$@" -name '*.py' -print0 | sort -z | PAT="$pattern" xargs -0 awk '
    FNR == 1 { allow = 0 }
    /gate-allow/ { allow = FNR }
    $0 ~ ENVIRON["PAT"] && allow != FNR && allow != FNR - 1 { print FILENAME ":" FNR ":" $0 }
  '
}

# scan <name> <pattern> <path...>: any hit fails the gate.
scan() {
  local name=$1 pattern=$2 out
  shift 2
  out=$(mktemp)
  hits "$pattern" "$@" > "$out"
  { echo "=== $name ==="; cat "$out"; } >> "$REPORT"
  if [[ -s "$out" ]]; then
    fail "$name" "$out"
  fi
  echo "ok    $name"
  rm -f "$out"
}

changed_py() {
  { git diff --name-only HEAD -- '*.py'; git ls-files --others --exclude-standard -- '*.py'; } |
    sed -n 's#^backend/##p' | sort -u | while read -r f; do [[ -f "$f" ]] && echo "$f"; done
}

format_check() {
  local files
  files=$(changed_py)
  if [[ -z "$files" ]]; then
    echo "no changed python files"
    return 0
  fi
  # shellcheck disable=SC2086
  uv run ruff format --check $files
}

step "ruff check" uv run ruff check .
step "ruff format (changed files)" format_check
step "import-linter" uv run lint-imports
step "alembic check" uv run alembic check

scan "skip/xfail scan" 'pytest\.mark\.skip|skipif|xfail|pytest\.skip\(|importorskip' tests
scan "planner flags in app/" 'enable_(seqscan|indexscan|indexonlyscan|bitmapscan|nestloop|hashjoin|mergejoin|sort|hashagg|material)' app
scan "str(exc)/logger.exception in app/" 'str\((exc|e|err|error|ex)\)|logger\.exception' app
scan "print( in app/" '(^|[^_a-zA-Z.])print\(' app

# get_session is allowed in its definition, the /health/db route (AR-12) and the
# two tenants-table users.
out=$(mktemp)
hits 'get_session([^_a-zA-Z]|$)' app |
  grep -vE '^app/(db/repositories/tenants|services/auth|db/session|main)\.py' > "$out"
{ echo "=== get_session scan ==="; cat "$out"; } >> "$REPORT"
[[ -s "$out" ]] && fail "get_session outside allowed files" "$out"
echo "ok    get_session scan"
rm -f "$out"

# pip-audit is warn-only and tolerates no network.
echo "=== pip-audit (warn-only) ===" >> "$REPORT"
if timeout 90 uv run pip-audit > /tmp/gate-audit.txt 2>&1; then
  cat /tmp/gate-audit.txt >> "$REPORT"
  echo "ok    pip-audit"
else
  cat /tmp/gate-audit.txt >> "$REPORT"
  echo "warn  pip-audit (findings or no network; see report)"
fi

if [[ $FULL -eq 1 ]]; then
  out=$(mktemp)
  echo "=== full tests ===" >> "$REPORT"
  if uv run pytest -q -m "slow or not slow" -rfsx > "$out" 2>&1; then
    cat "$out" >> "$REPORT"
    echo "ok    full tests: $(tail -n 1 "$out")"
  else
    cat "$out" >> "$REPORT"
    echo "FAIL  full tests  (details: $REPORT)"
    tail -n 12 "$out" | cut -c1-160
    exit 1
  fi
  rm -f "$out"
fi
echo "GATE PASSED"
