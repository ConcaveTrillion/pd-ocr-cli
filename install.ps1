# Install pd-ocr as a standalone tool using uv.
#
# Usage (run in PowerShell):
#   irm https://raw.githubusercontent.com/pdomain/pdomain-ocr-cli/main/install.ps1 | iex
#
# Manual CUDA override (if auto-detection fails):
#   $env:CUDA_VERSION = "12.4"   # replace with your version
#   irm https://raw.githubusercontent.com/pdomain/pdomain-ocr-cli/main/install.ps1 | iex
#
# Python override:
#   $env:PD_OCR_INSTALL_PYTHON = "3.12"
#   irm https://raw.githubusercontent.com/pdomain/pdomain-ocr-cli/main/install.ps1 | iex

$ErrorActionPreference = "Stop"

function Get-CudaVersion {
    if ($env:CUDA_VERSION) {
        return $env:CUDA_VERSION
    }

    if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
        return $null
    }

    try {
        $Query = & nvidia-smi -q 2>$null | Out-String
        if ($Query -match "CUDA Version\s*:\s*([0-9]+\.[0-9]+)") {
            return $Matches[1]
        }
    } catch {
    }

    try {
        $Plain = & nvidia-smi 2>$null | Out-String
        if ($Plain -match "CUDA Version:\s*([0-9]+\.[0-9]+)") {
            return $Matches[1]
        }
    } catch {
    }

    return $null
}

function Get-CudaTag {
    param([Parameter(Mandatory = $true)][string]$CudaVer)
    return "cu" + ($CudaVer -replace "\.", "")
}

function Get-BookToolsExtras {
    param([Parameter(Mandatory = $true)][string]$CudaVer)
    try {
        $Version = [version]$CudaVer
    } catch {
        return ""
    }
    if ($Version.Major -gt 12 -or ($Version.Major -eq 12 -and $Version.Minor -ge 4)) {
        return "[gpu]"
    }
    return ""
}

$HelperPath = $null
if ($PSScriptRoot) {
    $HelperPath = Join-Path $PSScriptRoot "scripts/install-cuda-detect.ps1"
}
if ($HelperPath -and (Test-Path $HelperPath)) {
    . $HelperPath
}

$Repo = "pdomain/pdomain-ocr-cli"
$PdIndexUrl = "https://pdomain.github.io/pdomain-index-pip/simple/"
$PythonVersion = if ($env:PD_OCR_INSTALL_PYTHON) { $env:PD_OCR_INSTALL_PYTHON } else { "3.13" }

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "uv not found -- installing uv..."
    irm https://astral.sh/uv/install.ps1 | iex
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "User") + ";" + $env:PATH
}

$ExtraIndex = ""
$BookToolsExtras = ""

if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    $CudaVer = Get-CudaVersion

    if ($CudaVer) {
        $CudaTag = Get-CudaTag $CudaVer
        $ExtraIndex = "https://download.pytorch.org/whl/$CudaTag"
        Write-Host "Detected CUDA $CudaVer -- will install PyTorch with $CudaTag support."

        $BookToolsExtras = Get-BookToolsExtras $CudaVer
        if ($BookToolsExtras -eq "[gpu]") {
            Write-Host "CUDA $CudaVer >= 12.4 -- enabling pdomain-book-tools[gpu] (CuPy + opencv-cuda)."
        } else {
            Write-Host "CUDA $CudaVer < 12.4 -- installing CPU-only book-tools (cupy-cuda12x needs >= 12.4)."
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

$ReleaseUrl = "https://api.github.com/repos/$Repo/releases/latest"
Write-Host "Resolving latest release via GitHub API..."
$Release = Invoke-RestMethod -Uri $ReleaseUrl
$ReleaseTag = $Release.tag_name
$WheelAsset = $Release.assets |
    Where-Object { $_.name -like "*.whl" -or $_.browser_download_url -like "*.whl" } |
    Select-Object -First 1

if (-not $WheelAsset) {
    throw "Latest release $ReleaseTag has no wheel asset attached."
}

$WheelUrl = $WheelAsset.browser_download_url
$WheelName = if ($WheelAsset.name) {
    $WheelAsset.name
} else {
    Split-Path -Leaf ([Uri]$WheelUrl).AbsolutePath
}

Write-Host "Latest release: $ReleaseTag"
Write-Host "Wheel asset:    $WheelUrl"
Write-Host "pdomain-index-pip:       $PdIndexUrl"

$TempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("pd-ocr-install-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $TempDir | Out-Null

try {
    $WheelFile = Join-Path $TempDir $WheelName
    Write-Host "Downloading wheel..."
    Invoke-WebRequest -Uri $WheelUrl -OutFile $WheelFile

    Write-Host "Installing pd-ocr $ReleaseTag from $WheelName..."
    $UvArgs = @("tool", "install", "--python", $PythonVersion, "--reinstall", $WheelFile, "--extra-index-url", $PdIndexUrl)
    if ($BookToolsExtras) {
        $UvArgs += @("--with", "pdomain-book-tools$BookToolsExtras")
    }
    if ($ExtraIndex) {
        $UvArgs += @("--extra-index-url", $ExtraIndex)
    }
    & uv @UvArgs
} finally {
    Remove-Item -Recurse -Force $TempDir -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "Done! Run: pd-ocr page.png"
Write-Host "If 'pd-ocr' is not found, ensure uv's tool bin is on your PATH."
Write-Host "  uv tool update-shell"
