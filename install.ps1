# Install pd-ocr as a standalone tool using uv.
#
# NOTE: This script has not been tested yet. Please report any issues at
#       https://github.com/ConcaveTrillion/pd-ocr-cli/issues
#
# PRECONDITION (GPU auto-enable):
#   The CUDA >= 12.4 branch below appends `[gpu]` to the install ref. That
#   extra exists only in pd-book-tools >= v0.11.0 (the release that moves
#   cupy-cuda12x + opencv-cuda from mandatory deps into an optional [gpu]
#   extra), and it is exposed transitively via pd-ocr-cli's own [gpu] extra.
#   Until pyproject.toml is repinned to pd-book-tools v0.11.0+, sourcing
#   this script on a CUDA host will produce a "package does not have an
#   extra named gpu" warning from uv. DO NOT MERGE this branch until the
#   pin is bumped.
#
# Usage (run in PowerShell):
#   irm https://raw.githubusercontent.com/ConcaveTrillion/pd-ocr-cli/main/install.ps1 | iex

$ErrorActionPreference = "Stop"

# Install uv if not already present
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "uv not found -- installing uv..."
    irm https://astral.sh/uv/install.ps1 | iex
    # Reload PATH so uv is available in this session
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "User") + ";" + $env:PATH
}

$ExtraIndex = ""
$BookToolsExtras = ""

# Auto-detect NVIDIA CUDA via nvidia-smi
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    try {
        $smiOut = & nvidia-smi 2>$null
        if ($smiOut -match "CUDA Version:\s*(\d+\.\d+)") {
            $CudaVer = $Matches[1]
            $CudaTag = "cu" + ($CudaVer -replace "\.", "")
            $ExtraIndex = "https://download.pytorch.org/whl/$CudaTag"
            Write-Host "Detected CUDA $CudaVer -- will install PyTorch with $CudaTag support."

            # CuPy (cupy-cuda12x) requires CUDA >= 12.4. Use [version]
            # for a clean numeric compare; fall back gracefully on
            # malformed strings.
            try {
                if ([version]$CudaVer -ge [version]"12.4") {
                    $BookToolsExtras = "[gpu]"
                    Write-Host "CUDA $CudaVer >= 12.4 -- enabling pd-ocr-cli[gpu] (CuPy + opencv-cuda)."
                } else {
                    Write-Host "CUDA $CudaVer < 12.4 -- installing CPU-only book-tools (cupy-cuda12x needs >= 12.4)."
                }
            } catch {
                Write-Host "Could not parse CUDA version '$CudaVer' for [gpu] gating -- installing CPU-only."
            }
        } else {
            Write-Host "nvidia-smi found but could not detect CUDA version -- falling back to CPU."
        }
    } catch {
        Write-Host "nvidia-smi found but could not detect CUDA version -- falling back to CPU."
    }
} else {
    Write-Host "No GPU detected -- installing CPU-only PyTorch."
}

# Resolve latest git tag from GitHub
$Repo = "ConcaveTrillion/pd-ocr-cli"
# The install ref points at the project itself (not pd-book-tools). When
# $BookToolsExtras is "[gpu]", pd-ocr-cli's own [gpu] extra is requested,
# which forwards to pd-book-tools[gpu] via the optional-dependency table
# in pyproject.toml. PEP 508 extras attach inside the URL form as
# `<name>[<extras>] @ git+...`; for `git+https://...` refs uv accepts the
# equivalent `git+https://...#egg=<name>[<extras>]` style, but the simpler
# form is to pass `<name>[<extras>] @ git+...`. We keep the existing
# bare-URL ref when no extras are requested, and switch to the PEP 508
# form when [gpu] is on.
$InstallRef = "git+https://github.com/$Repo"
try {
    $Tags = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/tags" -TimeoutSec 10
    if ($Tags -and $Tags.Count -gt 0) {
        $LatestTag = $Tags[0].name
        $InstallRef = "git+https://github.com/$Repo@$LatestTag"
        Write-Host "Installing pd-ocr $LatestTag$BookToolsExtras..."
    } else {
        Write-Host "Installing pd-ocr (latest commit -- no tags found)..."
    }
} catch {
    Write-Host "Installing pd-ocr (latest commit -- could not resolve tag)..."
}

if ($BookToolsExtras) {
    # PEP 508 form so the [gpu] extra attaches to the project ref.
    $InstallRef = "pd-ocr-cli$BookToolsExtras @ $InstallRef"
}

if ($ExtraIndex) {
    uv tool install --python 3.13 --reinstall $InstallRef --extra-index-url $ExtraIndex
} else {
    uv tool install --python 3.13 --reinstall $InstallRef
}

Write-Host ""
Write-Host "Done! Run: pd-ocr page.png"
Write-Host "If 'pd-ocr' is not found, ensure uv's tool bin is on your PATH."
Write-Host "  uv tool update-shell"
