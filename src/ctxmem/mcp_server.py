"""
MCP server exposing ctxmem to AI agents (e.g. GitHub Copilot or Codex).

Tools:
  recall(query, limit, type, mode)            -> search project memory + code
  ask(query, limit, type, mode)               -> recall + HIT/WEAK/MISS verdict
  remember(content, type, title, tags, supersedes, path) -> store a decision/note/session
  context(query, budget, limit, type, mode)   -> budgeted context and metadata
  memory_status()                             -> mode, branch/commit, index counts

Run:  ctxmem-mcp        (set CTXMEM_ROOT to point at the repo; defaults to cwd)

Requires the optional dependency:  pip install "ctxmem[mcp]"
"""

import os
from typing import Optional

from . import context as contextmod
from . import gitinfo, retrieval, store

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "The MCP extra is not installed. Run: pip install \"ctxmem[mcp]\""
    ) from exc

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
        out.append(_format_row(row))
    return "\n\n".join(out)


def _format_row(row):
    mem_id = row.get("mem_id") or ""
    marks = []
    if row.get("_superseded"):
        by = row.get("_superseded_by") or {}
        marks.append("\u26a0 SUPERSEDED by {}".format(by.get("title") or by.get("id") or "?"))
    elif row.get("_replaces"):
        old = row.get("_replaces") or {}
        marks.append("\u21b3 replaces {}".format(old.get("title") or old.get("id") or "?"))
    if row.get("_stale"):
        marks.append("\u26a0 STALE ({})".format(row.get("_stale")))
    mark = (" " + " ".join(marks)) if marks else ""
    idpart = " {{{}}}".format(mem_id) if mem_id else ""
    head = "[{}]{}{} {}".format(
        row.get("type"), mark, idpart, row.get("title") or row.get("path"))
    if row.get("type") == "map":
        return "{}\n{}".format(head, row.get("content") or "")
    body = " ".join((row.get("content") or "").split())[:300]
    loc = " (@ {})".format(row.get("path")) if row.get("path") and row.get("title") else ""
    return "{}{}\n{}".format(head, loc, body)


@mcp.tool()
def ask(query: str, limit: int = 8, type: Optional[str] = None,
        mode: Optional[str] = None) -> str:
    """Check whether memory already knows something before you answer.

    Returns a verdict line (HIT | WEAK | MISS) followed by the matching records.
    Call this first on every question; if HIT, base your answer on the records.
    """
    conn = retrieval.get_conn(ROOT)
    if conn is None:
        return "No memory initialized. Run 'ctxmem init' in the repo first."
    rows, used = retrieval.search(
        conn, query, ROOT, limit=limit, type_filter=type, mode_override=mode)
    label, detail = retrieval.verdict(rows, query)
    out = ["VERDICT: {} \u2014 {}".format(label, detail), "(mode: {})".format(used)]
    for row in rows:
        out.append(_format_row(row))
    return "\n\n".join(out)


@mcp.tool()
def context(query: str, budget: int, limit: int = 50,
            type: Optional[str] = None, mode: Optional[str] = None) -> dict:
    """Return budgeted context text with separate token and selection metadata.

    The budget covers the text field only, not MCP transport or metadata.
    Superseded records are excluded; stale records retain verification warnings.
    """
    return contextmod.build(ROOT, query, budget, limit, type, mode)


@mcp.tool()
def remember(content: str, type: str = "note", title: str = "", tags: str = "",
             supersedes: str = "", path: str = "") -> str:
    """Store a decision/note/session into the shared, git-committed memory.

    Set path to a repository-relative file to detect changes since saving.
    Set supersedes to the id of an earlier memory when this record corrects or
    replaces it; recall will then demote and flag the stale one.
    """
    root = ROOT
    base, jsonl_path, db_path = store.memory_paths(root)
    if not os.path.isdir(base):
        return "No memory initialized. Run 'ctxmem init' in the repo first."
    db_exists = os.path.exists(db_path)
    supersedes = (supersedes or "").strip()
    warn = ""
    if supersedes and db_exists:
        probe = retrieval.get_conn(root)
        if probe is not None and store.find_memory(probe, supersedes) is None:
            warn = " (warning: no memory with id {})".format(supersedes)
    rec = {
        "id": store.new_id(),
        "ts": store.now_iso(),
        "type": type,
        "branch": gitinfo.branch(root),
        "commit": gitinfo.commit(root),
        "path": path,
        "file_hash": store.file_hash(root, path),
        "title": title,
        "content": content,
        "tags": [t for t in tags.split(",") if t],
        "supersedes": supersedes,
    }
    store.append_jsonl(jsonl_path, rec)
    conn = retrieval.get_conn(root)
    if db_exists:
        rec["source"] = "memory"
        store.insert_row(conn, rec)
        conn.commit()
    tail = " (supersedes {})".format(supersedes) if supersedes else ""
    return "Remembered [{}] {} on branch {} [id {}]{}{}.".format(
        type, title or content[:40], rec["branch"], rec["id"], tail, warn)


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
