"""Budget invariants, selection policy, and command integration."""
import sys
import types

import pytest

from ctxmem import cli, context, embeddings


BYTES = (lambda text: len(text.encode("utf-8")), "test-bytes")


def test_pack_priorities_warnings_duplicates_and_whole_blocks():
    rows = [
        {"type": "symbol", "content": "def login(): pass", "path": "auth.py:1"},
        {"type": "decision", "mem_id": "old", "content": "obsolete", "_superseded": True},
        {"type": "note", "content": "verify me", "_stale": "file changed"},
        {"type": "decision", "mem_id": "new", "content": "Use JWT"},
        {"type": "decision", "mem_id": "new", "content": "Use JWT"},
    ]
    result = context.pack(rows, 1000, BYTES)
    assert result["selected"] == 3
    assert "obsolete" not in result["text"]
    assert "Use JWT" in result["text"]
    assert "def login" in result["text"]
    assert "@ auth.py:1" in result["text"]
    assert "WARNING: STALE — file changed" in result["text"]
    assert result["tokens"] == BYTES[0](result["text"])
    assert result["policy"] == "relevance-aware-v1"


@pytest.mark.parametrize("budget", [1, 10, 40, 100, 1000])
def test_budget_includes_unicode_headers_and_separators(budget):
    rows = [{"type": "decision", "title": "日本語 🧠", "content": "è" * 50},
            {"type": "note", "content": "small"}]
    result = context.pack(rows, budget, BYTES)
    assert BYTES[0](result["text"]) <= budget
    if "è" in result["text"]:
        assert "è" * 50 in result["text"]


def test_oversized_record_does_not_block_smaller_one():
    result = context.pack([{"type": "decision", "content": "x" * 1000},
                           {"type": "note", "content": "small"}], 30, BYTES)
    assert result["selected"] == 1
    assert result["text"] == "[note]\nsmall\n"
    exact = context.pack([{"type": "note", "content": "small"}], 13, BYTES)
    assert exact["tokens"] <= 13


def test_relevance_can_beat_a_distant_decision():
    rows = [
        {"type": "symbol", "content": "relevant-code"},
        {"type": "note", "content": "old-a", "_superseded": True},
        {"type": "note", "content": "old-b", "_superseded": True},
        {"type": "decision", "content": "distant-decision"},
    ]
    symbol_cost = BYTES[0]("[symbol]\nrelevant-code\n")
    decision_cost = BYTES[0]("[decision]\ndistant-decision\n")
    result = context.pack(rows, max(symbol_cost, decision_cost), BYTES)

    assert "relevant-code" in result["text"]
    assert "distant-decision" not in result["text"]


def test_nearby_decision_gets_modest_authority_bonus():
    rows = [
        {"type": "symbol", "content": "code-result"},
        {"type": "decision", "content": "saved-choice"},
    ]
    budget = max(BYTES[0]("[symbol]\ncode-result\n"),
                 BYTES[0]("[decision]\nsaved-choice\n"))
    result = context.pack(rows, budget, BYTES)

    assert "saved-choice" in result["text"]
    assert "code-result" not in result["text"]


def test_explain_reports_selection_and_skip_reasons():
    rows = [
        {"type": "decision", "mem_id": "active", "content": "chosen"},
        {"type": "note", "mem_id": "old", "content": "obsolete",
         "_superseded": True},
        {"type": "symbol", "content": "too-large-" * 20},
    ]
    result = context.pack(rows, 40, BYTES, explain=True)
    by_label = {item["label"]: item for item in result["selection"]}

    assert by_label["chosen"]["status"] == "selected"
    assert by_label["obsolete"]["reason"] == "superseded memory"
    assert "does not fit" in by_label[("too-large-" * 20)[:40]]["reason"]
    assert all("utility" in item and "tokens" in item for item in result["selection"])


def test_keyword_policy_rejects_zero_overlap_fillers():
    rows = [
        {"type": "symbol", "content": "authentication handler"},
        {"type": "note", "content": "tiny unrelated filler"},
    ]
    result = context.pack(rows, 1000, BYTES, explain=True,
                          query="authentication security", keyword=True)

    assert "authentication handler" in result["text"]
    assert "unrelated filler" not in result["text"]
    filler = next(item for item in result["selection"] if item["label"].startswith("tiny"))
    assert filler["reason"] == "no meaningful keyword overlap"


