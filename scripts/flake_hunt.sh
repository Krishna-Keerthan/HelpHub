#!/usr/bin/env bash
# Repeat a pytest command N times and report pass/fail counts.
# Usage: scripts/flake_hunt.sh [-n N] [--keep-going] [--between-isolation] -- <pytest args>
#   -n N                 number of runs (default 20)
#   --keep-going         do not stop at the first failure
#   --between-isolation  run `pytest -q tests/isolation` before every iteration
# Holds the pytest session lock (flock) for the whole hunt, so no other session
# can slip in between iterations; children skip the lock via
# HELPHUB_PYTEST_LOCK_HOLDER (see backend/tests/conftest.py).
set -uo pipefail

RUNS=20; KEEP=0; BETWEEN=0
while [ $# -gt 0 ]; do
  case "$1" in
    -n) RUNS="$2"; shift 2 ;;
    --keep-going) KEEP=1; shift ;;
    --between-isolation) BETWEEN=1; shift ;;
    --) shift; break ;;
    *) echo "unknown option: $1" >&2; exit 64 ;;
  esac
done
[ $# -gt 0 ] || { echo "usage: $0 [-n N] [--keep-going] [--between-isolation] -- <pytest args>" >&2; exit 64; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"
CMD=(uv run pytest -q "$@")
OUT="$(mktemp -d "${TMPDIR:-/tmp}/flake_hunt.XXXXXX")"
PASS=0; FAIL=0; FAILED_RUNS=()

exec 9>"${HELPHUB_PYTEST_LOCK_FILE:-/tmp/helphub-pytest.lock}"
flock -n 9 || { echo "another pytest session is running (shared database)" >&2; exit 2; }
export HELPHUB_PYTEST_LOCK_HOLDER=$$

uptime_s() { cut -d. -f1 /proc/uptime; }
summary() {
  echo "hunt: runs=$((PASS + FAIL)) pass=$PASS fail=$FAIL logs=$OUT"
  [ "$FAIL" -eq 0 ] || echo "failed runs: ${FAILED_RUNS[*]}"
}

# ---- hunt ------------------------------------------------------------------
for i in $(seq 1 "$RUNS"); do
  log="$OUT/run_$i.log"
  if [ "$BETWEEN" -eq 1 ]; then
    uv run pytest -q tests/isolation > "$OUT/between_$i.log" 2>&1
    echo "run $i: isolation rc=$?" >> "$OUT/between.log"
  fi
  w0=$(date +%s); u0=$(uptime_s)
  
  # Run pytest. We temporarily disable pipefail/errexit behavior for the test command evaluation
  "${CMD[@]}" > "$log" 2>&1; rc=$?
  
  w1=$(date +%s); u1=$(uptime_s)
  dur=$((w1 - w0)); drift=$(( (w1 - w0) - (u1 - u0) ))
  echo "run=$i start=$(date -Is -d "@$w0") rc=$rc wall_s=$dur uptime_s=$((u1 - u0)) drift_s=$drift" >> "$OUT/clock.log"

  if [ "$rc" -eq 0 ]; then
    PASS=$((PASS + 1)); echo "run $i: ok (${dur}s) $(tail -n 1 "$log")"
  else
    FAIL=$((FAIL + 1)); FAILED_RUNS+=("$i")
    echo "run $i: FAILED rc=$rc (${dur}s) -> $log"
    if [ "${drift#-}" -gt 2 ]; then
      echo "  !! wall clock and VM uptime disagree by ${drift}s: the clock jumped during this run"
    fi
    # Added || true to prevent grep failures from poisoning pipefail
    echo "  -- failing tests:";        grep -E '^(FAILED|ERROR) ' "$log" | head -20 || true
    echo "  -- auth rejections:";      grep -n 'auth_rejected' "$log" | head -20 || true
    echo "  -- status hints:";         grep -nE ' (401|403|409|413|422|429|500|503)\b|Not authenticated' "$log" | head -20 || true
    echo "  -- captured log excerpt:"; grep -n -A8 'Captured log' "$log" | head -60 || true
    [ "$KEEP" -eq 0 ] && break
  fi
done

summary
[ "$FAIL" -eq 0 ]
