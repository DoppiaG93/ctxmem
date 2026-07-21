"""Opt-in integration tests that exercise the real semantic backend.

These require a running Ollama endpoint with the embedding model pulled — the
intended way is the Lima VM in `ollama/` (`task start` then `task pull`). They
are skipped unless you explicitly opt in, so CI (which has no Ollama) never runs
them:

    CTXMEM_OLLAMA_IT=1 python -m pytest tests/test_integration_ollama.py -v

They validate two things end to end against a live backend:
  1. semantic recall actually ranks the relevant record first for a paraphrase;
  2. the on-disk embedding cache makes a re-sync skip unchanged content, so only
     new/edited records hit Ollama.
"""

import json
import os

import pytest

from ctxmem import embeddings, retrieval, store


def _skip_reason():
    if os.environ.get("CTXMEM_OLLAMA_IT") != "1":
        return "set CTXMEM_OLLAMA_IT=1 to run the Ollama integration tests"
    if not store.fts5_available():
        return "sqlite3 without FTS5"
    if not embeddings.sqlite_vec_available():
        return "sqlite-vec not installed"
    if not embeddings.ollama_available(dict(store.DEFAULT_CONFIG)):
        return "no Ollama endpoint at the configured URL (start the VM first)"
    return None


_SKIP = _skip_reason()
pytestmark = pytest.mark.skipif(_SKIP is not None, reason=_SKIP or "")


def _semantic_project(tmp_path, records):
    root = str(tmp_path)
    memory_dir = tmp_path / ".ctxmem"
    memory_dir.mkdir()
    cfg = dict(store.DEFAULT_CONFIG)
    cfg["mode"] = "semantic"
    store.save_config(root, cfg)
    jsonl = memory_dir / "memory.jsonl"
    jsonl.write_text(
        "".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return root, memory_dir, jsonl


def test_semantic_recall_ranks_relevant_record_first(tmp_path):
    root, _, _ = _semantic_project(tmp_path, [
        {"id": "auth", "type": "decision", "title": "Authentication",
         "content": "User login and passwords are handled by the auth service."},
        {"id": "pay", "type": "decision", "title": "Payments",
         "content": "Billing and invoices go through the Stripe integration."},
    ])

    conn, _, _, emb_rows = retrieval.rebuild(root)
    assert emb_rows == 2

    rows, used = retrieval.search(conn, "how do we sign in users", root)

    assert used == "semantic"
    assert rows and rows[0]["mem_id"] == "auth"


def test_cache_makes_resync_skip_unchanged_content(tmp_path, monkeypatch):
    root, memory_dir, jsonl = _semantic_project(tmp_path, [
        {"id": "a", "type": "note", "content": "first note about caching"},
        {"id": "b", "type": "note", "content": "second note about vectors"},
    ])

    real_embed = embeddings.embed
    calls = {"n": 0}

    def counting_embed(text, cfg):
        calls["n"] += 1
        return real_embed(text, cfg)

    monkeypatch.setattr(embeddings, "embed", counting_embed)

    retrieval.rebuild(root)
    assert calls["n"] == 2  # both records embedded on the first sync
    assert (memory_dir / store.EMB_CACHE_NAME).exists()

    # Add a third record; the two existing ones must come from the cache.
    with open(jsonl, "a", encoding="utf-8") as f:
        f.write(json.dumps(
            {"id": "c", "type": "note", "content": "third note about hashing"}) + "\n")

    calls["n"] = 0
    _, _, _, emb_rows = retrieval.rebuild(root)

    assert emb_rows == 3
    assert calls["n"] == 1  # only the new record hit the backend
