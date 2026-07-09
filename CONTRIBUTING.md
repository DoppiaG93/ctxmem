# 🤝 Contributing to ctxmem

Thanks for your interest in improving **ctxmem**! This guide explains how the
project is organized and how to propose changes.

---

## 🛠️ Development setup

```bash
git clone https://github.com/DoppiaG93/ctxmem.git
cd ctxmem

python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate

pip install -e ".[all]"              # editable install with all optional extras
ctxmem --help                        # verify the CLI works
```

Requirements: **Python 3.8+**. The core has zero third-party dependencies; the
extras (`mcp`, `semantic`, `bench`) are optional.

> There is no automated test suite yet. Validate your changes by running the CLI
> end to end (`init` → `remember` → `sync` → `recall`) and describe how you
> tested them in the pull request.

---

## 🌳 Branching model (Git Flow)

Two long-lived branches:

- **`main`** — released code only. Never commit directly; it changes only through
  a reviewed pull request.
- **`develop`** — integration branch where finished work accumulates for the next
  release.

Short-lived branches, deleted after merge:

| Prefix | Branch from | Merge into | Use for |
|--------|-------------|------------|---------|
| `feature/` | `develop` | `develop` | New features / enhancements |
| `bugfix/` | `develop` | `develop` | Non-urgent fixes for the next release |
| `hotfix/` | `main` | `main` **and** `develop` | Urgent fixes to the released version |

Name branches in lowercase kebab-case, e.g. `feature/recall-json-output`,
`bugfix/empty-query-crash`, `hotfix/index-corruption`.

---

## 🔁 Workflow

```bash
git switch develop
git pull origin develop

git switch -c feature/my-thing        # or bugfix/my-thing
# ... make changes, commit ...
git push -u origin feature/my-thing
```

Then open a **Pull Request** targeting **`develop`**. Once merged, the branch is
deleted and your change is queued for the next release.

For a **hotfix**, branch from `main`, then merge the fix into both `main` (ship a
patch release) and `develop` (so it isn't lost).

---

## ✍️ Commits & pull requests

- Write clear commit messages; [Conventional Commits](https://www.conventionalcommits.org/)
  (`feat:`, `fix:`, `docs:`, `chore:` …) are encouraged but not required.
- In the PR description, explain **what** changed, **why**, and **how** you tested it.
- Feel free to add **labels** and a **milestone** if you find them helpful — they
  are optional and not required to contribute.

---

## 🚀 Release process

Releases flow from `develop` to `main`:

1. Make sure `develop` has everything intended for the release.
2. Bump the version in [`pyproject.toml`](pyproject.toml) and
   `src/ctxmem/__init__.py`.
3. Open a PR **`develop` → `main`** (e.g. `Release v0.2.0`).
4. After merge, tag the release on `main`:
   ```bash
   git switch main && git pull origin main
   git tag -a v0.2.0 -m "ctxmem 0.2.0"
   git push origin v0.2.0
   ```

Versioning follows [Semantic Versioning](https://semver.org/); tags are prefixed
with `v` to match the version in `pyproject.toml`.

---

## 🐛 Reporting bugs & requesting features

Open an issue describing the problem (steps to reproduce, expected vs actual
behavior, OS, Python version, and `ctxmem status` output) or the feature and its
use case.

Thanks for contributing! 🙌
