#!/usr/bin/env bash
# install-uv-tool.sh — install pdomain-ocr as a uv tool, auto-detecting CUDA.
#
# Mirrors the original inline `install` recipe behavior: detects an NVIDIA
# GPU + CUDA version via nvidia-smi and adds the matching PyTorch wheel
# index, falls back to a friendly Apple Silicon note, otherwise installs
# CPU-only PyTorch. Log messages go to stdout to match prior behavior.
#
# Usage: scripts/install-uv-tool.sh

set -eu

EXTRA_INDEX=""
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
    CUDA_VER=$(nvidia-smi 2>/dev/null | sed -n 's/.*CUDA Version: \([0-9]*\.[0-9]*\).*/\1/p' | head -1)
    if [ -n "$CUDA_VER" ]; then
        CUDA_TAG="cu$(echo "$CUDA_VER" | tr -d '.')"
        EXTRA_INDEX="https://download.pytorch.org/whl/$CUDA_TAG"
        echo "🟢 Detected CUDA $CUDA_VER — installing PyTorch with $CUDA_TAG support."
    else
        echo "⚠️  nvidia-smi found but could not detect CUDA version — falling back to CPU."
    fi
elif [ "$(uname)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ]; then
    echo "🍎 Detected Apple Silicon — MPS acceleration will be used automatically."
else
    echo "💻 No GPU detected — installing CPU-only PyTorch."
fi

echo "📦 Installing pdomain-ocr from local source..."
if [ -n "$EXTRA_INDEX" ]; then
    uv tool install --reinstall . --extra-index-url "$EXTRA_INDEX"
else
    uv tool install --reinstall .
fi
echo "✅ pdomain-ocr installed. Run: pdomain-ocr --version"
