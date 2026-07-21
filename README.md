<div align="center">

<p align="center">
  <img src="assets/banner.png" alt="ctxmem banner" width="100%">
</p>

# ctxmem

**Git-native, shareable project memory for AI coding agents — fully local, no cloud.**

[![Test](https://github.com/DoppiaG93/ctxmem/actions/workflows/test.yml/badge.svg)](https://github.com/DoppiaG93/ctxmem/actions/workflows/test.yml)
[![Lint](https://github.com/DoppiaG93/ctxmem/actions/workflows/lint.yml/badge.svg)](https://github.com/DoppiaG93/ctxmem/actions/workflows/lint.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![Dependencies](https://img.shields.io/badge/core%20deps-zero-brightgreen.svg)](pyproject.toml)
[![MCP](https://img.shields.io/badge/MCP-ready-8A2BE2.svg)](https://modelcontextprotocol.io)

</div>

---

`ctxmem` gives your project a permanent, searchable memory that lives **inside the
repo**. AI agents (and you) store decisions and recall relevant context on demand,
so nothing is forgotten when a chat exceeds the model's context window.

- 🧠 **Remembers** — decisions, notes, sessions + your code, in a searchable index.
- 🔎 **Self-checking** — `ctxmem ask` tells the agent whether memory already knows
  (`HIT` / `WEAK` / `MISS`) *before* it answers.
- ♻️ **Self-correcting** — supersede an outdated decision (`--supersedes`); recall
  demotes and flags it (`⚠ SUPERSEDED` / `⚠ STALE`).
- 🤝 **Shareable** — the memory is a text file committed to git. Commit, your
  colleague pulls, they get *your exact context*. Branch-aware for free.
- 📦 **Works as a git package** — `pip install git+https://…`, zero required deps.
- 🔒 **Fully local** — SQLite files in your repo. No cloud, no API keys, no servers.
- 🔍 **Search modes** — `keyword` (built-in) plus `semantic` / `hybrid` (🧪 **beta**,
  local embeddings).

<p align="center">
  <img src="assets/demo.svg" alt="ctxmem demo: init, remember, sync, recall" width="90%">
</p>

> **How it works, in one line:** a committed, human-readable `memory.jsonl` is the
> source of truth; a local, gitignored SQLite index makes it (and your code)
> instantly searchable. For the full design, see **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

---

## Install

```bash
pip install "git+https://github.com/DoppiaG93/ctxmem.git"   # as a git package
# or, from a clone:  pip install -e .

# optional extras
pip install "ctxmem[mcp]"        # AI-agent server (MCP)
pip install "ctxmem[semantic]"   # 🧪 beta semantic search (needs Ollama too)
pip install "ctxmem[all]"        # everything
```

Requires **Python 3.8+** with FTS5 (bundled in virtually every `sqlite3` build).
The base install has **zero third-party dependencies**.

## Quick start

```bash
cd your-project

ctxmem init                                   # creates .ctxmem/
ctxmem hook install                           # auto-sync the index on every commit
ctxmem remember --type decision \
  --title "Auth via JWT" --tags auth,security \
  "We chose stateless JWT over server sessions for horizontal scaling."

ctxmem sync                                   # index memory + your code
ctxmem ask "how do we handle authentication"      # verdict: HIT / WEAK / MISS
ctxmem recall "how do we handle authentication"   # ask in plain language
ctxmem recall "cart" --type symbol            # search only code symbols
```

Then commit the memory so it's shared:

```bash
git add .ctxmem/memory.jsonl .ctxmem/config.json
git commit -m "chore: seed project memory"
```

Your colleague just `git pull`s and runs `ctxmem recall` — the index rebuilds
itself from `memory.jsonl`. For the full onboarding story (agent wiring, handing
memory to a teammate), see **[docs/GUIDE.md](docs/GUIDE.md)**.

## Commands

| Command | What it does |
|---------|--------------|
| `ctxmem init [--mode M]` | Create `.ctxmem/` and pick a search mode. |
| `ctxmem remember "text" [--type --title --tags --path --supersedes ID]` | Store a memory (→ `memory.jsonl`); prints the new record's `id`. Types: `note`, `decision`, `session`, `todo`. `--supersedes ID` corrects/replaces an earlier memory. |
| `ctxmem recall "query" [--limit --type --mode]` | Search memory + code. Superseded records are demoted + flagged `⚠ SUPERSEDED`; memories pointing at a missing file are flagged `⚠ STALE`. |
| `ctxmem ask "question" [--limit --type --mode]` | Recall **plus a verdict**: `HIT` / `WEAK` / `MISS`. Use it to check memory *before* answering. |
| `ctxmem sync` | Rebuild `index.db` from `memory.jsonl` + code (+ embeddings if enabled). |
| `ctxmem map` | Save a **structure + Python import map** into memory (`--type map`). Great first step so agents know the layout. |
| `ctxmem mode [M]` | Show, or switch to, `keyword` / `semantic` 🧪 / `hybrid` 🧪. |
| `ctxmem log [--limit]` | List recent memories. |
| `ctxmem status` | Branch/commit, mode, and counts of indexed items. |
| `ctxmem doctor` | Check the semantic (Ollama) backend end to end, with fix-it hints. |
| `ctxmem hook install`/`uninstall` | Add/remove a git post-commit auto-sync hook. |
| `ctxmem agent-init [--agent copilot\|codex\|all] [--mcp] [--force]` | Wire up agents: write the memory protocol into instruction files (+ `.vscode/mcp.json` with `--mcp`). |
| `ctxmem update-instructions [--mcp]` | Refresh the managed instruction block(s) after upgrading ctxmem. |
| `ctxmem bench "query" [--baseline files\|memory\|repo]` | Measure **token** and **premium-request** savings. Add `--suite FILE --report DIR` for a full report with charts. |
| `ctxmem --root PATH …` | Run against a repo other than the current directory. |

## Use it from an AI agent

Wire an agent (Codex, GitHub Copilot) to the memory in one command:

```bash
ctxmem agent-init --agent all        # write the memory protocol into AGENTS.md + copilot-instructions.md
ctxmem agent-init --agent all --mcp  # also drop a .vscode/mcp.json (MCP server)
```

This injects a **Project Memory Protocol** that tells the agent to `recall` before
a task, `remember` decisions, and `sync` after changing code — so the memory grows
by itself. Full details (CLI vs MCP, requirements, tips) in
**[docs/GUIDE.md → Use it from an AI agent](docs/GUIDE.md#use-it-from-an-ai-agent)**.

## Semantic search (Ollama, beta)

Keyword mode is the stable, zero-setup default. Optional 🧪 **beta** semantic and
hybrid modes match by *meaning* using a fully-local embedding model:

```bash
pip install "ctxmem[semantic]"
# Option A: install Ollama on the host, then:
ollama pull nomic-embed-text
ctxmem mode semantic
ctxmem doctor                        # verify the whole chain end to end

# Option B: run Ollama in an isolated Lima VM:
cd ollama && task enable             # brings the VM up + switches to semantic
```

If the backend isn't available, ctxmem **automatically falls back to keyword**.
Setup options, the Lima VM, and `ctxmem doctor` output are documented in
**[docs/GUIDE.md → Semantic backend](docs/GUIDE.md#semantic-backend-with-ollama-beta)**.

## Why it saves tokens

Instead of pasting whole files into the model, you inject only the relevant
`recall` snippets. Measured on the Django source tree:

| Metric | Without ctxmem | With ctxmem | Improvement |
|---|--:|--:|--:|
| Context tokens (13 questions) | 272,354 | 14,028 | **19.4× smaller** |
| Premium requests (round-trips) | 49 | 13 | **3.8× fewer** |

Full methodology and reproducible steps:
**[docs/ARCHITECTURE.md → Benchmark](docs/ARCHITECTURE.md#7-benchmark--how-it-was-tested)**.

## Documentation

- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — the problem, the data model,
  the retrieval pipeline, project structure, search-mode internals, and the benchmark.
- **[docs/GUIDE.md](docs/GUIDE.md)** — full walkthrough, team sharing, the git hook,
  AI-agent integration (CLI + MCP), and the semantic/Ollama backend.

## FAQ

**Is my data sent anywhere?** No. Everything is local: SQLite files in your repo
and, if you enable the beta semantic mode, a local Ollama.

**Do I have to use embeddings?** No. `keyword` mode needs nothing and is the
default. Semantic is opt-in and still in beta.

**Should I commit `index.db`?** No — it's derived and gitignored. Commit
`memory.jsonl` and `config.json`.

**What if a teammate doesn't have Ollama?** ctxmem falls back to keyword
automatically; the shared memory still works.

**Does it scale to a big repo?** Yes. The keyword index is fine for large repos,
and semantic mode is incremental — embeddings are cached by content hash
(`.ctxmem/emb_cache.db`), so a `sync` only re-embeds new or changed text.

**Is MCP proprietary?** No. MCP is an open protocol with MIT-licensed SDKs; the
server runs locally and reads only your repo.

## Contributing

**Contributions are currently invite-only.** The project is developed by a small
set of invited collaborators, so unsolicited pull requests are not accepted right
now — but **bug reports and feature requests are always welcome** via
[GitHub issues](https://github.com/DoppiaG93/ctxmem/issues). To contribute code,
reach out to [@DoppiaG93](https://github.com/DoppiaG93) to be added as a collaborator.

Invited collaborators follow the **Git Flow** branching model; see the
**[Contributing guide](CONTRIBUTING.md)** for branch naming, commit conventions,
and the release process. Please also review our
[Code of Conduct](CODE_OF_CONDUCT.md). To report a security issue, follow the
[Security Policy](SECURITY.md).

## License

Released under the [MIT License](LICENSE).
