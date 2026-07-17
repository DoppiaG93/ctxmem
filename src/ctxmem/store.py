"""
Storage layer.

Two artifacts live under `.ctxmem/`:

  memory.jsonl   -> source of truth. Human-readable, append-only, COMMITTED to git.
                    This is what you share with a colleague: they pull it and get
                    your exact project memory.

  index.db       -> derived SQLite full-text (FTS5) index. NOT committed.
                    Rebuilt on demand from memory.jsonl + the code on disk.

Because the source of truth is a text file inside the repo, the memory is
automatically branch-aware and merges like any other file.
"""

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone

MEMORY_DIR = ".ctxmem"
JSONL_NAME = "memory.jsonl"
DB_NAME = "index.db"
CONFIG_NAME = "config.json"
EMB_CACHE_NAME = "emb_cache.db"

DEFAULT_CONFIG = {
    "mode": "keyword",  # keyword | semantic | hybrid
    "embed_model": "nomic-embed-text",
    "ollama_url": "http://localhost:11434",
}


def memory_paths(root="."):
    base = os.path.join(root, MEMORY_DIR)
    return base, os.path.join(base, JSONL_NAME), os.path.join(base, DB_NAME)


def config_path(root="."):
    return os.path.join(root, MEMORY_DIR, CONFIG_NAME)


def emb_cache_path(root="."):
    """Path to the persistent embedding cache (keyed by content hash).

    Like index.db this file is derived and NOT committed; it survives full
    rebuilds so we only ever call the embedding backend for new/changed text.
    """
    return os.path.join(root, MEMORY_DIR, EMB_CACHE_NAME)


def load_config(root="."):
    cfg = dict(DEFAULT_CONFIG)
    path = config_path(root)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except (OSError, json.JSONDecodeError):
            pass
    return cfg


def save_config(root, cfg):
    with open(config_path(root), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def new_id():
    return uuid.uuid4().hex[:12]


def connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def fts5_available():
    try:
        c = sqlite3.connect(":memory:")
        c.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
        c.close()
        return True
    except sqlite3.OperationalError:
        return False


def init_schema(conn):
    # Columns without UNINDEXED are searchable; the rest are stored metadata.
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS mem USING fts5(
            mem_id UNINDEXED,
            type,
            branch UNINDEXED,
            commit_hash UNINDEXED,
            path,
            title,
            content,
            tags,
            source UNINDEXED,
            ts UNINDEXED,
            supersedes UNINDEXED
        )
        """
    )
    conn.commit()


def insert_row(conn, rec):
    conn.execute(
        "INSERT INTO mem "
        "(mem_id, type, branch, commit_hash, path, title, content, tags, source, ts, "
        "supersedes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            rec.get("id", new_id()),
            rec.get("type", "note"),
            rec.get("branch", ""),
            rec.get("commit", ""),
            rec.get("path", ""),
            rec.get("title", ""),
            rec.get("content", ""),
            " ".join(rec.get("tags", [])),
            rec.get("source", "memory"),
            rec.get("ts", ""),
            rec.get("supersedes", ""),
        ),
    )


def append_jsonl(jsonl_path, rec):
    with open(jsonl_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def read_jsonl(jsonl_path):
    if not os.path.exists(jsonl_path):
        return
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _fts_query(text):
    """Quote every token (so input can't break FTS5) and OR them together.

    OR + bm25 ranking gives useful "fuzzy" recall: a natural-language question
    still surfaces the most relevant records instead of requiring every word.
    """
    tokens = [t for t in text.replace('"', " ").split() if t]
    if not tokens:
        return '""'
    return " OR ".join('"{}"'.format(t) for t in tokens)


def search(conn, query, limit=10, type_filter=None):
    sql = (
        "SELECT mem_id, type, branch, commit_hash, path, title, content, tags, ts, "
        "bm25(mem) AS score FROM mem WHERE mem MATCH ?"
    )
    params = [_fts_query(query)]
    if type_filter:
        sql += " AND type = ?"
        params.append(type_filter)
    sql += " ORDER BY score LIMIT ?"
    params.append(limit)
    return conn.execute(sql, params).fetchall()


def recent(conn, limit=10):
    return conn.execute(
        "SELECT mem_id, type, branch, path, title, content, ts FROM mem "
        "WHERE source = 'memory' ORDER BY ts DESC LIMIT ?",
        (limit,),
    ).fetchall()


def counts(conn):
    return conn.execute(
        "SELECT type, COUNT(*) AS n FROM mem GROUP BY type ORDER BY n DESC"
    ).fetchall()


def find_memory(conn, mem_id):
    """Return the stored memory row for an id, or None."""
    return conn.execute(
        "SELECT mem_id, type, title, content FROM mem "
        "WHERE mem_id = ? AND source = 'memory' LIMIT 1",
        (mem_id,),
    ).fetchone()


def latest_memory_id(conn, type_):
    """Return the id of the most recent memory record of a given type, or None."""
    row = conn.execute(
        "SELECT mem_id FROM mem WHERE type = ? AND source = 'memory' "
        "ORDER BY ts DESC LIMIT 1",
        (type_,),
    ).fetchone()
    return row["mem_id"] if row else None


def supersede_index(conn):
    """Map how memory records supersede one another.

    Returns two dicts keyed by mem_id:
      superseded_by[old_id] = {"id": new_id, "title": new_title}
      replaces[new_id]      = {"id": old_id, "title": old_title}

    A record is "superseded" (stale) when its id appears in superseded_by.
    """
    titles = {}
    links = []
    for row in conn.execute(
        "SELECT mem_id, title, supersedes FROM mem WHERE source = 'memory'"
    ):
        titles[row["mem_id"]] = row["title"] or ""
        old = (row["supersedes"] or "").strip()
        if old:
            links.append((old, row["mem_id"]))
    superseded_by = {}
    replaces = {}
    for old_id, newer_id in links:
        superseded_by[old_id] = {"id": newer_id, "title": titles.get(newer_id, "")}
        replaces[newer_id] = {"id": old_id, "title": titles.get(old_id, "")}
    return superseded_by, replaces
