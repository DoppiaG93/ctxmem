"""
Semantic backend: local embeddings via Ollama + vector storage via sqlite-vec.

Both are open source and run entirely on your machine:
  - Ollama  (https://ollama.com) generates embeddings offline. Pull the model once:
        ollama pull nomic-embed-text
  - sqlite-vec is a loadable SQLite extension that stores vectors and does KNN.

Everything here is optional: if the extra isn't installed or Ollama isn't running,
callers fall back to keyword (FTS5) search.

Embeddings are cached on disk (`.ctxmem/emb_cache.db`, keyed by content hash)
so a rebuild only calls the backend for genuinely new or edited text — the
vector tables themselves are cheap to recreate locally.
"""

import json
import hashlib
import importlib.util
import sqlite3
import urllib.error
import urllib.request

DEFAULT_MODEL = "nomic-embed-text"
DEFAULT_URL = "http://localhost:11434"


def text_hash(text):
    """Stable content key used to cache and diff embeddings across rebuilds."""
    return hashlib.sha256((text or "").strip().encode("utf-8")).hexdigest()


def _text_of(row):
    return (row["content"] or row["title"] or "").strip()



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
    """True if emb_meta already reflects the current mem rows by content.

    We compare the *set of content hashes* rather than just row counts, so a
    change that keeps the row count constant (e.g. a supersede that rewrites a
    record's content) still forces a rebuild. A missing content_hash column
    means an index.db from an older ctxmem, which is treated as not fresh so it
    gets rebuilt with the current schema.
    """
    try:
        has = conn.execute(
            "SELECT name FROM sqlite_master WHERE name='vec_mem'").fetchone()
        if not has:
            return False
        cols = [r[1] for r in conn.execute("PRAGMA table_info(emb_meta)")]
        if "content_hash" not in cols:
            return False
        emb_hashes = [r[0] for r in conn.execute(
            "SELECT content_hash FROM emb_meta")]
        if not emb_hashes:
            return False
        mem_hashes = [
            text_hash(_text_of(r))
            for r in conn.execute("SELECT content, title FROM mem")
        ]
        return sorted(emb_hashes) == sorted(mem_hashes)
    except Exception:
        return False


def _open_cache(cache_path):
    """Open (creating if needed) the persistent content-hash embedding cache."""
    conn = sqlite3.connect(cache_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS emb_cache "
        "(hash TEXT PRIMARY KEY, dim INTEGER, vec BLOB)")
    return conn


def build(conn, cfg, cache_path=None):
    """(Re)create the vector tables, embedding only new/changed content.

    vec_mem/emb_meta are always rebuilt (cheap, local), but the expensive
    embedding calls are served from a persistent cache keyed by content hash.
    On a normal sync only genuinely new or edited rows hit the backend.
    """
    import sqlite_vec
    load_extension(conn)

    rows = conn.execute(
        "SELECT mem_id, type, path, title, content FROM mem").fetchall()
    if not rows:
        return 0

    cache = _open_cache(cache_path) if cache_path else None

    prepared = []  # (row, content_hash, serialized_vec)
    dim = None
    for row in rows:
        h = text_hash(_text_of(row))
        blob = None
        if cache is not None:
            hit = cache.execute(
                "SELECT dim, vec FROM emb_cache WHERE hash=?", (h,)).fetchone()
            if hit:
                dim, blob = hit[0], hit[1]
        if blob is None:
            vec = embed(_text_of(row), cfg)
            dim = len(vec)
            blob = sqlite_vec.serialize_float32(vec)
            if cache is not None:
                cache.execute(
                    "INSERT OR REPLACE INTO emb_cache(hash, dim, vec) "
                    "VALUES (?,?,?)", (h, dim, blob))
        prepared.append((row, h, blob))

    if cache is not None:
        cache.commit()
        cache.close()

    conn.execute("DROP TABLE IF EXISTS vec_mem")
    conn.execute(
        "CREATE VIRTUAL TABLE vec_mem USING vec0(embedding float[{}])".format(dim))
    conn.execute("DROP TABLE IF EXISTS emb_meta")
    conn.execute(
        "CREATE TABLE emb_meta "
        "(id INTEGER PRIMARY KEY, mem_id TEXT, type TEXT, path TEXT, "
        "title TEXT, content TEXT, content_hash TEXT)")

    for i, (row, h, blob) in enumerate(prepared, start=1):
        conn.execute(
            "INSERT INTO vec_mem(rowid, embedding) VALUES (?, ?)", (i, blob))
        conn.execute(
            "INSERT INTO emb_meta"
            "(id, mem_id, type, path, title, content, content_hash) "
            "VALUES (?,?,?,?,?,?,?)",
            (i, row["mem_id"], row["type"], row["path"], row["title"],
             row["content"], h))
    conn.commit()
    return len(prepared)



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
        "SELECT m.mem_id, m.type, m.path, m.title, m.content, knn.distance "
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
