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
ctxmem remember --type decision --title "Corrected title" \
  --supersedes <old-memory-id> "What is now true and why it changed"
```

Each `remember` prints the new record's `id`; use it as the `--supersedes`
target later. After changing code, run `ctxmem sync` to rebuild the index.

If your agent supports the MCP protocol instead of running shell commands, use
the MCP tools `recall(...)` and `remember(..., supersedes="<id>")` the same way.

_Managed by ctxmem 1.4.1 — run `ctxmem update-instructions` after upgrading._
<!-- ctxmem:end -->
