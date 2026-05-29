# Pure CUDA-detection helpers for install.ps1.
# Dot-sourced by install.ps1 and by tests/test_install_ps1_cuda.py.
# Contains NO top-level side effects.

function Get-CudaVersion {
    if ($env:CUDA_VERSION) {
        return $env:CUDA_VERSION
    }

    if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
        return $null
    }

    try {
        $qStr = & nvidia-smi -q 2>$null | Out-String
        if ($qStr -match "CUDA Version\s*:\s*([0-9]+\.[0-9]+)") {
            return $Matches[1]
        }
    } catch {
    }

    try {
        $smiStr = & nvidia-smi 2>$null | Out-String
        if ($smiStr -match "CUDA Version:\s*([0-9]+\.[0-9]+)") {
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
