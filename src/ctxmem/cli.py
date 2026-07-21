"""
ctxmem command line.

    ctxmem init [--mode keyword|semantic|hybrid]   set up .ctxmem/ in the repo
    ctxmem mode [keyword|semantic|hybrid]          show or change search mode
    ctxmem remember "..."                          store a decision/note/session
    ctxmem recall "query" [--mode ...]             search memory + code
    ctxmem ask "question"                          recall + HIT/WEAK/MISS verdict
    ctxmem sync                                    rebuild the index
    ctxmem map                                     save a codebase structure map to memory
    ctxmem log                                      recent memories
    ctxmem status                                  what is indexed
    ctxmem hook install|uninstall                  git post-commit auto-sync
    ctxmem agent-init [--agent ...] [--mcp]         wire up Copilot/Codex/agents
    ctxmem update-instructions [--mcp]             refresh agent instructions after upgrade
    ctxmem bench "query"                            token usage: with vs without ctxmem

Shareability: commit .ctxmem/memory.jsonl and .ctxmem/config.json. A colleague
pulls them and gets the same context (index rebuilds automatically).
"""

import argparse
import os
import sys

from . import bench as benchmod
from . import codemap, embeddings, gitinfo, retrieval, store

MODES = ["keyword", "semantic", "hybrid"]


def _require_memory(root):
    base, _, _ = store.memory_paths(root)
    if not os.path.isdir(base):
        sys.exit("No memory here. Run 'ctxmem init' first.")


def cmd_init(args):
    root = args.root
    base, jsonl_path, _ = store.memory_paths(root)
    if not store.fts5_available():
        sys.exit("Your Python's sqlite3 has no FTS5 support; ctxmem needs it.")
    os.makedirs(base, exist_ok=True)
    if not os.path.exists(jsonl_path):
        with open(jsonl_path, "a", encoding="utf-8"):
            pass
    cfg = store.load_config(root)
    cfg["mode"] = args.mode
    store.save_config(root, cfg)
    with open(os.path.join(base, ".gitignore"), "w", encoding="utf-8") as f:
        f.write("index.db\n")
    print("Initialized memory at {} (mode: {})".format(base, args.mode))
    if args.mode != "keyword":
        print("[beta] semantic/hybrid search is experimental and under active testing.")
        if not embeddings.available(cfg):
            print("[warn] semantic backend not ready (need 'pip install \"ctxmem[semantic]\"' "
                  "+ a running Ollama). recall will fall back to keyword until then.")
    print("Commit .ctxmem/memory.jsonl and .ctxmem/config.json to share it.")


def cmd_mode(args):
    root = args.root
    _require_memory(root)
    cfg = store.load_config(root)
    if args.value is None:
        print("mode: {}".format(cfg["mode"]))
        ok = embeddings.available(cfg)
        print("semantic backend: {}".format(
            "available" if ok else "unavailable (need sqlite-vec + Ollama)"))
        return
    cfg["mode"] = args.value
    store.save_config(root, cfg)
    print("mode set to {}".format(args.value))
    if args.value != "keyword":
        print("[beta] semantic/hybrid search is experimental and under active testing.")
        if not embeddings.available(cfg):
            print("[warn] semantic backend not available yet; recall falls back to keyword.")


def cmd_remember(args):
    root = args.root
    _require_memory(root)
    _, jsonl_path, db_path = store.memory_paths(root)
    db_exists = os.path.exists(db_path)
    supersedes = (getattr(args, "supersedes", "") or "").strip()
    if supersedes:
        conn = retrieval.get_conn(root)
        if conn is not None and store.find_memory(conn, supersedes) is None:
            print("[warn] --supersedes {}: no memory with that id; "
                  "recording anyway.".format(supersedes), file=sys.stderr)
    rec = {
        "id": store.new_id(),
        "ts": store.now_iso(),
        "type": args.type,
        "branch": gitinfo.branch(root),
        "commit": gitinfo.commit(root),
        "path": args.path or "",
        "title": args.title or "",
        "content": args.content,
        "tags": args.tags.split(",") if args.tags else [],
        "supersedes": supersedes,
    }
    store.append_jsonl(jsonl_path, rec)
    conn = retrieval.get_conn(root)
    if db_exists:
        rec["source"] = "memory"
        store.insert_row(conn, rec)
        conn.commit()
    suffix = " (supersedes {})".format(supersedes) if supersedes else ""
    print("Remembered [{}] {} (branch={}, commit={}){}".format(
        rec["type"], rec["title"] or rec["content"][:40],
        rec["branch"], rec["commit"], suffix))
    print("  id: {}".format(rec["id"]))


