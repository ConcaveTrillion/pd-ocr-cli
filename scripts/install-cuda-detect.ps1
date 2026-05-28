# Pure CUDA-detection helpers for install.ps1.
# Dot-sourced by install.ps1 and by tests/test_install_ps1_cuda.py.
# Contains NO top-level side effects.

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

function Get-CudaTag {
    param([Parameter(Mandatory = $true)][string]$CudaVer)
    return "cu" + ($CudaVer -replace "\.", "")
}

function Get-BookToolsExtras {
    param([Parameter(Mandatory = $true)][string]$CudaVer)
    # CuPy (cupy-cuda12x) requires CUDA >= 12.4.
    if ([version]$CudaVer -ge [version]"12.4") { return "[gpu]" }
    return ""
}
