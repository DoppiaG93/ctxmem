"""
Central retrieval layer: builds the index and dispatches searches to the
configured mode (keyword / semantic / hybrid), with automatic fallback to
keyword when the semantic backend is unavailable.

Shared by both the CLI and the MCP server.
"""

import os

from . import embeddings, gitinfo, store
from .indexer import index_code


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
            emb_rows = embeddings.build(conn, cfg)
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
    return store.connect(db_path)


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


def search(conn, query, root, limit=10, type_filter=None, mode_override=None):
    """Return (rows_as_dicts, mode_used)."""
    cfg = store.load_config(root)
    mode = mode_override or cfg["mode"]

    def keyword():
        return [dict(r) for r in store.search(conn, query, limit, type_filter)]

    if mode == "keyword":
        return keyword(), "keyword"

    if not embeddings.available(cfg):
        return keyword(), "keyword (fallback)"

    if not embeddings.index_fresh(conn):
        embeddings.build(conn, cfg)

    semantic = embeddings.search(conn, query, cfg, limit, type_filter)
    if mode == "semantic":
        return semantic, "semantic"

    return _merge(semantic, keyword(), limit), "hybrid"
