# Project memory

<!-- ctxmem:begin (managed by `ctxmem agent-init`) -->
This repo has a `ctxmem` memory. Before starting a task, run the
`ctxmem recall` command in the terminal to load relevant decisions and code:

```bash
ctxmem recall "<short description of the task or question>"
```

When you make or confirm an important decision, run `ctxmem remember` so it is
saved for future sessions and teammates:

```bash
ctxmem remember --type decision --title "Short title" "Detailed decision text"
```

After changing code, run `ctxmem sync` to rebuild the index.

If your agent supports the MCP protocol instead of running shell commands, it can
call the MCP tools `recall(...)` and `remember(...)` as an alternative.
<!-- ctxmem:end -->
