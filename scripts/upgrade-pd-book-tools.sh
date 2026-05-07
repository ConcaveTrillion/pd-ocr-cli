#!/usr/bin/env bash
# upgrade-pd-book-tools.sh — repin pd-book-tools to its latest published version.
#
# pd-book-tools is published on the self-hosted pd-index PEP 503 index at
# https://concavetrillion.github.io/pd-index/simple/. This script fetches
# the index page, extracts the highest version from the wheel filenames, and
# rewrites the version lower-bound in pyproject.toml, then runs `uv sync`
# so the lock + venv update.
#
# Usage: scripts/upgrade-pd-book-tools.sh

set -euo pipefail

PD_INDEX_URL="https://concavetrillion.github.io/pd-index/simple/pd-book-tools/"

echo "Fetching pd-book-tools versions from pd-index..."
INDEX_HTML=$(curl -sSf "$PD_INDEX_URL" 2>/dev/null || true)

if [ -z "$INDEX_HTML" ]; then
    echo "❌ Could not reach pd-index at ${PD_INDEX_URL}" >&2
    exit 1
fi

# Extract version numbers from wheel filenames, e.g.:
#   pd_book_tools-0.12.0-py3-none-any.whl  →  0.12.0
LATEST_VERSION=$(printf '%s\n' "$INDEX_HTML" \
    | grep -oE 'pd_book_tools-[0-9]+\.[0-9]+\.[0-9]+-' \
    | sed 's/pd_book_tools-//;s/-$//' \
    | sort -t. -k1,1n -k2,2n -k3,3n \
    | tail -1)

if [ -z "$LATEST_VERSION" ]; then
    echo "❌ Could not parse any version from ${PD_INDEX_URL}" >&2
    exit 1
fi

echo "Pinning to >=${LATEST_VERSION}..."

# Update the version lower-bound: pd-book-tools>=<old>  →  pd-book-tools>=<new>
sed -i "s|\"pd-book-tools>=[0-9][^\"]*\"|\"pd-book-tools>=${LATEST_VERSION}\"|g" pyproject.toml

echo "Syncing..."
uv sync --group dev

echo "pd-book-tools upgraded to >=${LATEST_VERSION}!"
