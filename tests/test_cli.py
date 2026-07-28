import io
from contextlib import redirect_stdout

import pytest

from ctxmem import cli, embeddings, retrieval, store


pytestmark = pytest.mark.skipif(
    not store.fts5_available(),
    reason="ctxmem needs sqlite3 with FTS5 enabled",
)


def run_cli(args):
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        cli.main(args)
    return stdout.getvalue()


def test_cli_init_remember_and_recall(tmp_path):
    init_out = run_cli(["--root", str(tmp_path), "init"])

    assert "Initialized memory" in init_out
    assert (tmp_path / ".ctxmem" / "memory.jsonl").exists()
    assert (tmp_path / ".ctxmem" / "config.json").exists()

    remember_out = run_cli([
        "--root",
        str(tmp_path),
        "remember",
        "--type",
        "decision",
        "--title",
        "Use keyword mode",
        "Keyword search is the stable default for ctxmem.",
    ])

    assert "Remembered [decision] Use keyword mode" in remember_out

    recall_out = run_cli(["--root", str(tmp_path), "recall", "stable keyword"])

    assert "Top 1 results" in recall_out
    assert "[decision] Use keyword mode" in recall_out
    assert "Keyword search is the stable default" in recall_out


def _remembered_id(output):
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("id:"):
            return line.split(":", 1)[1].strip()
    raise AssertionError("no id printed by remember:\n" + output)


def test_cli_remember_supersedes_demotes_old_record(tmp_path):
    run_cli(["--root", str(tmp_path), "init"])

    first = run_cli([
        "--root", str(tmp_path), "remember", "--type", "decision",
        "--title", "Secrets in .env",
        "Database password lives in a local .env file.",
    ])
    old_id = _remembered_id(first)

    second = run_cli([
        "--root", str(tmp_path), "remember", "--type", "decision",
        "--title", "Secrets in the vault",
        "--supersedes", old_id,
        "Database password now lives in the shared vault, not .env.",
    ])

    assert "supersedes {}".format(old_id) in second

    recall_out = run_cli([
        "--root", str(tmp_path), "recall", "database password secrets",
    ])

    assert "SUPERSEDED" in recall_out
    assert "replaces" in recall_out
    # The active (replacing) decision is listed before the superseded one.
    assert recall_out.index("replaces") < recall_out.index("SUPERSEDED")


def test_cli_ask_reports_hit_weak_and_miss(tmp_path):
    run_cli(["--root", str(tmp_path), "init"])
    run_cli([
        "--root", str(tmp_path), "remember", "--type", "decision",
        "--title", "Use keyword mode",
        "Keyword search is the stable default for ctxmem.",
    ])

    hit = run_cli(["--root", str(tmp_path), "ask", "stable keyword default"])
    assert "VERDICT: HIT" in hit
    assert "best answer memory is active decision 'Use keyword mode'" in hit

    miss = run_cli(["--root", str(tmp_path), "ask", "completely unrelated zxqw"])
    assert "VERDICT: MISS" in miss


def test_cli_ask_reports_weak_when_code_ranks_above_related_memory(tmp_path):
    run_cli(["--root", str(tmp_path), "init"])
    run_cli([
        "--root", str(tmp_path), "remember", "--type", "note",
        "--title", "Ask behavior",
        "Ask returns a verdict.",
    ])
    (tmp_path / "verdict.py").write_text(
        "def improve_ask_verdict_false_positive_ranking_symbols():\n"
        "    return 'improve ask verdict false positive ranking symbols'\n",
        encoding="utf-8",
    )
    run_cli(["--root", str(tmp_path), "sync"])

    out = run_cli([
        "--root", str(tmp_path), "ask",
        "improve ask verdict false positive ranking symbols",
    ])

    assert "VERDICT: WEAK" in out
    assert "closest match is code; related memories rank lower" in out


def test_verdict_treats_codebase_map_as_weak():
    label, detail = retrieval.verdict([{
        "type": "map",
        "title": "Codebase map",
        "content": "Project structure",
    }])

    assert label == "WEAK"
    assert "closest match is a codebase map" in detail


def test_verdict_rejects_generic_keyword_memory_match():
    label, detail = retrieval.verdict([{
        "type": "decision",
        "title": "Release workflow",
        "content": "Publish releases to PyPI from the main branch.",
        "tags": "release",
        "score": -1.0,
    }], "what is the next improvement for semantic recall quality")

    assert label == "WEAK"
    assert "matches too little of the question" in detail


