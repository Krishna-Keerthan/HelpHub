#!/usr/bin/env bash
# Deterministic review gate. Fail-fast; one summary line per step on the terminal,
# details in /tmp/gate-report.txt. Usage: scripts/gate.sh [--full]
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT=${GATE_REPORT:-/tmp/gate-report.txt}
FULL=0
[[ "${1:-}" == "--full" ]] && FULL=1
cd "$ROOT/backend" || exit 2
# Never touch a non-local database (ruff, alembic and pytest all may). No connection is made.
if ! uv run python -m tests.helpers.db_guard; then
  echo "FAIL  local-database guard (nothing was run)"
  exit 2
fi
# First line of the report: which commit (and whether dirty) this run covered.
python3 "$ROOT/scripts/gate_checks.py" stamp "$REPORT"

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

# hits <rule-id> <pattern> <path...>: "file:line:text" for each match of the ERE
# in .py files, except lines marked "# gate-allow: <rule-id> <reason>" (reason of
# 10+ characters) on the same or the previous line.
hits() {
  local rule=$1 pattern=$2
  shift 2
  find "$@" -name '*.py' -print0 | sort -z | RULE="$rule" PAT="$pattern" xargs -0 awk '
    function valid(line,   marker, rest) {
      marker = "gate-allow: " ENVIRON["RULE"] " "
      if (!index(line, marker)) return 0
      rest = substr(line, index(line, marker) + length(marker))
      return length(rest) >= 10
    }
    FNR == 1 { allow = 0 }
    /gate-allow/ { allow = valid($0) ? FNR : 0 }
    $0 ~ ENVIRON["PAT"] && allow != FNR && allow != FNR - 1 { print FILENAME ":" FNR ":" $0 }
  '
}

# scan <name> <rule-id> <pattern> <path...>: any hit fails the gate.
scan() {
  local name=$1 rule=$2 pattern=$3 out
  shift 3
  out=$(mktemp)
  hits "$rule" "$pattern" "$@" > "$out"
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

step "untracked files" python3 "$ROOT/scripts/gate_checks.py" untracked
step "ruff check" uv run ruff check .
step "ruff format (changed files)" format_check
step "import-linter" uv run lint-imports
step "alembic check" uv run alembic check

scan "skip/xfail scan" skip-xfail 'pytest\.mark\.skip|skipif|xfail|pytest\.skip\(|importorskip' tests
scan "planner flags in app/" planner-flag 'enable_(seqscan|indexscan|indexonlyscan|bitmapscan|nestloop|hashjoin|mergejoin|sort|hashagg|material)' app
scan "str(exc)/logger.exception in app/" str-exc 'str\((exc|e|err|error|ex)\)|logger\.exception' app
scan "print( in app/" print '(^|[^_a-zA-Z.])print\(' app

step "gate-allow format" python3 "$ROOT/scripts/gate_checks.py" allows
grep '^allow ' "$REPORT" | sed 's/^/      /'
step "secret scan" python3 "$ROOT/scripts/gate_checks.py" secrets
step "AR register" python3 "$ROOT/scripts/gate_checks.py" ar-register

# get_session is allowed in its definition, and the
# two tenants-table users.
out=$(mktemp)
hits get-session 'get_session([^_a-zA-Z]|$)' app |
  grep -vE '^app/(db/repositories/tenants|services/auth|db/session)\.py' > "$out"
{ echo "=== get_session scan ==="; cat "$out"; } >> "$REPORT"
[[ -s "$out" ]] && fail "get_session outside allowed files" "$out"
echo "ok    get_session scan"
rm -f "$out"

step "security tests" uv run pytest -q tests/security

# Production dependencies: blocking, same script as CI. Fails closed, so it also
# fails when the advisory database cannot be reached (no network).
step "pip-audit (production, blocking)" timeout 120 "$ROOT/scripts/audit_deps.sh" prod

# Full environment including dev: warnings only, never fails the gate.
echo "=== pip-audit (full, warn-only) ===" >> "$REPORT"
timeout 120 "$ROOT/scripts/audit_deps.sh" full > /tmp/gate-audit.txt 2>&1
cat /tmp/gate-audit.txt >> "$REPORT"
if grep -q "^WARNING" /tmp/gate-audit.txt; then
  echo "warn  pip-audit (full environment, non-blocking; see report)"
else
  echo "ok    pip-audit (full environment)"
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
