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
