#!/usr/bin/env bash
# scripts/local-run.sh — run repo's CLI/server against the local-dev workspace.
#
# Requires local-dev mode. Delegates to repo-specific `make run` after the guard.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GIT_COMMON_DIR="$(git -C "$REPO_ROOT" rev-parse --git-common-dir)"
CANONICAL_REPO_ROOT="$(dirname "$GIT_COMMON_DIR")"
# Marker lives in the canonical repo's .venv (shared across worktrees).
MARKER="$CANONICAL_REPO_ROOT/.venv/.pd-local-mode"

if [[ ! -f "$MARKER" ]]; then
  echo "ERROR: not in local-dev mode. Run 'make local-dev' first." >&2
  exit 1
fi

# Repo-specific run target
exec make -C "$REPO_ROOT" run
