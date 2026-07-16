#!/usr/bin/env bash
#
# record-demo.sh — render assets/demo.svg from scripts/demo.sh using termtosvg.
#
# Requirements: pip install termtosvg  (already available in the project venv).
#
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

TERMTOSVG="$REPO_ROOT/.venv/bin/termtosvg"
command -v "$TERMTOSVG" >/dev/null 2>&1 || TERMTOSVG="termtosvg"

"$TERMTOSVG" assets/demo.svg \
  -c "bash $REPO_ROOT/scripts/demo.sh" \
  -g 92x22 \
  -M 1600 \
  -t window_frame

echo "Wrote assets/demo.svg"
