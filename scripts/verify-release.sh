#!/usr/bin/env bash
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

FAIL=0
run() { echo "==> $*"; if ! "$@"; then FAIL=1; fi; }

run python3 -m ruff check src tests || true
run python3 -m mypy src --ignore-missing-imports || true
run python3 -m pytest tests/unit tests/security -q
run python3 -m pytest tests/integration -q

# packaging metadata check
if [ -f packaging/rpm/amazon-music-desktop.spec ]; then
  echo "spec present"
else
  echo "missing spec"; FAIL=1
fi

if [ "$FAIL" -ne 0 ]; then
  echo "VERIFICATION FAILED"
  exit 1
fi
echo "VERIFICATION PASSED"
exit 0
