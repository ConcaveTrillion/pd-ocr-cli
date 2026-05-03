#!/bin/sh
set -e

# Install pd-ocr as a standalone tool using uv.
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/ConcaveTrillion/pd-ocr-cli/main/install.sh | sh

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

# Resolve latest git tag from GitHub
REPO="ConcaveTrillion/pd-ocr-cli"
LATEST_TAG=$(curl -sSf "https://api.github.com/repos/${REPO}/tags" 2>/dev/null \
    | grep -o '"name": "[^"]*"' | head -1 | grep -o '[^"]*$') || true

if [ -n "$LATEST_TAG" ]; then
    INSTALL_REF="git+https://github.com/${REPO}@${LATEST_TAG}"
    echo "Installing pd-ocr ${LATEST_TAG}..."
else
    INSTALL_REF="git+https://github.com/${REPO}"
    echo "Installing pd-ocr (latest commit — could not resolve tag)..."
fi

if [ -n "$EXTRA_INDEX" ]; then
    uv tool install --reinstall "$INSTALL_REF" \
        --extra-index-url "$EXTRA_INDEX"
else
    uv tool install --reinstall "$INSTALL_REF"
fi

echo ""
echo "Done! Run: pd-ocr page.png"
echo "If 'pd-ocr' is not found, add uv's tool bin to your PATH:"
echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
