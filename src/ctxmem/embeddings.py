"""
Semantic backend: local embeddings via Ollama + vector storage via sqlite-vec.

Both are open source and run entirely on your machine:
  - Ollama  (https://ollama.com) generates embeddings offline. Pull the model once:
        ollama pull nomic-embed-text
  - sqlite-vec is a loadable SQLite extension that stores vectors and does KNN.

Everything here is optional: if the extra isn't installed or Ollama isn't running,
callers fall back to keyword (FTS5) search.
"""

import json
import importlib.util
import urllib.error
import urllib.request

DEFAULT_MODEL = "nomic-embed-text"
DEFAULT_URL = "http://localhost:11434"


def sqlite_vec_available():
    return importlib.util.find_spec("sqlite_vec") is not None


def ollama_available(cfg):
    url = cfg.get("ollama_url", DEFAULT_URL).rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def available(cfg):
    return sqlite_vec_available() and ollama_available(cfg)


def load_extension(conn):
    import sqlite_vec
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)


def embed(text, cfg):
    url = cfg.get("ollama_url", DEFAULT_URL).rstrip("/") + "/api/embeddings"
    body = json.dumps({
        "model": cfg.get("embed_model", DEFAULT_MODEL),
        "prompt": text or "",
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read())
    return payload["embedding"]


def index_fresh(conn):
    """True if the vector index exists and covers every mem row."""
    try:
        has = conn.execute(
            "SELECT name FROM sqlite_master WHERE name='vec_mem'").fetchone()
        if not has:
            return False
        n_emb = conn.execute("SELECT COUNT(*) FROM emb_meta").fetchone()[0]
        n_mem = conn.execute("SELECT COUNT(*) FROM mem").fetchone()[0]
        return n_emb == n_mem and n_emb > 0
    except Exception:
        return False


def build(conn, cfg):
    """Embed every indexed row and (re)create the vector tables."""
    import sqlite_vec
    load_extension(conn)

    rows = conn.execute(
        "SELECT type, path, title, content FROM mem").fetchall()
    if not rows:
        return 0

    def text_of(row):
        return (row["content"] or row["title"] or "").strip()

    first = embed(text_of(rows[0]), cfg)
    dim = len(first)

    conn.execute("DROP TABLE IF EXISTS vec_mem")
    conn.execute(
        "CREATE VIRTUAL TABLE vec_mem USING vec0(embedding float[{}])".format(dim))
    conn.execute("DROP TABLE IF EXISTS emb_meta")
    conn.execute(
        "CREATE TABLE emb_meta "
        "(id INTEGER PRIMARY KEY, type TEXT, path TEXT, title TEXT, content TEXT)")

    def insert(i, vec, row):
        conn.execute(
            "INSERT INTO vec_mem(rowid, embedding) VALUES (?, ?)",
            (i, sqlite_vec.serialize_float32(vec)))
        conn.execute(
            "INSERT INTO emb_meta(id, type, path, title, content) VALUES (?,?,?,?,?)",
            (i, row["type"], row["path"], row["title"], row["content"]))

    insert(1, first, rows[0])
    for i, row in enumerate(rows[1:], start=2):
        insert(i, embed(text_of(row), cfg), row)
    conn.commit()
    return len(rows)


def search(conn, query, cfg, limit=8, type_filter=None):
    import sqlite_vec
    load_extension(conn)
    qvec = sqlite_vec.serialize_float32(embed(query, cfg))
    k = limit * 4 if type_filter else limit
    rows = conn.execute(
        "WITH knn AS ("
        "  SELECT rowid, distance FROM vec_mem "
        "  WHERE embedding MATCH ? ORDER BY distance LIMIT ?"
        ") "
        "SELECT m.type, m.path, m.title, m.content, knn.distance "
        "FROM knn JOIN emb_meta m ON m.id = knn.rowid ORDER BY knn.distance",
        (qvec, k),
    ).fetchall()

    out = []
    for r in rows:
        d = dict(r)
        if type_filter and d["type"] != type_filter:
            continue
        out.append(d)
        if len(out) >= limit:
            break
    return out
