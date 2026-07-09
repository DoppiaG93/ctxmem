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
