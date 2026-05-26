#!/usr/bin/env bash
# upgrade-pdomain-book-tools.sh — repin pdomain-book-tools to its latest published version.
#
# pdomain-book-tools is published on the self-hosted pdomain-index-pip PEP 503 index at
# https://pdomain.github.io/pdomain-index-pip/simple/. This script fetches
# the index page, extracts the highest version from the wheel filenames, and
# rewrites the version lower-bound in pyproject.toml, then runs `uv sync`
# so the lock + venv update.
#
# Usage: scripts/upgrade-pdomain-book-tools.sh

set -euo pipefail

PD_INDEX_URL="https://pdomain.github.io/pdomain-index-pip/simple/pdomain-book-tools/"

echo "Fetching pdomain-book-tools versions from pdomain-index-pip..."
INDEX_HTML=$(curl -sSf "$PD_INDEX_URL" 2>/dev/null || true)

if [ -z "$INDEX_HTML" ]; then
    echo "❌ Could not reach pdomain-index-pip at ${PD_INDEX_URL}" >&2
    exit 1
fi

# Extract version numbers from wheel filenames, e.g.:
#   pdomain_book_tools-0.12.0-py3-none-any.whl  →  0.12.0
LATEST_VERSION=$(printf '%s\n' "$INDEX_HTML" \
    | grep -oE 'pdomain_book_tools-[0-9]+\.[0-9]+\.[0-9]+-' \
    | sed 's/pdomain_book_tools-//;s/-$//' \
    | sort -t. -k1,1n -k2,2n -k3,3n \
    | tail -1)

if [ -z "$LATEST_VERSION" ]; then
    echo "❌ Could not parse any version from ${PD_INDEX_URL}" >&2
    exit 1
fi

echo "Pinning to >=${LATEST_VERSION}..."

# Update the version lower-bound: pdomain-book-tools>=<old>  →  pdomain-book-tools>=<new>
sed -i "s|\"pdomain-book-tools>=[0-9][^\"]*\"|\"pdomain-book-tools>=${LATEST_VERSION}\"|g" pyproject.toml

echo "Syncing..."
uv sync --group dev

echo "pdomain-book-tools upgraded to >=${LATEST_VERSION}!"
