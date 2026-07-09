"""
Code indexer: turns source files into searchable symbol chunks.

Symbols are DERIVED from the code on disk, so they are stored only in the
index.db (never in memory.jsonl). Rebuilding is deterministic: replay the
JSONL, then re-scan the code.
"""

import os
import re

from . import store

CODE_EXT = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs",
    ".java", ".rb", ".c", ".cpp", ".h", ".hpp", ".cs", ".php",
}

SKIP_DIRS = {
    ".git", ".ctxmem", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".mypy_cache", ".pytest_cache", "site-packages",
    ".egg-info",
}

DEF_RE = re.compile(
    r"^\s*(?:export\s+)?(?:public\s+|private\s+|protected\s+)?"
    r"(?:async\s+)?(?:def|function|class|func|fn|type|interface|struct)\s+"
    r"([A-Za-z_][A-Za-z0-9_]*)"
)


def extract_symbols(path, text):
    lines = text.splitlines()
    matches = []
    for i, line in enumerate(lines):
        m = DEF_RE.match(line)
        if m:
            matches.append((i, m.group(1)))

    chunks = []
    for idx, (ln, name) in enumerate(matches):
        end = matches[idx + 1][0] if idx + 1 < len(matches) else len(lines)
        body = "\n".join(lines[ln:end])[:2000]
        chunks.append((name, ln + 1, body))

    if not matches:
        # No recognizable symbols: index the head of the file as a fallback.
        chunks.append((os.path.basename(path), 1, "\n".join(lines[:60])[:2000]))
    return chunks


def index_code(conn, root, branch, commit):
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d not in SKIP_DIRS and not d.endswith(".egg-info")
        ]
        for fn in filenames:
            if os.path.splitext(fn)[1] not in CODE_EXT:
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root)
            try:
                with open(full, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
            except OSError:
                continue
            for name, line, body in extract_symbols(full, text):
                store.insert_row(conn, {
                    "id": store.new_id(),
                    "type": "symbol",
                    "branch": branch,
                    "commit": commit,
                    "path": "{}:{}".format(rel, line),
                    "title": name,
                    "content": body,
                    "tags": [],
                    "source": "code",
                    "ts": "",
                })
                count += 1
    conn.commit()
    return count
