import json

import pytest

from ctxmem import retrieval, store


pytestmark = pytest.mark.skipif(
    not store.fts5_available(),
    reason="ctxmem needs sqlite3 with FTS5 enabled",
)


def test_read_jsonl_ignores_blank_and_invalid_lines(tmp_path):
    jsonl_path = tmp_path / "memory.jsonl"
    jsonl_path.write_text(
        "\n"
        "{\"type\": \"note\", \"content\": \"valid\"}\n"
        "not-json\n"
        + json.dumps({"type": "decision", "content": "also valid"})
        + "\n",
        encoding="utf-8",
    )

    rows = list(store.read_jsonl(str(jsonl_path)))

    assert [row["content"] for row in rows] == ["valid", "also valid"]


def test_search_handles_quotes_in_user_query(tmp_path):
    db_path = tmp_path / "index.db"
    conn = store.connect(str(db_path))
    store.init_schema(conn)
    store.insert_row(conn, {
        "id": "mem-1",
        "type": "decision",
        "title": "Search mode",
        "content": "Keyword recall is the stable default.",
        "tags": ["search"],
    })
    conn.commit()

    rows = store.search(conn, '"keyword" default')

    assert len(rows) == 1
    assert rows[0]["title"] == "Search mode"


def test_search_supersede_demotes_and_flags_old_record(tmp_path):
    memory_dir = tmp_path / ".ctxmem"
    memory_dir.mkdir()
    store.save_config(str(tmp_path), store.DEFAULT_CONFIG)
    (memory_dir / "memory.jsonl").write_text(
        json.dumps({
            "id": "old-1",
            "type": "decision",
            "title": "Store secrets in .env",
            "content": "Database password lives in a local .env file.",
        }) + "\n"
        + json.dumps({
            "id": "new-1",
            "type": "decision",
            "title": "Store secrets in the vault",
            "content": "Database password now lives in the shared vault, not .env.",
            "supersedes": "old-1",
        }) + "\n",
        encoding="utf-8",
    )

    conn, _, _, _ = retrieval.rebuild(str(tmp_path))
    rows, _ = retrieval.search(conn, "database password secrets", str(tmp_path))

    by_id = {row["mem_id"]: row for row in rows}
    assert by_id["old-1"].get("_superseded") is True
    assert by_id["old-1"]["_superseded_by"]["id"] == "new-1"
    assert by_id["new-1"].get("_superseded") is not True
    assert by_id["new-1"]["_replaces"]["id"] == "old-1"

    # The active decision must rank ahead of the superseded one.
    order = [row["mem_id"] for row in rows if row["mem_id"] in ("old-1", "new-1")]
    assert order.index("new-1") < order.index("old-1")


def test_supersede_index_maps_relationships(tmp_path):
    db_path = tmp_path / "index.db"
    conn = store.connect(str(db_path))
    store.init_schema(conn)
    store.insert_row(conn, {
        "id": "a", "type": "decision", "title": "Old", "content": "old",
    })
    store.insert_row(conn, {
        "id": "b", "type": "decision", "title": "New", "content": "new",
        "supersedes": "a",
    })
    conn.commit()

    superseded_by, replaces = store.supersede_index(conn)

    assert superseded_by == {"a": {"id": "b", "title": "New"}}
    assert replaces == {"b": {"id": "a", "title": "Old"}}


def test_search_flags_stale_record_with_missing_path(tmp_path):
    memory_dir = tmp_path / ".ctxmem"
    memory_dir.mkdir()
    store.save_config(str(tmp_path), store.DEFAULT_CONFIG)
    (memory_dir / "memory.jsonl").write_text(
        json.dumps({
            "id": "d1",
            "type": "decision",
            "title": "Auth lives in old module",
            "content": "Login logic is in legacy auth handler.",
            "path": "src/legacy/auth.py",
        }) + "\n",
        encoding="utf-8",
    )

    conn, _, _, _ = retrieval.rebuild(str(tmp_path))
    rows, _ = retrieval.search(conn, "login auth logic", str(tmp_path))

    stale = [r for r in rows if r.get("mem_id") == "d1"]
    assert stale and "src/legacy/auth.py" in stale[0]["_stale"]


def test_search_does_not_flag_record_with_existing_path(tmp_path):
    memory_dir = tmp_path / ".ctxmem"
    memory_dir.mkdir()
    store.save_config(str(tmp_path), store.DEFAULT_CONFIG)
    src = tmp_path / "src"
    src.mkdir()
    (src / "auth.py").write_text("def login():\n    return True\n", encoding="utf-8")
    (memory_dir / "memory.jsonl").write_text(
        json.dumps({
            "id": "d1",
            "type": "decision",
            "title": "Auth module",
            "content": "Login logic lives in the auth module.",
            "path": "src/auth.py",
        }) + "\n",
        encoding="utf-8",
    )

    conn, _, _, _ = retrieval.rebuild(str(tmp_path))
    rows, _ = retrieval.search(conn, "login auth logic", str(tmp_path))

    row = next(r for r in rows if r.get("mem_id") == "d1")
    assert "_stale" not in row


def test_rebuild_indexes_memory_and_code_symbols(tmp_path):
    memory_dir = tmp_path / ".ctxmem"
    memory_dir.mkdir()
    store.save_config(str(tmp_path), store.DEFAULT_CONFIG)
    (memory_dir / "memory.jsonl").write_text(
        json.dumps({
            "id": "decision-1",
            "type": "decision",
            "title": "Index code",
            "content": "ctxmem indexes code symbols during sync.",
            "tags": ["index"],
        })
        + "\n",
        encoding="utf-8",
    )
    source_dir = tmp_path / "src" / "demo"
    source_dir.mkdir(parents=True)
    (source_dir / "sample.py").write_text(
        "def searchable_function():\n"
        "    return 'indexed symbol body'\n",
        encoding="utf-8",
    )

    conn, mem_rows, code_rows, emb_rows = retrieval.rebuild(str(tmp_path))

    assert mem_rows == 1
    assert code_rows == 1
    assert emb_rows == 0

    rows, used = retrieval.search(conn, "indexed symbol body", str(tmp_path))

    assert used == "keyword"
    assert any(row["type"] == "symbol" and row["title"] == "searchable_function"
               for row in rows)
