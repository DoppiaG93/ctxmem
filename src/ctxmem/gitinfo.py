"""Read the current git branch and commit so every memory is context-aware."""

import subprocess


def _run(args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=5)
        return result.stdout.strip()
    except Exception:
        return ""


def branch(root="."):
    return _run(["git", "-C", root, "rev-parse", "--abbrev-ref", "HEAD"]) or "no-git"


def commit(root="."):
    return _run(["git", "-C", root, "rev-parse", "--short", "HEAD"]) or "none"
