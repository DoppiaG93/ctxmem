# Project memory

<!-- ctxmem:begin (managed by `ctxmem agent-init`) -->
This repo has a `ctxmem` memory: a shared, git-committed record of
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

When assembling context for implementation or a handoff, use a bounded payload:

```bash
ctxmem context "<task or question>" --budget 2000
```

Choose the budget to fit the task and available context; 2000 is an example,
not a mandatory limit. This complements the initial `ask` verdict. Avoid loading
both outputs again when the first already provides enough context.
`context` prioritizes active decisions, excludes superseded records, and retains
sources and STALE warnings. Oversized blocks are skipped, not truncated; empty
output does not prove the memory has no answer. Refine the query, increase the
budget, or use `recall` to inspect omitted context when needed.
Only stdout is the payload; stderr reports the count and method. The budget
covers payload text only (cl100k_base tokens when available, otherwise conservative
UTF-8 bytes), not surrounding prompts or arbitrary model tokenizers.

**2. Reconcile — decide who is right.**
If what the memory says conflicts with your own context or with the current
code, do not silently pick one. Verify against the actual code in the repo:

- If the **code/reality** proves the memory is outdated, correct the memory
  (step 3) and tell the user what changed.
- If the **memory** is right and your context was stale, trust the memory.

Records shown with `⚠ SUPERSEDED` are already outdated — use the newer one.
Records shown with `⚠ STALE` or `WARNING: STALE` reference files that changed,
are missing, or cannot be verified. Check the code and supersede the memory if
it is wrong; a changed file alone does not prove the decision is obsolete.

**3. Remember — persist every decision and correction.**
When you make or confirm an important decision, save it:

```bash
ctxmem remember --type decision --title "Short title" "Detailed decision text"
```

When you find that an existing memory is wrong or obsolete, replace it instead
of just adding a new one (this demotes and flags the old record in recall):

```bash
ctxmem remember --type decision --title "Corrected title" \
  --supersedes <old-memory-id> "What is now true and why it changed"
```

Each `remember` prints the new record's `id`; use it as the `--supersedes`
target later. After changing code, run `ctxmem sync` to rebuild the index.

If your agent supports the MCP protocol instead of running shell commands, use
the MCP tools `ask(...)`, `recall(...)`, and `remember(..., supersedes="<id>")`
the same way. For budgeted context use `context(query="<task>", budget=2000)`;
consume its `text` field as the payload and inspect the separate selection/count
metadata. The budget excludes the MCP envelope and metadata.

_Managed by ctxmem 2.0.1 — run `ctxmem update-instructions` after upgrading._
<!-- ctxmem:end -->
