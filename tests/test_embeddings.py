import json

import pytest

from ctxmem import embeddings, retrieval, store


pytest.importorskip("sqlite_vec", reason="semantic backend needs sqlite-vec")

pytestmark = pytest.mark.skipif(
    not store.fts5_available(),
    reason="ctxmem needs sqlite3 with FTS5 enabled",
)


def _fake_embed(text, _cfg):
    """Deterministic tiny vector derived from the content hash (no network)."""
    h = embeddings.text_hash(text)
    return [float(int(h[j:j + 2], 16)) for j in range(0, 8, 2)]


def _semantic_project(tmp_path, records):
    root = str(tmp_path)
    memory_dir = tmp_path / ".ctxmem"
    memory_dir.mkdir()
    cfg = dict(store.DEFAULT_CONFIG)
    cfg["mode"] = "semantic"
    store.save_config(root, cfg)
    (memory_dir / "memory.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return root, memory_dir / "memory.jsonl"


def test_text_hash_is_stable_and_content_sensitive():
    assert embeddings.text_hash("hello") == embeddings.text_hash("hello")
    # Leading/trailing whitespace is normalized away.
    assert embeddings.text_hash("  hello  ") == embeddings.text_hash("hello")
    assert embeddings.text_hash("hello") != embeddings.text_hash("world")


def test_build_uses_cache_to_skip_unchanged_rows(tmp_path, monkeypatch):
    calls = {"n": 0}

    def counting_embed(text, cfg):
        calls["n"] += 1
        return _fake_embed(text, cfg)

    monkeypatch.setattr(embeddings, "embed", counting_embed)
    monkeypatch.setattr(embeddings, "ollama_available", lambda cfg: True)

    root, jsonl = _semantic_project(tmp_path, [
        {"id": "a", "type": "note", "content": "first note"},
        {"id": "b", "type": "note", "content": "second note"},
    ])

    _, _, _, emb_rows = retrieval.rebuild(root)
    assert emb_rows == 2
    assert calls["n"] == 2  # both embedded on the first build

    # A third record is added; the two existing ones are served from cache.
    with open(jsonl, "a", encoding="utf-8") as f:
        f.write(json.dumps({"id": "c", "type": "note", "content": "third note"}) + "\n")

    _, _, _, emb_rows2 = retrieval.rebuild(root)
    assert emb_rows2 == 3
    assert calls["n"] == 3  # only the new record hit the backend


def test_index_fresh_tracks_content_not_just_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(embeddings, "embed", _fake_embed)
    monkeypatch.setattr(embeddings, "ollama_available", lambda cfg: True)

    root, _ = _semantic_project(tmp_path, [
        {"id": "a", "type": "note", "content": "first note"},
        {"id": "b", "type": "note", "content": "second note"},
    ])

    conn, _, _, _ = retrieval.rebuild(root)
    assert embeddings.index_fresh(conn) is True

    # Adding a not-yet-embedded mem row makes the vector index stale.
    store.insert_row(conn, {"id": "z", "type": "note", "content": "unindexed"})
    conn.commit()
    assert embeddings.index_fresh(conn) is False


def test_index_fresh_false_without_content_hash_column(tmp_path, monkeypatch):
    monkeypatch.setattr(embeddings, "embed", _fake_embed)
    monkeypatch.setattr(embeddings, "ollama_available", lambda cfg: True)

    root, _ = _semantic_project(tmp_path, [
        {"id": "a", "type": "note", "content": "first note"},
    ])

    conn, _, _, _ = retrieval.rebuild(root)
    # Simulate an index.db written by an older ctxmem (no content_hash column).
    conn.execute("ALTER TABLE emb_meta RENAME COLUMN content_hash TO legacy")
    conn.commit()
    assert embeddings.index_fresh(conn) is False
