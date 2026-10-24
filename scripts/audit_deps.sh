#!/usr/bin/env bash
# Dependency audit, shared by CI and scripts/gate.sh. Run from backend/.
#   scripts/audit_deps.sh prod   BLOCKING: only what ships (--no-dev, frozen lock).
#                                Exits non-zero on any finding, and also when the
#                                advisory database cannot be reached (fails closed).
#   scripts/audit_deps.sh full   NON-blocking: the whole environment including dev.
#                                Prints findings as warnings and always exits 0.
set -u
mode=${1:-}
case "$mode" in
  prod)
    req=$(mktemp)
    trap 'rm -f "$req"' EXIT
    uv export --frozen --no-dev --no-emit-project -o "$req" > /dev/null || exit 2
    # Hashed, fully pinned requirements: pip-audit needs no resolver (--disable-pip).
    uv run pip-audit -r "$req" --disable-pip
    ;;
  full)
    if uv run pip-audit; then
      echo "full-environment audit: no findings"
    else
      echo "WARNING: full-environment audit reported findings or could not run (non-blocking; dev-only packages included)"
    fi
    exit 0
    ;;
  *)
    echo "usage: scripts/audit_deps.sh prod|full" >&2
    exit 2
    ;;
esac
