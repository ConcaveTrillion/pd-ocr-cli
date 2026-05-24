#!/usr/bin/env bash
# scripts/local-install.sh — install uv tool with editable sibling overrides.
#
# Requires local-dev mode (marker must be present).
set -euo pipefail

TOOL_NAME="pd-ocr"                  # repo-specific
PY_SIBLINGS=(pd-book-tools)
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GIT_COMMON_DIR="$(git -C "$REPO_ROOT" rev-parse --git-common-dir)"
CANONICAL_REPO_ROOT="$(dirname "$GIT_COMMON_DIR")"
WORKSPACE_ROOT="$(dirname "$CANONICAL_REPO_ROOT")"
# Marker lives in the canonical repo's .venv (shared across worktrees).
MARKER="$CANONICAL_REPO_ROOT/.venv/.pd-local-mode"

say() { echo "[local-install] $*"; }

if [[ ! -f "$MARKER" ]]; then
  echo "ERROR: not in local-dev mode. Run 'make local-dev' first." >&2
  exit 1
fi

# Build --with-editable args
WITH_ARGS=()
for s in "${PY_SIBLINGS[@]}"; do
  WITH_ARGS+=(--with-editable "$WORKSPACE_ROOT/$s")
done

say "→ uv tool install --editable . ${WITH_ARGS[*]}"
uv tool install --editable . "${WITH_ARGS[@]}" --force

say "✓ $TOOL_NAME installed with editable siblings."
