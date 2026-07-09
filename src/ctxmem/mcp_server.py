"""
MCP server exposing ctxmem to AI agents (e.g. GitHub Copilot).

Tools:
  recall(query, limit, type, mode)            -> search project memory + code
  remember(content, type, title, tags)        -> store a decision/note/session
  memory_status()                             -> mode, branch/commit, index counts

Run:  ctxmem-mcp        (set CTXMEM_ROOT to point at the repo; defaults to cwd)

Requires the optional dependency:  pip install "ctxmem[mcp]"
"""

import os
from typing import Optional

from . import gitinfo, retrieval, store

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover
    raise SystemExit(
        "The MCP extra is not installed. Run: pip install \"ctxmem[mcp]\""
    )

ROOT = os.environ.get("CTXMEM_ROOT", ".")
mcp = FastMCP("ctxmem")


@mcp.tool()
def recall(query: str, limit: int = 8, type: Optional[str] = None,
           mode: Optional[str] = None) -> str:
    """Search the project's memory and code for context relevant to a task.

    mode overrides the configured search mode: keyword | semantic | hybrid.
    """
    conn = retrieval.get_conn(ROOT)
    if conn is None:
        return "No memory initialized. Run 'ctxmem init' in the repo first."
    rows, used = retrieval.search(
        conn, query, ROOT, limit=limit, type_filter=type, mode_override=mode)
    if not rows:
        return "No matches for: {}".format(query)
    out = ["(mode: {})".format(used)]
    for row in rows:
        head = "[{}] {}".format(row.get("type"), row.get("title") or row.get("path"))
        body = " ".join((row.get("content") or "").split())[:300]
        loc = " (@ {})".format(row.get("path")) if row.get("path") and row.get("title") else ""
        out.append("{}{}\n{}".format(head, loc, body))
    return "\n\n".join(out)


@mcp.tool()
def remember(content: str, type: str = "note", title: str = "", tags: str = "") -> str:
    """Store a decision/note/session into the shared, git-committed memory."""
    root = ROOT
    base, jsonl_path, db_path = store.memory_paths(root)
    if not os.path.isdir(base):
        return "No memory initialized. Run 'ctxmem init' in the repo first."
    rec = {
        "id": store.new_id(),
        "ts": store.now_iso(),
        "type": type,
        "branch": gitinfo.branch(root),
        "commit": gitinfo.commit(root),
        "path": "",
        "title": title,
        "content": content,
        "tags": [t for t in tags.split(",") if t],
    }
    store.append_jsonl(jsonl_path, rec)
    conn = retrieval.get_conn(root)
    rec["source"] = "memory"
    store.insert_row(conn, rec)
    conn.commit()
    return "Remembered [{}] {} on branch {}.".format(
        type, title or content[:40], rec["branch"])


@mcp.tool()
def memory_status() -> str:
    """Report search mode, current branch/commit and how many items are indexed."""
    conn = retrieval.get_conn(ROOT)
    if conn is None:
        return "No memory initialized. Run 'ctxmem init' in the repo first."
    cfg = store.load_config(ROOT)
    lines = [
        "mode: {}".format(cfg["mode"]),
        "branch: {}".format(gitinfo.branch(ROOT)),
        "commit: {}".format(gitinfo.commit(ROOT)),
    ]
    for row in store.counts(conn):
        lines.append("{}: {}".format(row["type"], row["n"]))
    return "\n".join(lines)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
