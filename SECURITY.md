# Security Policy

## Supported versions

`ctxmem` is currently in the `0.x` series. Security fixes are applied to the
latest released version on the `main` branch.

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅        |

## Reporting a vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, report them privately using GitHub's
[private vulnerability reporting](https://github.com/DoppiaG93/ctxmem/security/advisories/new):

1. Go to the repository's **Security** tab.
2. Click **Report a vulnerability**.
3. Describe the issue, including steps to reproduce and the potential impact.

You can expect an initial response within a few days. Once the report is
confirmed, a fix will be prepared and released, and you will be credited in the
release notes unless you prefer to remain anonymous.

## Scope

`ctxmem` runs fully locally: it stores memory as files inside your repository
(`.ctxmem/memory.jsonl`) and does not send data to any external service. The
optional semantic backend (beta) talks only to a local Ollama instance you run
yourself. Keep this in mind when assessing potential impact.
