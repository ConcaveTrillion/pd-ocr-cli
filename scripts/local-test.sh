#!/usr/bin/env bash
# scripts/local-test.sh — run the fast pytest suite against editable local-dev siblings.
#
# Requires local-dev mode. Delegates to repo-specific `make test` after the guard.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GIT_COMMON_DIR="$(git -C "$REPO_ROOT" rev-parse --path-format=absolute --git-common-dir)"
CANONICAL_REPO_ROOT="$(dirname "$GIT_COMMON_DIR")"
# Marker lives in the canonical repo's .venv (shared across worktrees).
MARKER="$CANONICAL_REPO_ROOT/.venv/.pdomain-local-mode"

if [[ ! -f "$MARKER" ]]; then
  echo "ERROR: not in local-dev mode. Run 'make local-dev' first." >&2
  exit 1
fi

# Repo-specific test target
# UV_NO_SYNC=1: keep editable pd-* siblings; a plain `make test` re-syncs and
# reverts them to registry versions, breaking unreleased editable APIs at runtime.
exec env UV_NO_SYNC=1 make -C "$REPO_ROOT" test
