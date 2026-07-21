# ctxmem — Usage guide

The long-form manual: a full walkthrough, sharing across a team, the git hook,
wiring an AI agent, and enabling the semantic (Ollama) backend.

← Back to the [README](../README.md) · See also the [Architecture](ARCHITECTURE.md).

---

## Full walkthrough (install, agent, colleague)

A complete, realistic story: **you have your own package/codebase, you add ctxmem,
the AI agent starts remembering, and you hand the memory to a colleague.**

First, the key question up front:

> **Do I type commands by hand, or is it automatic?**
> Both — there are three levels, and you choose how much to automate:
>
> | What | Who does it | How |
> |------|-------------|-----|
> | Index the **code** | automatic | the git hook runs `ctxmem sync` on every commit |
> | Record a **decision** | you *or* the agent | you run `ctxmem remember`, **or** the AI calls the `remember` MCP tool for you |
> | **Recall** context | you *or* the agent | you run `ctxmem recall`, **or** the AI calls the `recall` MCP tool |
>
> The code index maintains itself. Decisions are written either by you (one
> command) or automatically by the agent once you wire up an instruction file
> and, optionally, MCP tools (Step 4 below).

### Step 1 — Add ctxmem to your codebase (once)

```bash
cd ~/code/my-awesome-package        # your existing repo

pip install "git+https://github.com/DoppiaG93/ctxmem.git"   # or: pip install -e ../ctxmem

ctxmem init                          # creates .ctxmem/ (keyword mode by default)
ctxmem hook install                  # auto-rebuild the index after every commit
ctxmem sync                          # first index of your existing code
```

What just happened:
- `.ctxmem/memory.jsonl` (empty for now) + `.ctxmem/config.json` were created.
- A `post-commit` hook now keeps the code index up to date by itself.
- Your code is already searchable: try `ctxmem recall "database connection"`.

### Step 2 — Seed a few decisions (you, one line each)

Write down the things you'd want a new teammate (or a fresh AI session) to know:

```bash
ctxmem remember --type decision --title "HTTP client" \
  "We use httpx (async) everywhere; do not add requests."

ctxmem remember --type decision --title "DB" --tags db \
  "Postgres via SQLAlchemy 2.0; migrations with Alembic."

ctxmem remember --type note --title "Gotcha" \
  "The worker must run with TZ=UTC or scheduling breaks."
```

Check them: `ctxmem log`.

### Step 3 — Commit the memory so it can be shared

```bash
git add .ctxmem/memory.jsonl .ctxmem/config.json
git commit -m "chore: seed project memory"
git push
```

Only the **source of truth** (`memory.jsonl`) and **config** are committed. The
`index.db` stays local (gitignored) and is rebuilt on demand.

### Step 4 — Let the AI agent remember on its own (optional but powerful)

So far you typed the commands. To make the **agent** do it automatically, create
the right instruction file for your tool:

```bash
ctxmem agent-init --agent codex      # writes/updates local AGENTS.md
ctxmem agent-init --agent copilot    # writes/updates .github/copilot-instructions.md
ctxmem agent-init --agent all        # writes both
ctxmem agent-init --agent all --mcp  # also writes .vscode/mcp.json
```

Codex reads `AGENTS.md` (often kept local and gitignored). GitHub Copilot reads
`.github/copilot-instructions.md`. The generated section is wrapped in ctxmem
markers, so re-running `agent-init` updates only that section.

After upgrading ctxmem (`pip install -U ctxmem`), run `ctxmem update-instructions`
to refresh the managed block in whichever of those files already exist — the block
carries a version footer so you can tell when it is stale.

