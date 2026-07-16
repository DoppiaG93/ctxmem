# 🤝 Contributing to ctxmem

Thanks for your interest in **ctxmem**!

> **⚠️ Contributions are currently invite-only.**
> The project is developed by a small set of invited collaborators, and
> unsolicited pull requests are not being accepted at this time. If you would
> like to contribute, please reach out to the maintainer
> ([@DoppiaG93](https://github.com/DoppiaG93)) to be added as a collaborator
> first. **Bug reports and feature requests are always welcome** through
> [GitHub issues](https://github.com/DoppiaG93/ctxmem/issues).

The rest of this guide explains how the project is organized and the workflow
invited collaborators are expected to follow.

---

## 🛠️ Development setup

```bash
git clone https://github.com/DoppiaG93/ctxmem.git
cd ctxmem

python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate

python -m pip install --upgrade pip
pip install -e ".[all,dev]"          # optional runtime extras + pytest/pylint
ctxmem --help                        # verify the CLI works
```

Requirements: **Python 3.8+**. The core has zero third-party dependencies; the
extras (`mcp`, `semantic`, `bench`, `test`, `lint`, `dev`) are optional.

Before opening a pull request, run the local checks:

```bash
python -m pytest
python -m pylint src/ctxmem tests
ctxmem --help
```

The same test and lint checks run in GitHub Actions for pull requests only.

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
| `release/` | `develop` | `main` **and** `develop` | Prepare a release (version bump, final polish) |
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

Releases use a short-lived `release/*` branch (classic Git Flow): it branches
from `develop` and merges into **both `main` and `develop`**.

1. Make sure `develop` has everything intended for the release.
2. Cut a release branch from `develop` and bump the version:
   ```bash
   git switch develop && git pull origin develop
   git switch -c release/1.5.0
   scripts/release.sh 1.5.0 --no-tag     # bump pyproject.toml + commit (no tag yet)
   ```
   Use this branch only for release polish (version bump, changelog, last fixes).
3. Open a PR **`release/1.5.0` → `main`** and merge it (reviewed).
4. Tag the release on `main` — pushing the tag triggers the PyPI publish:
   ```bash
   git switch main && git pull origin main
   git tag -a v1.5.0 -m "ctxmem 1.5.0"
   git push origin v1.5.0
   ```
5. Back-merge the release into `develop` so it keeps the version bump, then
   delete the branch:
   ```bash
   git switch develop && git merge --no-ff release/1.5.0
   git push origin develop
   ```

`scripts/release.sh` (maintainer-only, gitignored) automates the bump/commit/tag.
Inside a `release/*` branch pass `--no-tag` (you tag on `main` in step 4); add
`--push` to also push and open the GitHub Release.

The version in `pyproject.toml` is the single source of truth
(`ctxmem.__version__` reads it from the installed package metadata). Versioning
follows [Semantic Versioning](https://semver.org/); tags are prefixed with `v`
to match `pyproject.toml`, and the publish workflow verifies they agree before
uploading to PyPI.

---

## 🐛 Reporting bugs & requesting features

Open an issue describing the problem (steps to reproduce, expected vs actual
behavior, OS, Python version, and `ctxmem status` output) or the feature and its
use case.

Thanks for contributing! 🙌
