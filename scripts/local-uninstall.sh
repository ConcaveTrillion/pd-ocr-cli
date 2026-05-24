#!/usr/bin/env bash
# scripts/local-uninstall.sh — uninstall the uv tool (siblings + venv untouched).
set -euo pipefail

TOOL_NAME="pd-ocr"

echo "[local-uninstall] → uv tool uninstall $TOOL_NAME"
uv tool uninstall "$TOOL_NAME" || true
echo "[local-uninstall] ✓ done. Venv + marker unchanged."
