"""
Token-efficiency benchmark: compare what you'd feed an LLM *with* ctxmem
(only the relevant recall snippets) versus *without* it (dumping whole files,
the whole memory, or the whole repo).

Token counting uses tiktoken when installed (accurate for OpenAI-family models),
otherwise a portable ~chars/4 heuristic.
"""

import os

from . import store
from .indexer import CODE_EXT, SKIP_DIRS

# Substrings / patterns that mark a file as test code. Test files are excluded
# from the baseline by default: a real agent would rarely dump entire test
# suites to answer a question, so counting them inflates the "without ctxmem"
# side and makes the benchmark look better than it honestly is.
_TEST_DIR_PARTS = ("/tests/", "/test/", "/testing/", "/__tests__/")


def is_test_file(path):
    """Heuristic: does this path look like test code rather than app source?"""
    p = "/" + path.replace("\\", "/").lower().strip("/") + "/"
    base = os.path.basename(path.replace("\\", "/")).lower()
    if any(part in p for part in _TEST_DIR_PARTS):
        return True
    if base.startswith("test_") or base.endswith("_test.py"):
        return True
    if base in ("tests.py", "test.py", "conftest.py"):
        return True
    return False


def count_tokens(text):
    """Return (n_tokens, method_label)."""
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text)), "tiktoken/cl100k_base"
    except Exception:
        return max(1, round(len(text) / 4)), "approx(chars/4)"


def recall_payload(rows):
    """Reconstruct the context block a recall would inject into the model."""
    parts = []
    for r in rows:
        head = "[{}] {}".format(r.get("type", ""), r.get("title") or "")
        path = r.get("path") or ""
        body = r.get("content") or ""
        block = head
        if path:
            block += "\n@ {}".format(path)
        if body:
            block += "\n{}".format(body)
        parts.append(block)
    return "\n\n".join(parts)


def _strip_line(path):
    """'src/foo.py:42' -> 'src/foo.py' (symbol paths carry a line number)."""
    if ":" in path:
        head, tail = path.rsplit(":", 1)
        if tail.isdigit():
            return head
    return path


def referenced_files(rows, root, include_tests=False):
    """Unique existing files referenced by the recall results (full paths).

    Test files are skipped unless include_tests is True.
    """
    out = []
    seen = set()
    for r in rows:
        p = _strip_line(r.get("path") or "")
        if not p:
            continue
        if not include_tests and is_test_file(p):
            continue
        full = os.path.join(root, p)
        if full in seen:
            continue
        if os.path.isfile(full):
            seen.add(full)
            out.append(full)
    return out


