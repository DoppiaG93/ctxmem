"""
Build a structural map of the repository: the file/symbol tree plus a
best-effort local import graph for Python.

The map is meant to be stored in memory (via `ctxmem map`) so an agent knows how
the codebase is laid out before it starts reading files. It reuses the same file
filters and symbol extraction as the indexer, so it stays consistent with what
`recall` can surface.
"""

import ast
import os

from . import indexer

_MAX_SYMS_PER_FILE = 12


def _iter_source_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d not in indexer.SKIP_DIRS and not d.endswith(".egg-info")
        ]
        for fn in sorted(filenames):
            if os.path.splitext(fn)[1] in indexer.CODE_EXT:
                full = os.path.join(dirpath, fn)
                yield full, os.path.relpath(full, root).replace("\\", "/")


def _read(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except OSError:
        return ""


def _dedupe(items):
    seen = set()
    out = []
    for it in items:
        if it and it not in seen:
            seen.add(it)
            out.append(it)
    return out


def _symbols(full, text):
    return _dedupe(name for name, _line, _body in indexer.extract_symbols(full, text))


def _local_roots(files):
    """Top-level module names that live in this repo (for import filtering)."""
    roots = set()
    for _full, rel in files:
        parts = rel.split("/")
        head = parts[0]
        roots.add(head[:-3] if head.endswith(".py") else head)
        if head == "src" and len(parts) > 1:
            nxt = parts[1]
            roots.add(nxt[:-3] if nxt.endswith(".py") else nxt)
    return roots


def _py_imports(text, local_roots):
    """Return the local modules a Python file imports (relative + in-repo)."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []
    deps = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:  # relative import: from . / from .mod
                deps.append(node.module or ", ".join(a.name for a in node.names))
            elif node.module and node.module.split(".")[0] in local_roots:
                deps.append(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in local_roots:
                    deps.append(alias.name)
    return _dedupe(deps)


def build_map(root):
    """Return (markdown_body, file_count, symbol_count)."""
    files = list(_iter_source_files(root))
    roots = _local_roots(files)
    total_syms = 0
    by_dir = {}
    import_lines = []

    for full, rel in files:
        text = _read(full)
        syms = _symbols(full, text)
        total_syms += len(syms)
        directory = os.path.dirname(rel) or "."
        by_dir.setdefault(directory, []).append((os.path.basename(rel), syms))
        if full.endswith(".py"):
            deps = _py_imports(text, roots)
            if deps:
                import_lines.append("- `{}` \u2192 {}".format(rel, ", ".join(deps)))

    tree_lines = []
    for directory in sorted(by_dir):
        tree_lines.append("- `{}`".format(directory if directory == "." else directory + "/"))
        for fname, syms in sorted(by_dir[directory]):
            shown = ", ".join(syms[:_MAX_SYMS_PER_FILE])
            more = "" if len(syms) <= _MAX_SYMS_PER_FILE else \
                " (+{} more)".format(len(syms) - _MAX_SYMS_PER_FILE)
            desc = (" \u2014 " + shown + more) if shown else ""
            tree_lines.append("  - `{}`{}".format(fname, desc))

    parts = ["## Structure ({} files, {} symbols)".format(len(files), total_syms)]
    parts.extend(tree_lines)
    if import_lines:
        parts.append("")
        parts.append("## Local import graph (Python)")
        parts.extend(import_lines)
    return "\n".join(parts), len(files), total_syms