def test_semantic_policy_keeps_results_without_literal_overlap():
    rows = [{"type": "note", "content": "credential validation rules"}]
    result = context.pack(rows, 1000, BYTES, query="authentication security",
                          keyword=False)

    assert "credential validation rules" in result["text"]


def test_freshness_and_relative_size_affect_selection():
    stale = [
        {"type": "decision", "content": "stale-choice", "_stale": "file changed"},
        {"type": "note", "content": "fresh-note"},
    ]
    stale_budget = max(BYTES[0]("[decision]\nWARNING: STALE — file changed\nstale-choice\n"),
                       BYTES[0]("[note]\nfresh-note\n"))
    fresh_result = context.pack(stale, stale_budget, BYTES)
    assert "fresh-note" in fresh_result["text"]
    assert "stale-choice" not in fresh_result["text"]

    large = "x" * 110
    sized = [
        {"type": "note", "content": large},
        {"type": "symbol", "content": "compact-code"},
    ]
    large_cost = BYTES[0]("[note]\n" + large + "\n")
    compact_result = context.pack(sized, large_cost, BYTES)
    assert "compact-code" in compact_result["text"]
    assert large not in compact_result["text"]


def test_byte_fallback(monkeypatch):
    monkeypatch.setitem(sys.modules, "tiktoken", None)
    count, method = context.token_counter()
    assert count("") == 0
    assert count("🧠") == 4
    assert "conservative" in method


def test_cli_output_and_filters(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(context, "token_counter", lambda: BYTES)
    base = ["--root", str(tmp_path)]
    cli.main(base + ["init"])
    cli.main(base + ["remember", "--type", "decision", "--title", "Auth", "Use JWT auth"])
    capsys.readouterr()
    cli.main(base + ["context", "auth", "--budget", "200", "--type", "decision"])
    out = capsys.readouterr()
    assert "Use JWT auth" in out.out
    assert "Context:" not in out.out
    assert "1/1 records" in out.err
    assert "policy: relevance-aware-v1" in out.err
    assert BYTES[0](out.out) <= 200
    cli.main(base + ["context", "auth", "--budget", "200", "--explain"])
    explained = capsys.readouterr()
    assert "Use JWT auth" in explained.out
    assert "selected #1" in explained.err
    assert "utility" in explained.err
    cli.main(base + ["context", "auth", "--budget", "1"])
    out = capsys.readouterr()
    assert out.out == ""
    assert "No complete active record fits" in out.err
    cli.main(base + ["context", "zzzznomatch", "--budget", "200"])
    assert capsys.readouterr().out == ""
    monkeypatch.setattr(embeddings, "available", lambda cfg: False)
    result = context.build(str(tmp_path), "auth", 200, mode="semantic")
    assert result["mode"] == "keyword (fallback)"
    assert "Use JWT auth" in result["text"]


@pytest.mark.parametrize("args", [["--budget", "0"], ["--budget", "-1"],
                                  ["--budget", "abc"], ["--budget", "1", "--limit", "0"]])
def test_cli_rejects_invalid_budget_or_limit(args, tmp_path):
    with pytest.raises(SystemExit):
        cli.main(["--root", str(tmp_path), "context", "auth"] + args)


def test_empty_query_and_missing_memory(tmp_path):
    with pytest.raises(ValueError, match="query"):
        context.build(str(tmp_path), "  ", 100)
    with pytest.raises(ValueError, match="No memory"):
        context.build(str(tmp_path), "auth", 100)


def test_tiktoken_counter_and_exact_boundary(monkeypatch):
    calls = []

    class Encoder:
        def encode_ordinary(self, text):
            calls.append(text)
            return list(text)

    monkeypatch.setitem(sys.modules, "tiktoken", types.SimpleNamespace(
        get_encoding=lambda name: Encoder()))
    count, method = context.token_counter()
    assert count("<|endoftext|>") == 13
    assert method == "tiktoken/cl100k_base"
    row = {"type": "note", "content": "hello"}
    full = context.pack([row], 100, (count, method))
    assert context.pack([row], full["tokens"], (count, method))["text"] == full["text"]
    assert context.pack([row], full["tokens"] - 1, (count, method))["text"] == ""
    assert calls