def _read(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except OSError:
        return ""


def whole_memory_text(root):
    _, jsonl_path, _ = store.memory_paths(root)
    return _read(jsonl_path)


def whole_repo_text(root, include_tests=False):
    chunks = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if os.path.splitext(fn)[1] not in CODE_EXT:
                continue
            full = os.path.join(dirpath, fn)
            if not include_tests and is_test_file(os.path.relpath(full, root)):
                continue
            chunks.append(_read(full))
    chunks.append(whole_memory_text(root))
    return "\n".join(chunks)


def baseline_text(rows, root, kind, include_tests=False):
    """Text a naive approach would feed for this query."""
    if kind == "memory":
        return whole_memory_text(root), ["<whole memory.jsonl>"]
    if kind == "repo":
        return whole_repo_text(root, include_tests), ["<all indexed code + memory.jsonl>"]
    # kind == "files": full text of the files that hold the answer
    files = referenced_files(rows, root, include_tests)
    if not files:
        # No source files behind the results (pure notes): the naive fallback
        # is to paste the whole memory.
        return whole_memory_text(root), ["<whole memory.jsonl (no source files)>"]
    return "\n".join(_read(f) for f in files), [
        os.path.relpath(f, root) for f in files]


def exploration_steps(rows, root, include_tests=False):
    """Estimate agent round-trips ("premium requests") with vs without ctxmem.

    Model (deliberately conservative and easy to defend):
      * Without ctxmem the agent must first orient itself (1 search/grep step)
        and then open each relevant file to read the answer (1 step per file).
        -> steps = 1 + <number of source files it has to open>
      * With ctxmem a single `recall` returns every relevant snippet at once.
        -> steps = 1

    Returns (steps_without, steps_with, n_files).
    """
    files = referenced_files(rows, root, include_tests)
    n = len(files)
    steps_without = 1 + n if n else 1
    steps_with = 1
    return steps_without, steps_with, n


# --------------------------------------------------------------------------
# Tiny dependency-free SVG bar charts (render inline on GitHub markdown).
# --------------------------------------------------------------------------

_COL_WITHOUT = "#e8663c"   # warm orange = the costly "without ctxmem" side
_COL_WITH = "#1f9e8f"      # teal = the lean "with ctxmem" side
_COL_TEXT = "#222222"
_COL_GRID = "#dddddd"


def _svg_escape(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _fmt(n):
    """Human-friendly integer: 1234567 -> '1.23M', 15087 -> '15.1k'."""
    n = float(n)
    if n >= 1_000_000:
        return "{:.2f}M".format(n / 1_000_000)
    if n >= 1_000:
        return "{:.1f}k".format(n / 1_000)
    return "{:.0f}".format(n)


def svg_grouped_bars(title, subtitle, rows, path,
                     label_without="without ctxmem", label_with="with ctxmem"):
    """Write a grouped horizontal bar chart to `path`.

    rows: list of (label, without_value, with_value). The last row may be a
    TOTAL; it is rendered in bold automatically if its label is 'TOTAL'.
    """
    width = 940
    left = 300           # room for query labels
    right = 90           # room for value labels
    top = 74
    row_h = 46           # per query (two bars + gap)
    bar_h = 15
    gap = 4
    plot_w = width - left - right
    height = top + row_h * len(rows) + 54

    max_val = max([max(w, c) for _, w, c in rows] + [1])

    def bar_len(v):
        return max(1.0, (v / max_val) * plot_w)

    out = []
    out.append(
        '<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        'viewBox="0 0 {w} {h}" font-family="Segoe UI, Helvetica, Arial, sans-serif">'
        .format(w=width, h=height))
    out.append('<rect width="{}" height="{}" fill="#ffffff"/>'.format(width, height))
    out.append('<text x="24" y="34" font-size="21" font-weight="700" fill="{}">{}</text>'
               .format(_COL_TEXT, _svg_escape(title)))
    if subtitle:
        out.append('<text x="24" y="56" font-size="13" fill="#666666">{}</text>'
                   .format(_svg_escape(subtitle)))

    # legend
    lx = width - right - 250
    out.append('<rect x="{}" y="20" width="13" height="13" fill="{}"/>'.format(lx, _COL_WITHOUT))
    out.append('<text x="{}" y="31" font-size="12" fill="{}">{}</text>'
               .format(lx + 19, _COL_TEXT, _svg_escape(label_without)))
    out.append('<rect x="{}" y="40" width="13" height="13" fill="{}"/>'.format(lx, _COL_WITH))
    out.append('<text x="{}" y="51" font-size="12" fill="{}">{}</text>'
               .format(lx + 19, _COL_TEXT, _svg_escape(label_with)))

    y = top
    for label, w_val, c_val in rows:
        is_total = str(label).strip().upper() == "TOTAL"
        weight = "700" if is_total else "400"
        if is_total:
            out.append('<line x1="24" y1="{y}" x2="{x2}" y2="{y}" stroke="{c}"/>'
                       .format(y=y - 8, x2=width - 24, c=_COL_GRID))
        out.append('<text x="{x}" y="{y}" font-size="13" font-weight="{fw}" '
                   'fill="{c}" text-anchor="end">{t}</text>'
                   .format(x=left - 12, y=y + bar_h, fw=weight, c=_COL_TEXT,
                           t=_svg_escape(label)))
        # without bar
        out.append('<rect x="{x}" y="{y}" width="{wd:.1f}" height="{bh}" rx="2" fill="{c}"/>'
                   .format(x=left, y=y, wd=bar_len(w_val), bh=bar_h, c=_COL_WITHOUT))
        out.append('<text x="{x:.1f}" y="{y}" font-size="12" fill="#555">{v}</text>'
                   .format(x=left + bar_len(w_val) + 6, y=y + bar_h - 2, v=_fmt(w_val)))
        # with bar
        y2 = y + bar_h + gap
        out.append('<rect x="{x}" y="{y}" width="{wd:.1f}" height="{bh}" rx="2" fill="{c}"/>'
                   .format(x=left, y=y2, wd=bar_len(c_val), bh=bar_h, c=_COL_WITH))
        out.append('<text x="{x:.1f}" y="{y}" font-size="12" fill="#555">{v}</text>'
                   .format(x=left + bar_len(c_val) + 6, y=y2 + bar_h - 2, v=_fmt(c_val)))
        y += row_h

    out.append('<text x="24" y="{y}" font-size="11" fill="#999">'
               'Generated by `ctxmem bench` \u2014 lower is better.</text>'
               .format(y=height - 18))
    out.append('</svg>\n')
    svg = "\n".join(out)
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    return path
