"""File baselines survive indexing without rewriting memories."""
import importlib
import json
import sys
import types

import pytest

from ctxmem import cli, embeddings, retrieval, store


def initialize(root):
    cli.main(["--root", str(root), "init"])
    (root / "auth.py").write_text("expiry = 24\n", encoding="utf-8")


@pytest.mark.parametrize("change", ["unchanged", "modified", "missing", "directory"])
def test_cli_file_baseline_survives_sync(tmp_path, capsys, change):
    initialize(tmp_path)
    cli.main(["--root", str(tmp_path), "remember", "--path", "auth.py",
              "--title", "Token expiry", "Tokens expire after 24 hours"])
    memory = tmp_path / ".ctxmem" / "memory.jsonl"
    original = memory.read_bytes()
    assert json.loads(original)["file_hash"] == store.file_hash(tmp_path, "auth.py")
    target = tmp_path / "auth.py"
    if change == "modified":
        target.write_text("expiry = 1\n", encoding="utf-8")
    elif change in ("missing", "directory"):
        target.unlink()
        if change == "directory":
            target.mkdir()
    cli.main(["--root", str(tmp_path), "sync"])
    capsys.readouterr()
    cli.main(["--root", str(tmp_path), "ask", "Token expiry"])
    output = capsys.readouterr().out
    expected = {"modified": "file changed since saved", "missing": "missing file",
                "directory": "cannot verify file"}
    if change == "unchanged":
        assert "STALE" not in output
    else:
        assert expected[change] in output
        assert "STALE" in output
    assert memory.read_bytes() == original


def test_legacy_index_rebuild_does_not_invent_baselines(tmp_path):
    initialize(tmp_path)
    _, jsonl, db = store.memory_paths(tmp_path)
    store.append_jsonl(jsonl, {"id": "old", "path": "auth.py", "content": "expiry"})
    conn = store.connect(db)
    conn.execute("DROP TABLE IF EXISTS mem")
    conn.execute("CREATE VIRTUAL TABLE mem USING fts5(content)")
    conn.commit()
    conn.close()
    conn = retrieval.get_conn(tmp_path)
    rows, _ = retrieval.search(conn, "expiry", tmp_path, type_filter="note")
    assert len(rows) == 1
    assert "_stale" not in rows[0]
    assert "file_hash" not in list(store.read_jsonl(jsonl))[0]
    conn.close()


def test_mcp_remember_path_and_semantic_result_annotation(tmp_path, monkeypatch):
    # Exercise tools without requiring the optional MCP transport.
    fake = types.ModuleType("mcp.server.fastmcp")

    class FastMCP:
        def __init__(self, _name):
            pass

        def tool(self):
            return lambda func: func

    fake.FastMCP = FastMCP
    monkeypatch.setitem(sys.modules, "mcp.server.fastmcp", fake)
    monkeypatch.delitem(sys.modules, "ctxmem.mcp_server", raising=False)
    server = importlib.import_module("ctxmem.mcp_server")
    monkeypatch.setattr(server, "ROOT", str(tmp_path))
    initialize(tmp_path)
    server.remember("Tokens expire after 24 hours", title="Token expiry", path="auth.py")
    assert "STALE" not in server.recall("Token expiry")
    (tmp_path / "auth.py").write_text("expiry = 1\n", encoding="utf-8")
    assert "file changed since saved" in server.ask("Token expiry")
    assert "file changed since saved" in server.recall("Token expiry")
    packed = server.context("Token expiry", budget=1000, type="note")
    assert "WARNING: STALE" in packed["text"]
    assert packed["tokens"] <= 1000
    assert packed["selected"] == 1
    record = list(store.read_jsonl(store.memory_paths(tmp_path)[1]))[0]
    # Semantic results carry IDs but not file_hash.
    conn = retrieval.get_conn(tmp_path)
    monkeypatch.setattr(embeddings, "available", lambda cfg: True)
    monkeypatch.setattr(embeddings, "index_fresh", lambda connection: True)
    monkeypatch.setattr(embeddings, "search", lambda *args: [
        {"mem_id": record["id"], "type": "note", "path": "auth.py"}])
    for mode in ("semantic", "hybrid"):
        rows, used = retrieval.search(conn, "Token expiry", tmp_path, mode_override=mode)
        assert used == mode
        assert "file changed" in rows[0]["_stale"]
    conn.close()


def test_file_hash_optional_and_binary(tmp_path):
    assert store.file_hash(tmp_path, "") == ""
    assert store.file_hash(tmp_path, "missing") == ""
    assert store.file_hash(tmp_path, ".") == ""
    (tmp_path / "binary").write_bytes(b"\x00\xff")
    assert len(store.file_hash(tmp_path, "binary")) == 64
