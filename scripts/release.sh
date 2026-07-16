#!/usr/bin/env bash
#
# release.sh — bump the version and cut a release for ctxmem.
#
# Maintainer-only helper (scripts/ is gitignored, not shipped). It:
#   1. computes the new version from pyproject.toml,
#   2. writes it into pyproject.toml,
#   3. commits the bump and (unless --no-tag) creates an annotated tag vX.Y.Z,
#   4. optionally (--push) pushes and opens a GitHub Release, which triggers
#      .github/workflows/publish.yml -> build + publish to PyPI.
#
# The version in pyproject.toml at the tagged commit is what gets published, so
# whoever creates the tag (this script, or you on main) must tag the bumped commit.
#
# Git Flow (release branch): run this INSIDE a release/* branch with --no-tag to
# bump + commit, merge the branch into main, then tag vX.Y.Z on main (the tag is
# what publishes). Use plain (no --no-tag) when you tag directly on main.
#
# Usage:
#   scripts/release.sh <patch|minor|major|X.Y.Z> [--no-tag] [--push]
#
# Examples:
#   scripts/release.sh 1.5.0 --no-tag   # release-branch bump: commit only, tag on main later
#   scripts/release.sh patch            # bump patch, commit + tag locally
#   scripts/release.sh minor --push     # bump, tag, push, and create the release
#
set -euo pipefail

# --- locate repo root (script lives in <root>/scripts) ------------------------
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PYPROJECT="pyproject.toml"

die() { echo "error: $*" >&2; exit 1; }

# --- args ---------------------------------------------------------------------
[ $# -ge 1 ] || die "usage: scripts/release.sh <patch|minor|major|X.Y.Z> [--no-tag] [--push]"
BUMP="$1"; shift || true
PUSH="no"
NOTAG="no"
for arg in "$@"; do
  case "$arg" in
    --push) PUSH="yes" ;;
    --no-tag) NOTAG="yes" ;;
    *) die "unknown option: $arg" ;;
  esac
done

# --- preconditions ------------------------------------------------------------
[ -f "$PYPROJECT" ] || die "$PYPROJECT not found (run from the repo)"
git diff --quiet && git diff --cached --quiet || \
  die "working tree not clean — commit or stash your changes first"

BRANCH="$(git rev-parse --abbrev-ref HEAD)"

# --- current version ----------------------------------------------------------
CUR="$(grep -E '^version = ' "$PYPROJECT" | sed -E 's/version = "(.*)"/\1/')"
[ -n "$CUR" ] || die "could not read current version from $PYPROJECT"

# --- compute the new version --------------------------------------------------
if [[ "$BUMP" =~ ^[0-9]+\.[0-9]+\.[0-9]+([abrc.].*)?$ ]]; then
  NEW="$BUMP"
else
  IFS=. read -r MA MI PA <<< "$CUR"
  case "$BUMP" in
    major) NEW="$((MA + 1)).0.0" ;;
    minor) NEW="${MA}.$((MI + 1)).0" ;;
    patch) NEW="${MA}.${MI}.$((PA + 1))" ;;
    *) die "first arg must be patch|minor|major or an explicit X.Y.Z" ;;
  esac
fi

TAG="v${NEW}"
if [ "$NOTAG" != "yes" ]; then
  git rev-parse -q --verify "refs/tags/${TAG}" >/dev/null && \
    die "tag ${TAG} already exists"
fi

echo "Repo branch : ${BRANCH}"
echo "Version     : ${CUR}  ->  ${NEW}"
if [ "$NOTAG" = "yes" ]; then
  echo "Tag         : (skipped — tag ${TAG} on main after merge)"
else
  echo "Tag         : ${TAG}"
fi
echo "Push+Release: ${PUSH}"
read -r -p "Proceed? [y/N] " ans
[[ "$ans" =~ ^[Yy]$ ]] || { echo "aborted."; exit 1; }

# --- apply the bump -----------------------------------------------------------
sed -i -E "s/^version = \".*\"/version = \"${NEW}\"/" "$PYPROJECT"
grep -E '^version = ' "$PYPROJECT"

git add "$PYPROJECT"
git commit -m "chore(release): ${NEW}"
if [ "$NOTAG" = "yes" ]; then
  echo "Committed bump ${NEW} (no tag)."
else
  git tag -a "$TAG" -m "Release ${NEW}"
  echo "Committed bump and created tag ${TAG}."
fi

# --- next steps: release-branch flow, local-only, or push ---------------------
if [ "$NOTAG" = "yes" ]; then
  if [ "$PUSH" = "yes" ]; then
    read -r -p "Push ${BRANCH}? [y/N] " ans2
    [[ "$ans2" =~ ^[Yy]$ ]] || { echo "not pushed. Commit exists locally."; exit 1; }
    git push origin "$BRANCH"
  fi
  cat <<EOF

Bump committed on ${BRANCH}. Finish the release (Git Flow):
  1. Open a PR ${BRANCH} -> main and merge it.
  2. Tag on main (this publishes to PyPI):
       git switch main && git pull origin main
       git tag -a ${TAG} -m "ctxmem ${NEW}" && git push origin ${TAG}
  3. Back-merge into develop:
       git switch develop && git merge --no-ff ${BRANCH} && git push origin develop
EOF
  exit 0
fi

# --- optionally push + create the GitHub Release ------------------------------
if [ "$PUSH" != "yes" ]; then
  cat <<EOF

Done (local only). To publish, push and create the release:
  git push origin ${BRANCH} ${TAG}
  gh release create ${TAG} --target ${BRANCH} --title "${TAG}" --generate-notes
EOF
  exit 0
fi

command -v gh >/dev/null || die "gh (GitHub CLI) not found; push manually or install gh"
read -r -p "Push ${BRANCH} + ${TAG} and create GitHub Release ${TAG}? [y/N] " ans2
[[ "$ans2" =~ ^[Yy]$ ]] || { echo "not pushed. Tag/commit exist locally."; exit 1; }

git push origin "$BRANCH" "$TAG"
gh release create "$TAG" --target "$BRANCH" --title "$TAG" --generate-notes
echo "Release ${TAG} created — the publish workflow will build and upload to PyPI."
