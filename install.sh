#!/bin/sh
set -e

# Install pd-ocr as a standalone tool using uv.
#
# Pulls the wheel from the latest non-prerelease GitHub Release of
# ConcaveTrillion/pd-ocr-cli and installs it via `uv tool install`. Uses
# `gh` if available (and authenticated); otherwise falls back to the
# public GitHub Releases API via curl.
#
# PRECONDITION (GPU auto-enable):
#   The CUDA >= 12.4 branch below appends `[gpu]` to the pd-book-tools
#   install spec. That extra exists only in pd-book-tools >= v0.11.0 (the
#   release that moves cupy-cuda12x + opencv-cuda from mandatory deps into
#   an optional [gpu] extra). Until pyproject.toml is repinned to
#   pd-book-tools v0.11.0+ via `make upgrade-pd-book-tools`, sourcing this
#   script on a CUDA host will produce a "package does not have an extra
#   named gpu" warning from uv. The install still completes, but the warning
#   is noisy. DO NOT MERGE this branch until the pin is bumped.
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
PD_BOOK_TOOLS_EXTRAS=""

# Auto-detect NVIDIA CUDA
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
    CUDA_VER=$(nvidia-smi 2>/dev/null | sed -n 's/.*CUDA Version: \([0-9]*\.[0-9]*\).*/\1/p' | head -1)
    if [ -n "$CUDA_VER" ]; then
        CUDA_TAG="cu$(echo "$CUDA_VER" | tr -d '.')"
        EXTRA_INDEX="https://download.pytorch.org/whl/${CUDA_TAG}"
        echo "Detected CUDA ${CUDA_VER} — will install PyTorch with ${CUDA_TAG} support."

        # CuPy (cupy-cuda12x) requires CUDA >= 12.4. Only opt into the
        # pd-book-tools[gpu] extra when that minimum is satisfied;
        # otherwise the [gpu] resolve fails with a CuPy version error
        # and a working CPU-only install would have been preferable.
        # POSIX-sh version compare — no `sort -V`, no `awk`.
        CUDA_MAJOR=${CUDA_VER%.*}
        CUDA_MINOR=${CUDA_VER#*.}
        if [ "$CUDA_MAJOR" -gt 12 ] || { [ "$CUDA_MAJOR" -eq 12 ] && [ "$CUDA_MINOR" -ge 4 ]; }; then
            PD_BOOK_TOOLS_EXTRAS="[gpu]"
            echo "CUDA ${CUDA_VER} >= 12.4 — enabling pd-book-tools[gpu] (CuPy + opencv-cuda)."
        else
            echo "CUDA ${CUDA_VER} < 12.4 — installing CPU-only book-tools (cupy-cuda12x needs >= 12.4)."
        fi
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
# Resolve the pd-book-tools git pin from the release's pyproject.toml.
# ---------------------------------------------------------------------------
# pd-book-tools is a sibling pd-* repo published as git tags only — there is
# no PyPI package and no wheel asset on its own Releases. The wheel built
# from this repo carries `Requires-Dist: pd-book-tools` with no source URL
# (PEP 621 wheel METADATA cannot encode `[tool.uv.sources]` git pins), so a
# bare `uv tool install <wheel>` fails: "pd-book-tools was not found in the
# package registry".
#
# Fix: fetch pyproject.toml from the *release tag* (so the pin matches the
# wheel exactly, not whatever main currently has) and pass the git ref to
# uv via `--with 'pd-book-tools @ git+https://...@<tag>'` (PEP 508 direct
# URL). uv resolves the dependency from git and the install proceeds.
#
# The sibling install scripts solve the same problem differently:
#   - pd-ocr-cli/install.ps1 + pd-ocr-labeler/install.sh install the whole
#     project with `git+https://...@<tag>`, which gives uv the project
#     context and `[tool.uv.sources]` activates naturally.
#   - We keep the wheel-download path here (matches the documented release
#     contract — see DEVELOPMENT.md / agent-memory release_flow.md) and
#     supplement it with `--with` for the one git-only transitive dep.
PYPROJECT_URL="https://raw.githubusercontent.com/${REPO}/${RELEASE_TAG}/pyproject.toml"
PYPROJECT_RAW=$(curl -sSfL "$PYPROJECT_URL" 2>/dev/null || true)

PD_BOOK_TOOLS_GIT=""
PD_BOOK_TOOLS_TAG=""
if [ -n "$PYPROJECT_RAW" ]; then
    # Match the line:
    #   pd-book-tools = { git = "https://github.com/.../pd-book-tools.git", tag = "v0.10.0" }
    PD_BOOK_TOOLS_LINE=$(printf '%s\n' "$PYPROJECT_RAW" | grep -E '^[[:space:]]*pd-book-tools[[:space:]]*=' | head -1)
    PD_BOOK_TOOLS_GIT=$(printf '%s' "$PD_BOOK_TOOLS_LINE" | sed -n 's/.*git[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p')
    PD_BOOK_TOOLS_TAG=$(printf '%s' "$PD_BOOK_TOOLS_LINE" | sed -n 's/.*tag[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p')
fi

PD_BOOK_TOOLS_WITH=""
if [ -n "$PD_BOOK_TOOLS_GIT" ] && [ -n "$PD_BOOK_TOOLS_TAG" ]; then
    # ``$PD_BOOK_TOOLS_EXTRAS`` is empty unless the CUDA-detect branch
    # above set it to ``[gpu]`` (NVIDIA + CUDA >= 12.4). In every other
    # case the extras suffix collapses to nothing and uv installs plain
    # ``pd-book-tools``.
    PD_BOOK_TOOLS_WITH="pd-book-tools${PD_BOOK_TOOLS_EXTRAS} @ git+${PD_BOOK_TOOLS_GIT}@${PD_BOOK_TOOLS_TAG}"
    echo "pd-book-tools:  ${PD_BOOK_TOOLS_GIT}@${PD_BOOK_TOOLS_TAG}${PD_BOOK_TOOLS_EXTRAS}"
else
    echo "⚠️  Could not resolve pd-book-tools git pin from ${PYPROJECT_URL}" >&2
    echo "    The install will likely fail with 'pd-book-tools was not found'." >&2
    echo "    File a bug at https://github.com/${REPO}/issues" >&2
fi

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
# Build the install command incrementally so we only emit `--with` / extra
# flags when relevant. POSIX sh has no arrays — use `set --` to manage args.
set -- --reinstall "$WHEEL_FILE"
if [ -n "$PD_BOOK_TOOLS_WITH" ]; then
    set -- "$@" --with "$PD_BOOK_TOOLS_WITH"
fi
if [ -n "$EXTRA_INDEX" ]; then
    set -- "$@" --extra-index-url "$EXTRA_INDEX"
fi
uv tool install "$@"

echo ""
echo "Done! Run: pd-ocr page.png"
echo "If 'pd-ocr' is not found, add uv's tool bin to your PATH:"
echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
