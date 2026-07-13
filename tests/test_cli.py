import io
from contextlib import redirect_stdout

import pytest

from ctxmem import cli, store


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
    assert "1 decision" in hit

    miss = run_cli(["--root", str(tmp_path), "ask", "completely unrelated zxqw"])
    assert "VERDICT: MISS" in miss


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
