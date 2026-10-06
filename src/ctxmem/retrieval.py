"""
Central retrieval layer: builds the index and dispatches searches to the
configured mode (keyword / semantic / hybrid), with automatic fallback to
keyword when the semantic backend is unavailable.

Shared by both the CLI and the MCP server.
"""

import os
import re

from . import embeddings, gitinfo, store
from .indexer import index_code


ANSWER_MEMORY_TYPES = {"decision", "note", "session", "todo"}
QUESTION_WORDS = {
    "about", "and", "are", "come", "cosa", "del", "della", "delle", "degli",
    "dei", "deve", "di", "do", "does", "for", "how", "il", "improve",
    "improvement", "in", "is", "la", "le", "lo", "miglioramento", "migliorare",
    "must", "next", "of", "per", "progetto", "project", "prossimo", "qual",
    "quale", "quando", "restituire", "return", "should", "step", "the", "to",
    "un", "una", "what", "when", "which",
}


def meaningful_tokens(text):
    return {
        token for token in re.findall(r"\w+", (text or "").lower())
        if len(token) >= 3 and token not in QUESTION_WORDS
    }


def _keyword_match_is_strong(row, query):
    """Require a keyword HIT to cover at least half the meaningful question."""
    if "score" not in row or query is None:
        return True
    query_tokens = meaningful_tokens(query)
    if not query_tokens:
        return False
    record_text = " ".join([
        row.get("title") or "",
        row.get("content") or "",
        row.get("tags") or "",
    ])
    overlap = query_tokens & meaningful_tokens(record_text)
    return bool(overlap) and len(overlap) / len(query_tokens) >= 0.5


def verdict(rows, query=None):
    """Classify ranked search results for ``ask``.

    Code and maps are supporting context, so they do not outrank an explicit
    answer memory for verdict purposes. Keyword answer memories still need
    enough lexical overlap to avoid false HITs from generic matches.
    """
    if not rows:
        return "MISS", "memory has nothing on this; answer fresh, then remember it."

    active_mem = [
        row for row in rows
        if row.get("type") in ANSWER_MEMORY_TYPES and not row.get("_superseded")
    ]
    answer = next(
        (row for row in active_mem if _keyword_match_is_strong(row, query)),
        None,
    )
    if answer:
        kind = answer.get("type")
        title = answer.get("title") or (answer.get("content") or "")[:60]
        stale = " (it looks stale — verify against the code)" if answer.get("_stale") else ""
        return "HIT", "best answer memory is active {} '{}'{}.".format(kind, title, stale)

    top = rows[0]
    top_type = top.get("type")
    if top_type == "symbol":
        reason = "the closest match is code"
    elif top_type == "map":
        reason = "the closest match is a codebase map"
    elif top.get("_superseded"):
        reason = "the closest memory is superseded"
    elif active_mem:
        reason = "the closest memory matches too little of the question"
    else:
        reason = "the closest result is not an answer memory"
    if active_mem:
        reason += "; related memories rank lower"
    return "WEAK", "{}; verify and consider remembering.".format(reason)


def rebuild(root, verbose=False):
    """Drop and rebuild index.db from JSONL + code, plus embeddings if enabled."""
    _, jsonl_path, db_path = store.memory_paths(root)
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = store.connect(db_path)
    store.init_schema(conn)

    mem_rows = 0
    for rec in store.read_jsonl(jsonl_path):
        rec["source"] = "memory"
        store.insert_row(conn, rec)
        mem_rows += 1
    conn.commit()

    code_rows = index_code(conn, root, gitinfo.branch(root), gitinfo.commit(root))

    cfg = store.load_config(root)
    emb_rows = 0
    if cfg["mode"] in ("semantic", "hybrid"):
        if embeddings.available(cfg):
            emb_rows = embeddings.build(conn, cfg, store.emb_cache_path(root))
        elif verbose:
            print("[warn] mode '{}' needs sqlite-vec + Ollama; "
                  "falling back to keyword.".format(cfg["mode"]))
    return conn, mem_rows, code_rows, emb_rows


def get_conn(root):
    base, _, db_path = store.memory_paths(root)
    if not os.path.isdir(base):
        return None
    if not os.path.exists(db_path):
        conn, _, _, _ = rebuild(root)
        return conn
    conn = store.connect(db_path)
    if "file_hash" not in {row["name"] for row in conn.execute("PRAGMA table_info(mem)")}:
        conn.close()
        conn, _, _, _ = rebuild(root)
    return conn


def _key(row):
    return (row.get("type"), row.get("path"), row.get("title"))


def _merge(primary, secondary, limit):
    seen = set()
    out = []
    for row in list(primary) + list(secondary):
        k = _key(row)
        if k in seen:
            continue
        seen.add(k)
        out.append(row)
        if len(out) >= limit:
            break
    return out


def _annotate(conn, rows, root):
    """Flag stale and superseded records; push superseded ones to the bottom.

    - Staleness: a memory record whose `path` points to a file that no longer
      exists on disk is marked `_stale` — the code changed, so the agent should
      verify (and likely supersede) that memory.
    - Fingerprints: changed or unreadable tracked files require verification.
      Legacy memories without a fingerprint retain missing-file detection only.
    - Supersede: a record replaced by a newer decision is marked and demoted,
      but still returned so the agent can see *why* it changed.
    """
    baselines = dict(conn.execute(
        "SELECT mem_id, file_hash FROM mem WHERE source = 'memory' AND file_hash != ''"
    ))
    current_hashes = {}
    for row in rows:
        if row.get("type") == "symbol":
            continue
        path = (row.get("path") or "").strip()
        if path and not os.path.exists(os.path.join(root, path)):
            row["_stale"] = "missing file: {}".format(path)
        elif path and baselines.get(row.get("mem_id")):
            if path not in current_hashes:
                current_hashes[path] = store.file_hash(root, path)
            current = current_hashes[path]
            if not current:
                row["_stale"] = "cannot verify file: {}".format(path)
            elif current != baselines[row["mem_id"]]:
                row["_stale"] = "file changed since saved; verify: {}".format(path)

    superseded_by, replaces = store.supersede_index(conn)
    if superseded_by:
        for row in rows:
            mem_id = row.get("mem_id")
            if not mem_id:
                continue
            if mem_id in superseded_by:
                row["_superseded"] = True
                row["_superseded_by"] = superseded_by[mem_id]
            if mem_id in replaces:
                row["_replaces"] = replaces[mem_id]
    # Stable sort: active records keep their order, superseded ones sink last.
    return sorted(rows, key=lambda r: 1 if r.get("_superseded") else 0)


def search(conn, query, root, limit=10, type_filter=None, mode_override=None):
    """Return (rows_as_dicts, mode_used)."""
    cfg = store.load_config(root)
    mode = mode_override or cfg["mode"]

    def keyword():
        return [dict(r) for r in store.search(conn, query, limit, type_filter)]

    def finish(rows, used):
        return _annotate(conn, rows, root), used

    if mode == "keyword":
        return finish(keyword(), "keyword")

    if not embeddings.available(cfg):
        return finish(keyword(), "keyword (fallback)")

    if not embeddings.index_fresh(conn):
        embeddings.build(conn, cfg, store.emb_cache_path(root))

    semantic = embeddings.search(conn, query, cfg, limit, type_filter)
    if mode == "semantic":
        return finish(semantic, "semantic")

    return finish(_merge(semantic, keyword(), limit), "hybrid")