def _print_row(row):
    kind = row.get("type", "")
    title = row.get("title") or ""
    path = row.get("path") or ""
    marks = []
    if row.get("_superseded"):
        by = row.get("_superseded_by") or {}
        marks.append("\u26a0 SUPERSEDED by {}".format(by.get("title") or by.get("id") or "?"))
    elif row.get("_replaces"):
        old = row.get("_replaces") or {}
        marks.append("\u21b3 replaces {}".format(old.get("title") or old.get("id") or "?"))
    if row.get("_stale"):
        marks.append("\u26a0 STALE ({})".format(row.get("_stale")))
    mark = (" " + " ".join(marks)) if marks else ""
    print("  [{}]{} {}".format(kind, mark, title if title else path))
    if path and title:
        print("      @ {}".format(path))
    if row.get("type") == "map":
        for cl in (row.get("content") or "").splitlines():
            print("      {}".format(cl))
        return
    snippet = " ".join((row.get("content") or "").split())
    if snippet:
        print("      {}".format(snippet[:160]))


def _verdict(rows):
    """Classify a result set so an agent can decide if memory already knows.

    HIT  -> memory holds at least one active (non-superseded) decision/note.
    WEAK -> only related code symbols, or every memory match is superseded.
    MISS -> nothing matched.
    """
    if not rows:
        return "MISS", "memory has nothing on this; answer fresh, then remember it."
    active_mem = [r for r in rows
                  if r.get("type") != "symbol" and not r.get("_superseded")]
    if active_mem:
        kinds = {}
        for r in active_mem:
            kinds[r.get("type", "note")] = kinds.get(r.get("type", "note"), 0) + 1
        summary = ", ".join(
            "{} {}{}".format(n, k, "" if n == 1 else "s") for k, n in kinds.items())
        note = ""
        if any(r.get("_stale") for r in active_mem):
            note = " (some records look stale \u2014 verify against the code)"
        return "HIT", "memory has {}{}.".format(summary, note)
    return "WEAK", ("no stored decision \u2014 only related code/superseded notes; "
                    "verify and consider remembering.")


def cmd_recall(args):
    root = args.root
    conn = retrieval.get_conn(root)
    if conn is None:
        sys.exit("No memory here. Run 'ctxmem init' first.")
    rows, used = retrieval.search(
        conn, args.query, root, limit=args.limit,
        type_filter=args.type, mode_override=args.mode)
    if not rows:
        print("No matches for: {}".format(args.query))
        return
    print("Top {} results for '{}' [{}]:".format(len(rows), args.query, used))
    for row in rows:
        _print_row(row)


def cmd_ask(args):
    root = args.root
    conn = retrieval.get_conn(root)
    if conn is None:
        sys.exit("No memory here. Run 'ctxmem init' first.")
    rows, used = retrieval.search(
        conn, args.query, root, limit=args.limit,
        type_filter=args.type, mode_override=args.mode)
    verdict, detail = _verdict(rows)
    print("VERDICT: {} \u2014 {}".format(verdict, detail))
    if not rows:
        return
    print("Top {} results for '{}' [{}]:".format(len(rows), args.query, used))
    for row in rows:
        _print_row(row)


def cmd_sync(args):
    _require_memory(args.root)
    _, mem_rows, code_rows, emb_rows = retrieval.rebuild(args.root, verbose=True)
    msg = "Index rebuilt: {} memory records, {} code symbols".format(mem_rows, code_rows)
    if emb_rows:
        msg += ", {} embeddings".format(emb_rows)
    print(msg + ".")


def cmd_log(args):
    _require_memory(args.root)
    conn = retrieval.get_conn(args.root)
    rows = store.recent(conn, limit=args.limit)
    if not rows:
        print("No memories yet. Use 'ctxmem remember'.")
        return
    for row in rows:
        print("- {} [{}] {}".format(
            (row["ts"] or "")[:19], row["type"], row["title"] or row["content"][:60]))


def cmd_status(args):
    root = args.root
    _require_memory(root)
    conn = retrieval.get_conn(root)
    cfg = store.load_config(root)
    print("Repo branch : {}".format(gitinfo.branch(root)))
    print("Repo commit : {}".format(gitinfo.commit(root)))
    print("Search mode : {}".format(cfg["mode"]))
    print("Semantic    : {}".format(
        "available" if embeddings.available(cfg) else "unavailable"))
    print("Indexed content:")
    for row in store.counts(conn):
        print("  {:10s} {}".format(row["type"], row["n"]))


