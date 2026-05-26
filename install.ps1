# Install pd-ocr as a standalone tool using uv.
#
# NOTE: This script has not been tested yet. Please report any issues at
#       https://github.com/pdomain/pdomain-ocr-cli/issues
#
# PRECONDITION (GPU auto-enable):
#   The CUDA >= 12.4 branch below appends `[gpu]` to the install ref. That
#   extra exists only in pdomain-book-tools >= v0.11.0 (the release that moves
#   cupy-cuda12x + opencv-cuda from mandatory deps into an optional [gpu]
#   extra), and it is exposed transitively via pdomain-ocr-cli's own [gpu] extra.
#   Until pyproject.toml is repinned to pdomain-book-tools v0.11.0+, sourcing
#   this script on a CUDA host will produce a "package does not have an
#   extra named gpu" warning from uv. DO NOT MERGE this branch until the
#   pin is bumped.
#
# Usage (run in PowerShell):
#   irm https://raw.githubusercontent.com/pdomain/pdomain-ocr-cli/main/install.ps1 | iex
#
# Manual CUDA override (if auto-detection fails):
#   $env:CUDA_VERSION = "12.4"   # replace with your version
#   irm https://raw.githubusercontent.com/pdomain/pdomain-ocr-cli/main/install.ps1 | iex

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

# ── CUDA version detection ──────────────────────────────────────────────────
#
# Resolution order:
#   1. $env:CUDA_VERSION — manual override (e.g. "12.4")
#   2. nvidia-smi -q     — verbose query output; always contains
#                          "CUDA Version                          : X.Y"
#   3. nvidia-smi        — summary table header; contains "CUDA Version: X.Y"
#
# IMPORTANT: PowerShell -match on an array returns the matching *elements*
# (not $true/$false) and does NOT populate $Matches. We must join the output
# array into a single string before using -match so that the capture group
# populates $Matches[1].

function Get-CudaVersion {
    # 1. Manual env override takes precedence.
    if ($env:CUDA_VERSION) {
        Write-Host "Using CUDA_VERSION override: $($env:CUDA_VERSION)"
        return $env:CUDA_VERSION
    }

    if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
        return $null
    }

    # 2. nvidia-smi -q (verbose output; reliable on all supported platforms)
    #    Format:  "    CUDA Version                          : 12.4"
    #    Allow optional whitespace around the colon.
    try {
        $qOut = & nvidia-smi -q 2>$null
        $qStr = ($qOut -join "`n")
        if ($qStr -match "CUDA Version\s*:\s*(\d+\.\d+)") {
            return $Matches[1]
        }
    } catch {
        # nvidia-smi -q unavailable; fall through to plain nvidia-smi
    }

    # 3. Plain nvidia-smi summary table header.
    #    Format:  "| ... CUDA Version: 12.4   |"
    try {
        $smiOut = & nvidia-smi 2>$null
        $smiStr = ($smiOut -join "`n")
        if ($smiStr -match "CUDA Version:\s*(\d+\.\d+)") {
            return $Matches[1]
        }
    } catch {
        # nvidia-smi failed entirely; return $null below
    }

    return $null
}

if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    $CudaVer = Get-CudaVersion

    if ($CudaVer) {
        $CudaTag = "cu" + ($CudaVer -replace "\.", "")
        $ExtraIndex = "https://download.pytorch.org/whl/$CudaTag"
        Write-Host "Detected CUDA $CudaVer -- will install PyTorch with $CudaTag support."

        # CuPy (cupy-cuda12x) requires CUDA >= 12.4. Use [version]
        # for a clean numeric compare; fall back gracefully on
        # malformed strings.
        try {
            if ([version]$CudaVer -ge [version]"12.4") {
                $BookToolsExtras = "[gpu]"
                Write-Host "CUDA $CudaVer >= 12.4 -- enabling pdomain-ocr-cli[gpu] (CuPy + opencv-cuda)."
            } else {
                Write-Host "CUDA $CudaVer < 12.4 -- installing CPU-only book-tools (cupy-cuda12x needs >= 12.4)."
            }
        } catch {
            Write-Host "Could not parse CUDA version '$CudaVer' for [gpu] gating -- installing CPU-only."
        }
    } else {
        Write-Host ""
        Write-Host "WARNING: NVIDIA GPU detected but CUDA version could not be determined."
        Write-Host "         Installing CPU-only build of pd-ocr."
        Write-Host ""
        Write-Host "         To install the GPU build instead, re-run with a manual override:"
        Write-Host "           `$env:CUDA_VERSION = `"12.4`"   # replace with your CUDA version"
        Write-Host "           irm https://raw.githubusercontent.com/pdomain/pdomain-ocr-cli/main/install.ps1 | iex"
        Write-Host ""
        Write-Host "         Find your CUDA version by running:  nvidia-smi"
        Write-Host "         and looking for the 'CUDA Version' field in the output."
        Write-Host ""
    }
} else {
    Write-Host "No GPU detected -- installing CPU-only PyTorch."
}

# Resolve latest git tag from GitHub
$Repo = "pdomain/pdomain-ocr-cli"
# The install ref points at the project itself (not pdomain-book-tools). When
# $BookToolsExtras is "[gpu]", pdomain-ocr-cli's own [gpu] extra is requested,
# which forwards to pdomain-book-tools[gpu] via the optional-dependency table
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
    $InstallRef = "pdomain-ocr-cli$BookToolsExtras @ $InstallRef"
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
