#!/usr/bin/env bash
#
# demo.sh — scripted ctxmem walkthrough used to render the README animation.
#
# It runs in a throwaway temp directory so it never touches this repo's own
# memory. Regenerate the animation with:
#
#     scripts/record-demo.sh
#
set -e

# Make the local ctxmem (installed in the venv) available on PATH.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -x "$REPO_ROOT/.venv/bin/ctxmem" ]; then
  export PATH="$REPO_ROOT/.venv/bin:$PATH"
fi

# Isolated sandbox so the demo doesn't write into the real project.
DEMO_DIR="$(mktemp -d)"
cd "$DEMO_DIR"
git init -q
git commit -q --allow-empty -m "init" >/dev/null 2>&1 || true

# Print a green prompt and "type" a command character by character.
prompt() {
  printf '\033[1;32m$\033[0m '
  local s="$1" i
  for ((i = 0; i < ${#s}; i++)); do
    printf '%s' "${s:i:1}"
    sleep 0.035
  done
  printf '\n'
  sleep 0.35
}

sleep 0.6

prompt 'ctxmem init'
ctxmem init
echo
sleep 0.7

prompt 'ctxmem remember --type decision --title "Authentication" "We use stateless JWT for authentication, not server sessions."'
ctxmem remember --type decision --title "Authentication" "We use stateless JWT for authentication, not server sessions."
echo
sleep 0.7

prompt 'ctxmem sync'
ctxmem sync
echo
sleep 0.7

prompt 'ctxmem recall "how do we handle authentication"'
ctxmem recall "how do we handle authentication"
echo
sleep 2.0

# Clean up the sandbox.
cd /
rm -rf "$DEMO_DIR"