def cmd_doctor(args):
    """Check the semantic (Ollama) backend end to end, with fix-it hints."""
    cfg = store.load_config(args.root)
    url = cfg.get("ollama_url", embeddings.DEFAULT_URL)
    model = cfg.get("embed_model", embeddings.DEFAULT_MODEL)
    state = {"ok": True}

    def check(label, passed, hint=""):
        print("[{}] {}".format("OK  " if passed else "FAIL", label))
        if not passed:
            state["ok"] = False
            if hint:
                print("       -> {}".format(hint))

    print("ctxmem doctor - semantic backend check")
    print("  mode  : {}".format(cfg["mode"]))
    print("  ollama: {}".format(url))
    print("  model : {}".format(model))
    print()

    check("sqlite3 has FTS5 (keyword search)", store.fts5_available(),
          "your Python's sqlite3 lacks FTS5; keyword search won't work.")

    has_vec = embeddings.sqlite_vec_available()
    check("sqlite-vec installed (vector search)", has_vec,
          "pip install \"ctxmem[semantic]\"")

    reachable = embeddings.ollama_available(cfg)
    check("Ollama reachable at {}".format(url), reachable,
          "start it: 'cd ollama && task start' (Lima VM) or 'ollama serve'.")

    models = embeddings.installed_models(cfg) if reachable else []
    has_model = any(
        m == model or m.split(":")[0] == model.split(":")[0] for m in models)
    check("embedding model '{}' pulled".format(model), reachable and has_model,
          "pull it: 'cd ollama && task pull MODEL={0}' or 'ollama pull {0}'."
          .format(model))

    if has_vec and reachable and has_model:
        try:
            vec = embeddings.embed("ctxmem doctor connectivity test", cfg)
            check("live embedding call ({} dims)".format(len(vec)), bool(vec),
                  "the model returned an empty vector.")
        except Exception as exc:  # noqa: BLE001 - report any backend failure
            check("live embedding call", False, "embed failed: {}".format(exc))
    else:
        check("live embedding call", False, "skipped until the above pass.")

    print()
    if state["ok"]:
        print("Semantic backend READY. Turn it on with 'ctxmem mode semantic'.")
    else:
        print("Semantic backend NOT READY - keyword search still works "
              "(recall falls back automatically).")
    sys.exit(0 if state["ok"] else 1)


HOOK_MARKER = "# ctxmem post-commit hook"


def _hook_path(root):
    return os.path.join(root, ".git", "hooks", "post-commit")


def cmd_hook(args):
    root = args.root
    if not os.path.isdir(os.path.join(root, ".git")):
        sys.exit("Not a git repository (no .git/ found).")
    hook = _hook_path(root)

    if args.action == "uninstall":
        if os.path.exists(hook):
            os.remove(hook)
            print("Removed post-commit hook.")
        else:
            print("No hook to remove.")
        return

    if os.path.exists(hook):
        with open(hook, "r", encoding="utf-8") as f:
            if HOOK_MARKER not in f.read():
                sys.exit("A different post-commit hook already exists; not overwriting.")
    os.makedirs(os.path.dirname(hook), exist_ok=True)
    script = (
        "#!/usr/bin/env sh\n"
        "{marker}\n"
        "'{py}' -m ctxmem.cli --root '{root}' sync >/dev/null 2>&1\n"
        "exit 0\n"
    ).format(marker=HOOK_MARKER, py=sys.executable, root=os.path.abspath(root))
    with open(hook, "w", encoding="utf-8") as f:
        f.write(script)
    os.chmod(hook, 0o755)
    print("Installed post-commit hook -> {}".format(hook))
    print("The memory index will now rebuild automatically after each commit.")


AGENT_MARK_BEGIN = "<!-- ctxmem:begin (managed by `ctxmem agent-init`) -->"
AGENT_MARK_END = "<!-- ctxmem:end -->"

