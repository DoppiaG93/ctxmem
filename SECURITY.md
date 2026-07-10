# Security Policy

## Supported versions

Security fixes are applied to the latest `1.3.x` release on `main`. Older
versions are not maintained; please upgrade to the current release before
reporting an issue.

| Version | Supported |
|---------|-----------|
| 1.3.x   | ✅        |
| < 1.3   | ❌        |

## Reporting a vulnerability

**Please do not report security vulnerabilities through public GitHub issues,
discussions, or pull requests.**

Report them privately using GitHub's
[private vulnerability reporting](https://github.com/DoppiaG93/ctxmem/security/advisories/new):

1. Open the repository's **Security** tab.
2. Click **Report a vulnerability**.
3. Include the affected version, reproduction steps, and the impact you observed.

You can expect an initial acknowledgement within a few days. Once a report is
confirmed, a fix is prepared on a private branch, released as a patch, and you
are credited in the release notes unless you ask to remain anonymous.

## Threat model

`ctxmem` runs entirely on your machine. Understanding what it touches helps scope
reports:

- **Local memory files.** Memory is stored as plain-text
  [`.ctxmem/memory.jsonl`](.ctxmem/memory.jsonl) plus a derived, git-ignored
  `index.db`. Anyone with read access to the repository can read every stored
  memory. **Never store secrets, credentials, tokens, or personal data in a
  memory** — the JSONL is committed to git and shared with the team.
- **Git integration.** `ctxmem` shells out to `git` to read commit metadata and
  may install a local hook. Treat memory content coming from an untrusted
  repository as untrusted input.
- **MCP server.** `ctxmem mcp` exposes `recall`/`remember` over stdio to a local
  agent only. It reads and writes the current repository's `.ctxmem/` directory
  and does not open any network socket.
- **Semantic backend (beta).** The optional embeddings path talks only to a
  local Ollama endpoint you configure and run yourself, and can load the
  `sqlite-vec` extension into SQLite. No embeddings or memory content leave your
  machine.

## In scope

- Path traversal or writes outside the intended `.ctxmem/` directory.
- Code execution triggered by loading a crafted `memory.jsonl`, `config.json`,
  or repository state.
- Injection into the git hook, CLI arguments, or MCP request handling.
- Loading of unexpected native code via the `sqlite-vec` / Ollama integration.

## Out of scope

- Reading memory you already have filesystem/repository access to (this is by
  design — memory is meant to be shared with collaborators).
- Secrets a user intentionally placed inside a memory (see the warning above).
- Vulnerabilities in Ollama, SQLite, or other third-party software `ctxmem`
  integrates with — report those to their respective projects.