def test_verdict_does_not_let_code_outrank_a_strong_answer_memory():
    label, detail = retrieval.verdict([
        {
            "type": "symbol",
            "title": "release_workflow",
            "content": "def release_workflow(): publish_to_pypi()",
            "score": -4.0,
        },
        {
            "type": "decision",
            "title": "Release workflow",
            "content": "The release workflow publishes to PyPI.",
            "tags": "release",
            "score": -2.0,
        },
    ], "release workflow PyPI")

    assert label == "HIT"
    assert "best answer memory is active decision 'Release workflow'" in detail


def test_cli_map_saves_structure_into_memory(tmp_path):
    run_cli(["--root", str(tmp_path), "init"])
    pkg = tmp_path / "src" / "demo"
    pkg.mkdir(parents=True)
    (pkg / "core.py").write_text(
        "from . import helper\n\n\ndef run():\n    return helper.value()\n",
        encoding="utf-8",
    )
    (pkg / "helper.py").write_text(
        "def value():\n    return 42\n",
        encoding="utf-8",
    )

    out = run_cli(["--root", str(tmp_path), "map"])
    assert "Saved codebase map" in out

    recall_out = run_cli(["--root", str(tmp_path), "recall", "codebase map", "--type", "map"])
    assert "[map]" in recall_out
    assert "src/demo/core.py" in recall_out
    assert "Local import graph" in recall_out


def test_cli_map_supersedes_previous_map(tmp_path):
    run_cli(["--root", str(tmp_path), "init"])
    (tmp_path / "a.py").write_text("def one():\n    return 1\n", encoding="utf-8")

    first = run_cli(["--root", str(tmp_path), "map"])
    assert "superseded" not in first

    second = run_cli(["--root", str(tmp_path), "map"])
    assert "superseded previous map" in second


def test_cli_update_instructions_refreshes_existing_file(tmp_path):
    run_cli(["--root", str(tmp_path), "init"])
    run_cli(["--root", str(tmp_path), "agent-init", "--agent", "copilot"])

    out = run_cli(["--root", str(tmp_path), "update-instructions"])
    assert "copilot-instructions.md" in out
    assert "Instructions refreshed" in out

    content = (tmp_path / ".github" / "copilot-instructions.md").read_text(encoding="utf-8")
    assert "Managed by ctxmem" in content


def test_cli_update_instructions_without_files_hints_agent_init(tmp_path):
    run_cli(["--root", str(tmp_path), "init"])

    out = run_cli(["--root", str(tmp_path), "update-instructions"])
    assert "Run 'ctxmem agent-init' first" in out


def _run_doctor(tmp_path):
    stdout = io.StringIO()
    code = 0
    with redirect_stdout(stdout):
        try:
            cli.main(["--root", str(tmp_path), "doctor"])
        except SystemExit as exc:
            code = exc.code
    return code, stdout.getvalue()


def test_cli_doctor_reports_not_ready_without_backend(tmp_path, monkeypatch):
    run_cli(["--root", str(tmp_path), "init"])
    monkeypatch.setattr(embeddings, "ollama_available", lambda cfg: False)
    monkeypatch.setattr(embeddings, "installed_models", lambda cfg: [])

    code, out = _run_doctor(tmp_path)

    assert code == 1
    assert "NOT READY" in out
    assert "Ollama reachable" in out
    assert "task start" in out  # actionable hint is shown


def test_cli_doctor_reports_ready_when_backend_ok(tmp_path, monkeypatch):
    run_cli(["--root", str(tmp_path), "init"])
    monkeypatch.setattr(embeddings, "sqlite_vec_available", lambda: True)
    monkeypatch.setattr(embeddings, "ollama_available", lambda cfg: True)
    monkeypatch.setattr(
        embeddings, "installed_models", lambda cfg: ["nomic-embed-text:latest"])
    monkeypatch.setattr(embeddings, "embed", lambda text, cfg: [0.1] * 8)

    code, out = _run_doctor(tmp_path)

    assert code == 0
    assert "READY" in out
    assert "NOT READY" not in out
    assert "live embedding call (8 dims)" in out
