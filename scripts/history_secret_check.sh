#!/usr/bin/env bash
# HUMAN-RUN ONLY. Never run through an AI tool: it reads .env locally.
# Checks that no secret value from .env appears anywhere in git history.
# Prints variable NAMES only, never values.
set -u
cd "$(git rev-parse --show-toplevel)" || exit 2
[ -f .env ] || { echo "no .env found"; exit 2; }
rc=0
revs=$(git rev-list --all)
while IFS='=' read -r name value; do
  case "$name" in ''|\#*) continue ;; esac
  value="${value%$'\r'}"; value="${value%\"}"; value="${value#\"}"
  case "$name" in
    *DSN*|DATABASE_URL|MIGRATION_DATABASE_URL)       # check only the password inside the URL
      value=$(printf '%s' "$value" | sed -n 's#^[^:]*://[^:]*:\([^@]*\)@.*#\1#p') ;;
    *KEY*|*SECRET*|*PASSWORD*|*TOKEN*) ;;
    *) continue ;;
  esac
  [ "${#value}" -lt 8 ] && continue
  # shellcheck disable=SC2086
  if git grep -q -I -F -e "$value" $revs 2>/dev/null; then
    echo "FOUND in history: $name"; rc=1
  else
    echo "clean: $name"
  fi
done < .env
exit "$rc"
