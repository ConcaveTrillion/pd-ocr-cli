#!/usr/bin/env bash
# upgrade-pd-book-tools.sh — repin pd-book-tools to its latest GitHub tag.
#
# Fetches the most recent tag from the ConcaveTrillion/pd-book-tools repo's
# tags API, rewrites the matching git-source line in pyproject.toml to use
# that tag, then runs `uv sync --group dev` so the lock + venv update.
#
# Usage: scripts/upgrade-pd-book-tools.sh

set -euo pipefail

echo "🔍 Fetching latest pd-book-tools tag..."
LATEST_TAG=$(curl -sSf "https://api.github.com/repos/ConcaveTrillion/pd-book-tools/tags" \
    | grep '"name"' | head -1 | sed 's/.*"name": "\(.*\)".*/\1/')

if [ -z "$LATEST_TAG" ]; then
    echo "❌ Could not fetch latest tag."
    exit 1
fi

echo "📌 Pinning to $LATEST_TAG..."
sed -i "s|pd-book-tools = { git = \"https://github.com/ConcaveTrillion/pd-book-tools.git\", tag = \".*\" }|pd-book-tools = { git = \"https://github.com/ConcaveTrillion/pd-book-tools.git\", tag = \"$LATEST_TAG\" }|" pyproject.toml

echo "📦 Syncing..."
uv sync --group dev

echo "✅ pd-book-tools upgraded to $LATEST_TAG!"