The injected **Project Memory Protocol** tells the agent to `recall` before a
task, `remember` when it makes a decision, and `sync` after changing code. For
the full protocol text, the manual wiring, and MCP setup, see
[Use it from an AI agent](#use-it-from-an-ai-agent).

Now, in a normal chat, the agent recalls past decisions at the start and records
new ones as it goes — the memory grows by itself. You can still use the CLI
anytime; the agent and you write to the same memory.

### Step 5 — Your colleague gets the exact same context

```bash
git clone https://github.com/DoppiaG93/my-awesome-package && cd my-awesome-package
pip install "git+https://github.com/DoppiaG93/ctxmem.git"   # or your normal env setup

ctxmem hook install     # one-time: git doesn't share hooks, so each dev installs it
ctxmem recall "which HTTP client do we use"
#   [decision] HTTP client
#   We use httpx (async) everywhere; do not add requests.
```

They never ran `remember` — they simply pulled your `memory.jsonl`. The first
`recall` rebuilt their local `index.db` automatically. If they use Codex, they
can run `ctxmem agent-init --agent codex` to create their local `AGENTS.md`; if
the repo includes `.github/copilot-instructions.md` or `.vscode/mcp.json`,
those agent integrations travel with the repo.

> **Two one-time, per-machine steps** that git can't do for you: `pip install`
> ctxmem, and `ctxmem hook install` (git hooks live in `.git/`, which isn't
> pushed). Everything else travels in the repo.

### Recap: what's manual vs automatic

- **Automatic:** code indexing (git hook), index rebuild on `recall`, and — once
  Step 4 is set up — the agent recalling and recording decisions.
- **Manual (optional):** writing decisions yourself with `ctxmem remember`, and
  the two per-machine setup commands above.

## Measuring token savings (`bench`)

`ctxmem bench` quantifies the whole point of the tool: instead of pasting whole
files (or the whole repo) into the model, you inject only the relevant `recall`
snippets. It reports **two** things — the context **tokens** you feed the model
and the number of **premium requests** (agent round-trips) the answer costs.

```bash
ctxmem bench "how is a marker structured"                 # snippets vs whole referenced files
ctxmem bench "how is a marker structured" --baseline repo # snippets vs the entire codebase
ctxmem bench "versioning" --baseline memory --type note   # snippets vs the whole memory.jsonl
```

```
  without ctxmem :    21306 tokens
  with ctxmem    :     1526 tokens
  saved          :    19780 tokens  (92.8%)
  reduction      :     14.0x smaller
  premium requests (estimated agent round-trips)
  without ctxmem :        6  (1 orient + 5 file reads)
  with ctxmem    :        1  (single recall)
  saved          :        5  (6.0x fewer)
```

Baselines: `files` (default — full text of the files behind the results),
`memory` (the whole `memory.jsonl`), `repo` (all indexed code + memory). Test
files are **excluded** from the baseline by default (`--include-tests` to keep
them), because a real agent would not paste whole test suites to answer a
question. Token counts use **tiktoken** when installed
(`pip install "ctxmem[bench]"`), otherwise a portable ~chars/4 estimate (the
label shows which was used).

Run a whole suite of questions and generate a shareable report with charts:

```bash
ctxmem bench --suite questions.txt --baseline files --report bench-out
# writes bench-out/report.md, bench-out/bench_tokens.svg, bench-out/bench_requests.svg
```

For the full methodology and reproducible numbers on the Django codebase, see the
[Benchmark section of the Architecture doc](ARCHITECTURE.md#7-benchmark--how-it-was-tested).

## Sharing with your team

The memory travels through git like code:

```bash
# you
ctxmem remember --type decision "Payments go through Stripe, not PayPal."
git add .ctxmem/memory.jsonl && git commit -m "memory: payments" && git push

# your colleague
git pull
ctxmem recall "payments"     # index rebuilds from memory.jsonl → same context
```

Because `memory.jsonl` is a normal file:

- **Branch-aware:** each branch carries its own decisions; switch branch and
  `recall` reflects it.
- **Merge-friendly:** append-only lines merge cleanly; conflicts are rare and
  readable.
- **No server:** nothing to host, nothing to sync — git *is* the transport.

## Auto-sync with a git hook

Keep the index fresh automatically:

```bash
ctxmem hook install      # writes .git/hooks/post-commit
ctxmem hook uninstall
```

After every `git commit`, the index rebuilds so `recall` always reflects the
latest code and decisions. The hook uses your exact Python interpreter, so it
works from inside a virtualenv.

## Use it from an AI agent

There are two ways to connect an agent (e.g. Codex or GitHub Copilot) to the
memory. They are independent — use whichever your setup allows.

### Option A — instructions + CLI (recommended, no MCP needed)

The agent already runs terminal commands, so it can drive the `ctxmem` CLI
directly. You just tell it *when* to `recall` and `remember` via an instructions
file. This works even when MCP is unavailable or disabled by policy.

Set it up in one command from your repo root:

```bash
ctxmem agent-init --agent codex      # writes/updates local AGENTS.md
ctxmem agent-init --agent copilot    # writes/updates .github/copilot-instructions.md
ctxmem agent-init --agent all        # writes both instruction files
ctxmem agent-init --agent all --mcp  # also drop a .vscode/mcp.json (for Option B)
```

This inserts a **Project Memory Protocol** between managed markers
(`<!-- ctxmem:begin -->` … `<!-- ctxmem:end -->`). It is **idempotent**: if the
file already exists it appends the section; re-running updates that section in
place without duplicating it or touching your other instructions.

Codex uses `AGENTS.md` (often kept local and gitignored). GitHub Copilot uses
`.github/copilot-instructions.md`. The default remains `--agent copilot` for
backward compatibility.

The protocol tells the agent to:

1. run `ctxmem ask "<the request>"` **before answering**, to check whether the
   memory already knows (verdict `HIT` / `WEAK` / `MISS`) and load context;
2. **reconcile** conflicts — if the current code contradicts a memory (e.g. a
   record flagged `⚠ STALE` or `⚠ SUPERSEDED`), trust the code and correct the
   memory with `ctxmem remember --supersedes <id> …`;
3. run `ctxmem remember …` when it makes or confirms an important decision;
4. run `ctxmem sync` after changing code.

Requirements & tips:

- **`ctxmem` must be on PATH** in the terminal the agent uses. If you installed it
  in a venv, expose it globally, e.g. `ln -s "$(command -v ctxmem)" ~/.local/bin/`.
- Use the agent in a mode that can run terminal commands (Codex, or VS Code
  Copilot **Agent** mode). Choose **"Always allow"** for `ctxmem` when your
  client offers command allow-listing.
- Start a **new chat** after `agent-init` so the updated instructions load.
- **Reality check:** LLMs are probabilistic — a strong, imperative protocol makes
  proactive saving *reliable*, not *guaranteed*. For 100% determinism, save
  explicitly (ask the agent, or run `ctxmem remember` yourself) or via the git hook.

### Option B — MCP server

`ctxmem` also ships an [MCP](https://modelcontextprotocol.io) server so agents can
call the memory as native tools. MCP is an **open standard** (MIT-licensed SDKs);
the server runs **locally** and reads only your repo.

```bash
pip install "ctxmem[mcp]"
```

Register it (VS Code `.vscode/mcp.json`, also created by `agent-init --mcp`):

```json
{
  "servers": {
    "ctxmem": {
      "command": "ctxmem-mcp",
      "env": { "CTXMEM_ROOT": "${workspaceFolder}" }
    }
  }
}
```

> If `ctxmem-mcp` isn't on the global PATH (e.g. it lives in a venv), use the
> absolute path to the binary as `command`.

Tools exposed to the agent:

- `recall(query, limit, type, mode)` — pull relevant context before a task.
- `ask(query, limit, type, mode)` — recall **plus** a `HIT` / `WEAK` / `MISS` verdict.
- `remember(content, type, title, tags, supersedes)` — record a decision (or
  correct an earlier one via `supersedes`).
- `memory_status()` — mode, branch/commit, index counts.

**The pattern (both options):** the agent calls `recall` at the start of a task
(injecting only the relevant snippets, staying well under the token limit) and
`remember` at the end — so the project's memory grows and persists across sessions.

## Semantic backend with Ollama (beta)

> ⚠️ **Beta / experimental.** Semantic search works but is under active testing.
> Keyword mode remains the stable default. Expect the semantic setup and defaults
> to evolve in a future release.

Semantic search needs two open-source, fully-local pieces:

- **[Ollama](https://ollama.com)** runs an embedding model on your machine
  (offline, no API key). We use the small `nomic-embed-text` model.
- **[sqlite-vec](https://github.com/asg017/sqlite-vec)** stores the vectors and
  does nearest-neighbor search inside SQLite (a single loadable extension, no
  server).

### Option A — install Ollama on the host

```bash
pip install "ctxmem[semantic]"
# install Ollama from https://ollama.com, then:
ollama pull nomic-embed-text
ctxmem mode semantic
```

### Option B — run Ollama in an isolated Lima VM

Keeps Ollama off the host. Guest port `11434` is forwarded to the host, so ctxmem
(default `ollama_url = http://localhost:11434`) needs no extra config.

```bash
cd ollama
task requirements # check Lima is installed (prints install help if not)
task enable       # ONE command: bring the VM up + switch ctxmem to semantic
# or step by step:
task start        # create VM, install Ollama, pull nomic-embed-text
task status       # verify the endpoint responds
task demo         # ctxmem mode semantic + a real query
task stop         # or: task delete   (fully reversible)
```

`task start` requires Lima (`limactl`). If it's missing, `task requirements`
(run automatically by `start`) prints how to install it — or how to skip the VM
and use Option A instead. `ollama/lima.yaml` provisions Ubuntu 24.04, installs
Ollama as a systemd service, pulls the model, and includes a readiness probe.

> **Turn semantic mode on (one command):** `ctxmem mode semantic`. That's the
> only switch ctxmem needs — it just changes the search mode in `config.json`.
> `task enable` is the convenience wrapper that also makes sure the VM/backend is
> up first and then runs `ctxmem doctor`.

### Check it works: `ctxmem doctor`

Whichever option you pick, verify the whole chain with one command:

```bash
ctxmem doctor
```

It checks sqlite-vec, the Ollama endpoint, that the embedding model is pulled,
and does a real embedding call — printing an actionable hint for anything that
fails, and exiting non-zero if the backend isn't fully ready:

```text
[OK  ] sqlite3 has FTS5 (keyword search)
[OK  ] sqlite-vec installed (vector search)
[OK  ] Ollama reachable at http://localhost:11434
[OK  ] embedding model 'nomic-embed-text' pulled
[OK  ] live embedding call (768 dims)

Semantic backend READY. Turn it on with 'ctxmem mode semantic'.
```
