#!/bin/sh
set -e

# Install pd-ocr as a standalone tool using uv.
#
# Pulls the wheel from the latest non-prerelease GitHub Release of
# ConcaveTrillion/pd-ocr-cli and installs it via `uv tool install`. Uses
# `gh` if available (and authenticated); otherwise falls back to the
# public GitHub Releases API via curl.
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/ConcaveTrillion/pd-ocr-cli/main/install.sh | sh

REPO="ConcaveTrillion/pd-ocr-cli"

# Install uv if not already present
if ! command -v uv >/dev/null 2>&1; then
    echo "uv not found — installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

EXTRA_INDEX=""

# Auto-detect NVIDIA CUDA
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
    CUDA_VER=$(nvidia-smi 2>/dev/null | sed -n 's/.*CUDA Version: \([0-9]*\.[0-9]*\).*/\1/p' | head -1)
    if [ -n "$CUDA_VER" ]; then
        CUDA_TAG="cu$(echo "$CUDA_VER" | tr -d '.')"
        EXTRA_INDEX="https://download.pytorch.org/whl/${CUDA_TAG}"
        echo "Detected CUDA ${CUDA_VER} — will install PyTorch with ${CUDA_TAG} support."
    else
        echo "nvidia-smi found but could not detect CUDA version — falling back to CPU."
    fi
# Detect Apple Silicon (MPS)
elif [ "$(uname)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ]; then
    echo "Detected Apple Silicon — MPS acceleration will be used automatically."
else
    echo "No GPU detected — installing CPU-only PyTorch."
fi

# ---------------------------------------------------------------------------
# Resolve the latest non-prerelease GitHub Release and find the wheel asset.
# ---------------------------------------------------------------------------
# We pin to the asset URL of the .whl on the "latest" Release. The Release
# workflow (.github/workflows/release.yml) attaches both .whl and .tar.gz —
# we install the .whl directly so end users don't need a build toolchain.

WHEEL_URL=""
RELEASE_TAG=""

if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    echo "Resolving latest release via gh..."
    # `gh release view --json` returns assets with their download URLs.
    RELEASE_JSON=$(gh release view --repo "$REPO" --json tagName,assets 2>/dev/null || true)
    if [ -n "$RELEASE_JSON" ]; then
        RELEASE_TAG=$(printf '%s' "$RELEASE_JSON" | grep -o '"tagName":"[^"]*"' | head -1 | sed 's/.*"tagName":"\([^"]*\)".*/\1/')
        # Pull the first .whl asset's URL.
        WHEEL_URL=$(printf '%s' "$RELEASE_JSON" \
            | tr ',' '\n' \
            | grep -o '"url":"[^"]*\.whl"' \
            | head -1 \
            | sed 's/.*"url":"\([^"]*\)".*/\1/')
    fi
fi

if [ -z "$WHEEL_URL" ]; then
    echo "Resolving latest release via GitHub API..."
    RELEASE_JSON=$(curl -sSfL "https://api.github.com/repos/${REPO}/releases/latest" 2>/dev/null || true)
    if [ -z "$RELEASE_JSON" ]; then
        echo "❌ Could not query the GitHub Releases API for ${REPO}." >&2
        echo "   Check your network, or install manually with:" >&2
        echo "     uv tool install git+https://github.com/${REPO}" >&2
        exit 1
    fi
    RELEASE_TAG=$(printf '%s' "$RELEASE_JSON" \
        | grep '"tag_name"' | head -1 \
        | sed 's/.*"tag_name": *"\([^"]*\)".*/\1/')
    WHEEL_URL=$(printf '%s' "$RELEASE_JSON" \
        | grep '"browser_download_url"' \
        | grep '\.whl"' \
        | head -1 \
        | sed 's/.*"browser_download_url": *"\([^"]*\)".*/\1/')
fi

if [ -z "$WHEEL_URL" ]; then
    echo "❌ Latest release ${RELEASE_TAG:-?} has no wheel asset attached." >&2
    echo "   Cannot install. Please check https://github.com/${REPO}/releases" >&2
    echo "   and report the missing wheel — or install from source with:" >&2
    echo "     uv tool install git+https://github.com/${REPO}" >&2
    exit 1
fi

echo "Latest release: ${RELEASE_TAG:-(unknown tag)}"
echo "Wheel asset:    ${WHEEL_URL}"

# ---------------------------------------------------------------------------
# Download the wheel to a temp dir and install.
# ---------------------------------------------------------------------------
TMPDIR=$(mktemp -d)
# shellcheck disable=SC2064
trap "rm -rf '$TMPDIR'" EXIT

WHEEL_FILE="$TMPDIR/$(basename "$WHEEL_URL")"
echo "Downloading wheel..."
# `gh` asset URLs (api.github.com/repos/.../assets/<id>) require an Accept
# header to receive the binary; public browser_download_url variants do not.
# Sending the header for both forms is harmless.
if ! curl -sSfL \
        -H "Accept: application/octet-stream" \
        -o "$WHEEL_FILE" "$WHEEL_URL"; then
    echo "❌ Failed to download wheel from ${WHEEL_URL}" >&2
    exit 1
fi

echo "Installing pd-ocr ${RELEASE_TAG:-} from $(basename "$WHEEL_FILE")..."
if [ -n "$EXTRA_INDEX" ]; then
    uv tool install --reinstall "$WHEEL_FILE" \
        --extra-index-url "$EXTRA_INDEX"
else
    uv tool install --reinstall "$WHEEL_FILE"
fi

echo ""
echo "Done! Run: pd-ocr page.png"
echo "If 'pd-ocr' is not found, add uv's tool bin to your PATH:"
echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
