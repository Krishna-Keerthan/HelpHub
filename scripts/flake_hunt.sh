# ---- hunt ------------------------------------------------------------------
for i in $(seq 1 "$RUNS"); do
  log="$OUT/run_$i.log"
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