AGENT_PROTOCOL = """This repo has a `ctxmem` memory: a shared, git-committed record of
decisions and code context. Treat it as your first source of truth and keep it
correct. Follow this loop on EVERY request, without being asked.

**1. Recall first — before answering.**
Before you respond to a question or start a task, query the memory to check
whether the answer is already known:

```bash
ctxmem ask "<the user's question or task, in a few words>"
```

`ask` prints a verdict: **HIT** (memory has an answer — base your reply on the
listed records), **WEAK** (only related code/superseded notes — verify), or
**MISS** (nothing — answer fresh, then remember it). Do this even for questions
you think you can answer from your own context.

**2. Reconcile — decide who is right.**
If what the memory says conflicts with your own context or with the current
code, do not silently pick one. Verify against the actual code in the repo:

- If the **code/reality** proves the memory is outdated, correct the memory
  (step 3) and tell the user what changed.
- If the **memory** is right and your context was stale, trust the memory.

Records shown with `⚠ SUPERSEDED` are already outdated — use the newer one.
Records shown with `⚠ STALE` point at code that no longer exists — verify against
the repo and supersede them if they are wrong.

**3. Remember — persist every decision and correction.**
When you make or confirm an important decision, save it:

```bash
ctxmem remember --type decision --title "Short title" "Detailed decision text"
```

When you find that an existing memory is wrong or obsolete, replace it instead
of just adding a new one (this demotes and flags the old record in recall):

```bash
ctxmem remember --type decision --title "Corrected title" \\
  --supersedes <old-memory-id> "What is now true and why it changed"
```

Each `remember` prints the new record's `id`; use it as the `--supersedes`
target later. After changing code, run `ctxmem sync` to rebuild the index.

If your agent supports the MCP protocol instead of running shell commands, use
the MCP tools `recall(...)` and `remember(..., supersedes="<id>")` the same way."""

MCP_JSON = """{
  "servers": {
    "ctxmem": {
      "command": "ctxmem-mcp",
      "env": {
        "CTXMEM_ROOT": "${workspaceFolder}"
      }
    }
  }
}
"""


def _ctxmem_version():
    from . import __version__
    return __version__


def _write_managed_instructions(path, default_title):
    """Create or idempotently update a Markdown instructions file."""
    footer = ("\n\n_Managed by ctxmem {} \u2014 run `ctxmem update-instructions` "
              "after upgrading._").format(_ctxmem_version())
    block = "{begin}\n{body}{footer}\n{end}\n".format(
        begin=AGENT_MARK_BEGIN, body=AGENT_PROTOCOL, footer=footer, end=AGENT_MARK_END)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(default_title + "\n\n" + block)
        return "created " + path
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if AGENT_MARK_BEGIN in content and AGENT_MARK_END in content:
        pre = content.split(AGENT_MARK_BEGIN, 1)[0]
        post = content.split(AGENT_MARK_END, 1)[1]
        with open(path, "w", encoding="utf-8") as f:
            f.write(pre.rstrip("\n") + "\n\n" + block + post.lstrip("\n"))
        return "updated ctxmem section in " + path
    sep = "" if content.endswith("\n\n") else ("\n" if content.endswith("\n") else "\n\n")
    with open(path, "a", encoding="utf-8") as f:
        f.write(sep + "\n" + block)
    return "appended ctxmem section to " + path


def _write_copilot_instructions(root):
    path = os.path.join(root, ".github", "copilot-instructions.md")
    return _write_managed_instructions(path, "# Project memory")


def _write_codex_instructions(root):
    path = os.path.join(root, "AGENTS.md")
    return _write_managed_instructions(path, "# Project memory")


def _write_mcp(root, force):
    vs_dir = os.path.join(root, ".vscode")
    path = os.path.join(vs_dir, "mcp.json")
    if os.path.exists(path) and not force:
        return "skipped {} (already exists; use --force to overwrite)".format(path)
    os.makedirs(vs_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(MCP_JSON)
    return "wrote " + path


def _bench_one(conn, root, query, args):
    """Return metrics dict for one query, or None if no matches."""
    rows, used = retrieval.search(
        conn, query, root, limit=args.limit,
        type_filter=args.type, mode_override=args.mode)
    if not rows:
        return None
    include_tests = getattr(args, "include_tests", False)
    with_text = benchmod.recall_payload(rows)
    base_text, sources = benchmod.baseline_text(
        rows, root, args.baseline, include_tests)
    with_tok, method = benchmod.count_tokens(with_text)
    base_tok, _ = benchmod.count_tokens(base_text)
    req_base, req_with, n_files = benchmod.exploration_steps(
        rows, root, include_tests)
    # With the "files" baseline a query whose only sources are test files
    # (excluded) or non-source notes yields a 0-token baseline: that is a
    # measurement artifact, not a real comparison, so skip it.
    if args.baseline == "files" and base_tok == 0:
        return None
    return {
        "query": query, "mode": used, "results": len(rows), "method": method,
        "sources": sources, "base": base_tok, "with": with_tok,
        "saved": base_tok - with_tok,
        "pct": (base_tok - with_tok) / base_tok * 100 if base_tok else 0.0,
        "factor": base_tok / with_tok if with_tok else float("inf"),
        "req_base": req_base, "req_with": req_with, "files": n_files,
        "req_saved": req_base - req_with,
        "req_factor": req_base / req_with if req_with else float("inf"),
    }


def _read_suite(path):
    with open(path, "r", encoding="utf-8") as f:
        return [ln.strip() for ln in f
                if ln.strip() and not ln.lstrip().startswith("#")]


def _print_bench_single(m, baseline):
    print("Query    : {}".format(m["query"]))
    print("Mode     : {}   Results: {}   Tokenizer: {}".format(
        m["mode"], m["results"], m["method"]))
    print("Baseline : {} ({} source{})".format(
        baseline, len(m["sources"]), "" if len(m["sources"]) == 1 else "s"))
    for s in m["sources"][:8]:
        print("           - {}".format(s))
    if len(m["sources"]) > 8:
        print("           ... and {} more".format(len(m["sources"]) - 8))
    print("-" * 48)
    print("  without ctxmem : {:>8} tokens".format(m["base"]))
    print("  with ctxmem    : {:>8} tokens".format(m["with"]))
    print("-" * 48)
    print("  saved          : {:>8} tokens  ({:.1f}%)".format(m["saved"], m["pct"]))
    print("  reduction      : {:>7.1f}x smaller".format(m["factor"]))
    print("-" * 48)
    print("  premium requests (estimated agent round-trips)")
    print("  without ctxmem : {:>8}  (1 orient + {} file reads)".format(
        m["req_base"], m["files"]))
    print("  with ctxmem    : {:>8}  (single recall)".format(m["req_with"]))
    print("  saved          : {:>8}  ({:.1f}x fewer)".format(
        m["req_saved"], m["req_factor"]))


def _print_bench_table(metrics, baseline, method, as_markdown):
    tb = sum(m["base"] for m in metrics)
    tw = sum(m["with"] for m in metrics)
    ts = tb - tw
    tpct = ts / tb * 100 if tb else 0.0
    tfac = tb / tw if tw else float("inf")
    rb = sum(m["req_base"] for m in metrics)
    rw = sum(m["req_with"] for m in metrics)
    rfac = rb / rw if rw else float("inf")

    def clip(q, n):
        return q if len(q) <= n else q[:n - 1] + "\u2026"

    if as_markdown:
        print("\nToken benchmark (baseline: {}, tokenizer: {})\n".format(baseline, method))
        print("| Query | Tok without | Tok with | Saved | Requests w/o | Requests w/ |")
        print("|---|--:|--:|--:|--:|--:|")
        for m in metrics:
            print("| {} | {} | {} | {:.1f}% | {} | {} |".format(
                clip(m["query"], 60), m["base"], m["with"], m["pct"],
                m["req_base"], m["req_with"]))
        print("| **TOTAL** | **{}** | **{}** | **{:.1f}%** | **{}** | **{}** |".format(
            tb, tw, tpct, rb, rw))
        print("\n**{:.0f}x fewer tokens** and **{:.1f}x fewer premium requests** "
              "across {} queries.".format(tfac, rfac, len(metrics)))
        return

    print("\nToken benchmark  (baseline: {}, tokenizer: {})".format(baseline, method))
    print("=" * 82)
    print("{:<40} {:>9} {:>9} {:>6} {:>5} {:>5}".format(
        "query", "without", "with", "save%", "rq-", "rq+"))
    print("-" * 82)
    for m in metrics:
        print("{:<40} {:>9} {:>9} {:>5.1f}% {:>5} {:>5}".format(
            clip(m["query"], 40), m["base"], m["with"], m["pct"],
            m["req_base"], m["req_with"]))
    print("-" * 82)
    print("{:<40} {:>9} {:>9} {:>5.1f}% {:>5} {:>5}".format(
        "TOTAL", tb, tw, tpct, rb, rw))
    print("=" * 82)
    print("Tokens : {} -> {}  |  saved {} ({:.1f}%)  |  {:.1f}x smaller".format(
        tb, tw, ts, tpct, tfac))
    print("Premium requests : {} -> {}  |  {:.1f}x fewer agent round-trips".format(
        rb, rw, rfac))


def _write_bench_report(metrics, root, method, out_dir):
    """Write report.md + tokens.svg + requests.svg to out_dir."""
    os.makedirs(out_dir, exist_ok=True)

    def clip(q, n):
        return q if len(q) <= n else q[:n - 1] + "\u2026"

    tb = sum(m["base"] for m in metrics)
    tw = sum(m["with"] for m in metrics)
    tpct = (tb - tw) / tb * 100 if tb else 0.0
    tfac = tb / tw if tw else 0.0
    rb = sum(m["req_base"] for m in metrics)
    rw = sum(m["req_with"] for m in metrics)
    rfac = rb / rw if rw else 0.0

    tok_rows = [(clip(m["query"], 42), m["base"], m["with"]) for m in metrics]
    tok_rows.append(("TOTAL", tb, tw))
    req_rows = [(clip(m["query"], 42), m["req_base"], m["req_with"]) for m in metrics]
    req_rows.append(("TOTAL", rb, rw))

    tok_svg = os.path.join(out_dir, "bench_tokens.svg")
    req_svg = os.path.join(out_dir, "bench_requests.svg")
    benchmod.svg_grouped_bars(
        "Context tokens per question",
        "baseline: whole relevant source files (tests excluded) \u00b7 {}".format(method),
        tok_rows, tok_svg,
        label_without="without ctxmem", label_with="with ctxmem")
    benchmod.svg_grouped_bars(
        "Agent round-trips per question (\u2248 premium requests)",
        "without ctxmem: 1 orient + one read per relevant file \u00b7 with ctxmem: 1 recall",
        req_rows, req_svg,
        label_without="without ctxmem", label_with="with ctxmem")

    md = []
    md.append("# ctxmem benchmark\n")
    md.append("_Reproducible measurement of what `ctxmem` feeds an AI agent "
              "versus the naive approach._\n")
    md.append("- **Repo under test:** `{}`".format(
        os.path.basename(os.path.abspath(root)) or root))
    md.append("- **Tokenizer:** {}".format(method))
    md.append("- **Baseline (\u201cwithout ctxmem\u201d):** whole relevant source "
              "files, **test files excluded** (a real agent would not paste "
              "entire test suites to answer a question).")
    md.append("- **Queries:** {}\n".format(len(metrics)))
    md.append("## Headline\n")
    md.append("| Metric | Without ctxmem | With ctxmem | Improvement |")
    md.append("|---|--:|--:|--:|")
    md.append("| Context tokens (total) | {:,} | {:,} | **{:.1f}x smaller** ({:.1f}%) |"
              .format(tb, tw, tfac, tpct))
    md.append("| Premium requests (total) | {} | {} | **{:.1f}x fewer** |\n"
              .format(rb, rw, rfac))
    md.append("## Context tokens per question\n")
    md.append("![tokens](bench_tokens.svg)\n")
    md.append("## Premium requests per question\n")
    md.append("Premium requests are billed **per model round-trip**, not per token. "
              "Without stored memory an agent orients itself and then opens each "
              "relevant file (one round-trip each); `ctxmem` returns every snippet "
              "in a single `recall`.\n")
    md.append("![requests](bench_requests.svg)\n")
    md.append("## Full results\n")
    md.append("| Query | Tok without | Tok with | Saved | Requests w/o | Requests w/ |")
    md.append("|---|--:|--:|--:|--:|--:|")
    for m in metrics:
        md.append("| {} | {:,} | {:,} | {:.1f}% | {} | {} |".format(
            clip(m["query"], 70), m["base"], m["with"], m["pct"],
            m["req_base"], m["req_with"]))
    md.append("| **TOTAL** | **{:,}** | **{:,}** | **{:.1f}%** | **{}** | **{}** |\n"
              .format(tb, tw, tpct, rb, rw))
    md.append("## How to reproduce\n")
    md.append("```bash")
    md.append("ctxmem init && ctxmem sync            # index the repo")
    md.append("ctxmem bench --suite QUESTIONS.txt \\")
    md.append("    --baseline files --report {}".format(os.path.basename(out_dir.rstrip("/"))))
    md.append("```\n")
    report_path = os.path.join(out_dir, "report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    return report_path, tok_svg, req_svg


def cmd_bench(args):
    root = args.root
    conn = retrieval.get_conn(root)
    if conn is None:
        sys.exit("No memory here. Run 'ctxmem init' first.")

    if args.suite:
        queries = _read_suite(args.suite)
        if not queries:
            sys.exit("Suite file has no queries.")
        metrics = []
        skipped = 0
        for q in queries:
            m = _bench_one(conn, root, q, args)
            if m is None:
                skipped += 1
                continue
            metrics.append(m)
        if not metrics:
            print("No matches for any query in the suite.")
            return
        method = metrics[0]["method"]
        _print_bench_table(metrics, args.baseline, method, args.markdown)
        if skipped:
            print("({} quer{} returned no matches and were skipped)".format(
                skipped, "y" if skipped == 1 else "ies"))
        if args.report:
            report, tok_svg, req_svg = _write_bench_report(
                metrics, root, method, args.report)
            print("\nReport written:")
            print("  {}".format(report))
            print("  {}".format(tok_svg))
            print("  {}".format(req_svg))
        return

    if not args.query:
        sys.exit("Provide a query, or use --suite FILE.")
    m = _bench_one(conn, root, args.query, args)
    if m is None:
        print("No matches for: {}".format(args.query))
        return
    _print_bench_single(m, args.baseline)


def cmd_agent_init(args):
    root = args.root
    if args.agent in ("copilot", "all"):
        print(_write_copilot_instructions(root))
    if args.agent in ("codex", "all"):
        print(_write_codex_instructions(root))
    if args.mcp:
        print(_write_mcp(root, args.force))
    agent_label = {
        "copilot": "Copilot Agent",
        "codex": "Codex",
        "all": "Copilot/Codex",
    }[args.agent]
    print("Agent integration ready. Ensure 'ctxmem' is on PATH, then start a new "
          "{} chat/session so the instructions are loaded.".format(agent_label))


def cmd_update_instructions(args):
    root = args.root
    targets = [
        os.path.join(root, ".github", "copilot-instructions.md"),
        os.path.join(root, "AGENTS.md"),
    ]
    updated = [_write_managed_instructions(p, "# Project memory")
               for p in targets if os.path.exists(p)]
    if getattr(args, "mcp", False):
        mcp_path = os.path.join(root, ".vscode", "mcp.json")
        if os.path.exists(mcp_path):
            updated.append(_write_mcp(root, force=True))
    if not updated:
        print("No managed instruction files found. Run 'ctxmem agent-init' first.")
        return
    for line in updated:
        print(line)
    print("Instructions refreshed to ctxmem {}. Start a new agent chat to load them."
          .format(_ctxmem_version()))


def cmd_map(args):
    root = args.root
    _require_memory(root)
    _, jsonl_path, db_path = store.memory_paths(root)
    body, n_files, n_syms = codemap.build_map(root)
    branch, commit = gitinfo.branch(root), gitinfo.commit(root)
    content = "Codebase map (branch {}, commit {}). {} files, {} symbols.\n\n{}".format(
        branch, commit, n_files, n_syms, body)
    conn = retrieval.get_conn(root)
    prev = store.latest_memory_id(conn, "map") if conn is not None else None
    rec = {
        "id": store.new_id(),
        "ts": store.now_iso(),
        "type": "map",
        "branch": branch,
        "commit": commit,
        "path": "",
        "title": "Codebase map",
        "content": content,
        "tags": ["map", "structure"],
        "supersedes": prev or "",
    }
    store.append_jsonl(jsonl_path, rec)
    if os.path.exists(db_path):
        rec["source"] = "memory"
        store.insert_row(conn, rec)
        conn.commit()
    note = " (superseded previous map {})".format(prev) if prev else ""
    print("Saved codebase map: {} files, {} symbols [id {}]{}.".format(
        n_files, n_syms, rec["id"], note))
    print("Recall it any time with: ctxmem recall \"codebase map\" --type map")


def _add_search_args(parser, func, query_help):
    """Wire up the shared query/limit/type/mode args for recall and ask."""
    parser.add_argument("query", help=query_help)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--type", default=None,
                        choices=["note", "decision", "session", "todo", "map", "symbol"])
    parser.add_argument("--mode", default=None, choices=MODES,
                        help="Override the configured mode for this query.")
    parser.set_defaults(func=func)


def _add_agent_parsers(sub):
    ag = sub.add_parser(
        "agent-init",
        help="Wire up Copilot/Codex agents (instructions files, optional MCP).")
    ag.add_argument("--agent", default="copilot", choices=["copilot", "codex", "all"],
                    help="Instruction target to write: copilot, codex, or all "
                         "(default: copilot).")
    ag.add_argument("--mcp", action="store_true",
                    help="Also write .vscode/mcp.json for MCP-capable agents.")
    ag.add_argument("--force", action="store_true",
                    help="Overwrite .vscode/mcp.json if it already exists.")
    ag.set_defaults(func=cmd_agent_init)

    ui = sub.add_parser(
        "update-instructions",
        help="Refresh the managed agent instruction block(s) after upgrading ctxmem.")
    ui.add_argument("--mcp", action="store_true",
                    help="Also overwrite .vscode/mcp.json if it already exists.")
    ui.set_defaults(func=cmd_update_instructions)


def build_parser():
    p = argparse.ArgumentParser(prog="ctxmem", description="Git-native project memory.")
    p.add_argument("--root", default=".", help="Project root (default: cwd).")
    sub = p.add_subparsers(dest="cmd", required=True)

    ini = sub.add_parser("init", help="Initialize memory in this repo.")
    ini.add_argument("--mode", default="keyword", choices=MODES,
                     help="Search mode (default: keyword; semantic/hybrid are beta).")
    ini.set_defaults(func=cmd_init)

    md = sub.add_parser("mode", help="Show or change the search mode.")
    md.add_argument("value", nargs="?", choices=MODES,
                    help="New mode (omit to show; semantic/hybrid are beta).")
    md.set_defaults(func=cmd_mode)

    r = sub.add_parser("remember", help="Store a decision/note/session.")
    r.add_argument("content", help="What to remember.")
    r.add_argument("--type", default="note",
                   choices=["note", "decision", "session", "todo"], help="Kind of memory.")
    r.add_argument("--title", default="", help="Short title.")
    r.add_argument("--path", default="", help="Related file path.")
    r.add_argument("--tags", default="", help="Comma-separated tags.")
    r.add_argument("--supersedes", default="", metavar="MEM_ID",
                   help="Id of a previous memory this record corrects/replaces.")
    r.set_defaults(func=cmd_remember)

    rc = sub.add_parser("recall", help="Search the memory.")
    _add_search_args(rc, cmd_recall, "Search text.")

    ak = sub.add_parser(
        "ask", help="Recall + a HIT/WEAK/MISS verdict on whether memory knows.")
    _add_search_args(ak, cmd_ask, "The question to check against memory.")

    s = sub.add_parser("sync", help="Rebuild the index from jsonl + code.")
    s.set_defaults(func=cmd_sync)

    mp = sub.add_parser(
        "map", help="Scan the codebase and save a structure + import map into memory.")
    mp.set_defaults(func=cmd_map)

    lg = sub.add_parser("log", help="Show recent memories.")
    lg.add_argument("--limit", type=int, default=10)
    lg.set_defaults(func=cmd_log)

    st = sub.add_parser("status", help="Show what is indexed.")
    st.set_defaults(func=cmd_status)

    dr = sub.add_parser(
        "doctor",
        help="Check the semantic (Ollama) backend end to end, with fix hints.")
    dr.set_defaults(func=cmd_doctor)

    hk = sub.add_parser("hook", help="Install/uninstall the git post-commit hook.")
    hk.add_argument("action", choices=["install", "uninstall"])
    hk.set_defaults(func=cmd_hook)

    _add_agent_parsers(sub)

    bn = sub.add_parser(
        "bench",
        help="Measure token savings: recall snippets vs feeding whole files/repo.")
    bn.add_argument("query", nargs="?", default=None,
                    help="Search text (omit when using --suite).")
    bn.add_argument("--suite", default=None,
                    help="File with one query per line ('#' comments); prints a table.")
    bn.add_argument("--markdown", action="store_true",
                    help="Emit the suite table as Markdown.")
    bn.add_argument("--report", default=None, metavar="DIR",
                    help="Write report.md + SVG charts (tokens & premium requests) to DIR.")
    bn.add_argument("--include-tests", action="store_true",
                    help="Count test files in the baseline (excluded by default).")
    bn.add_argument("--limit", type=int, default=8,
                    help="How many recall results to inject (default: 8).")
    bn.add_argument("--type", default=None,
                    choices=["note", "decision", "session", "todo", "symbol"])
    bn.add_argument("--mode", default=None, choices=MODES,
                    help="Override the configured search mode.")
    bn.add_argument("--baseline", default="files", choices=["files", "memory", "repo"],
                    help="What 'without ctxmem' means: whole referenced files "
                         "(default), whole memory, or whole repo.")
    bn.set_defaults(func=cmd_bench)
    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
