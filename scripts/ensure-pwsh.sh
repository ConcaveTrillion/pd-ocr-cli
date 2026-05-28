#!/bin/sh
# ensure-pwsh.sh — idempotently ensure PowerShell (pwsh) is installed.
#
# WHY pwsh is required:
#   tests/test_install_ps1_cuda.py invokes the real install.ps1 script to
#   verify that the CUDA/CPU detection logic works correctly. These are NOT
#   mocked — they run actual PowerShell. Without pwsh the tests cannot run
#   and must not silently skip (pwsh availability is a hard requirement of
#   the test suite, not an optional enhancement).
#
# Fast-path: GitHub ubuntu-latest runners have pwsh pre-installed and never
#   reach the apt block. Local Debian 12 devcontainers typically don't, so
#   this script installs it via the Microsoft apt repo.
set -eu

# ---------------------------------------------------------------------------
# Fast-path: pwsh already present (CI ubuntu-latest, or already installed)
# ---------------------------------------------------------------------------
if command -v pwsh > /dev/null 2>&1; then
    version="$(pwsh --version 2>&1 || true)"
    echo "pwsh already present (${version})"
    exit 0
fi

# ---------------------------------------------------------------------------
# Detect distro via /etc/os-release
# ---------------------------------------------------------------------------
if [ ! -f /etc/os-release ]; then
    echo "ERROR: /etc/os-release not found — cannot detect distro." >&2
    echo "Install PowerShell manually: https://learn.microsoft.com/powershell/scripting/install/installing-powershell" >&2
    exit 1
fi

# shellcheck source=/dev/null
. /etc/os-release

# Check whether this is a Debian/Ubuntu family (ID or ID_LIKE)
is_debian_family=0
case "${ID:-}" in
    debian|ubuntu) is_debian_family=1 ;;
esac
if [ "${is_debian_family}" = "0" ]; then
    case "${ID_LIKE:-}" in
        *debian*|*ubuntu*) is_debian_family=1 ;;
    esac
fi

if [ "${is_debian_family}" = "0" ]; then
    echo "ERROR: Unsupported distro (ID=${ID:-unknown}, ID_LIKE=${ID_LIKE:-none})." >&2
    echo "Automatic pwsh install is only supported on Debian/Ubuntu." >&2
    echo "Install PowerShell manually: https://learn.microsoft.com/powershell/scripting/install/installing-powershell" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Debian/Ubuntu: install PowerShell via Microsoft apt repo
# ---------------------------------------------------------------------------

# Build the Microsoft package config URL for the detected distro/version.
# Concretely tested for Debian 12 (bookworm); the URL pattern is documented at
# https://learn.microsoft.com/powershell/scripting/install/installing-powershell-on-linux
DISTRO_ID="${ID:-debian}"
DISTRO_VERSION="${VERSION_ID:-12}"

echo "Detected ${DISTRO_ID} ${DISTRO_VERSION} — installing PowerShell via Microsoft apt repo..."

MS_DEB_URL="https://packages.microsoft.com/config/${DISTRO_ID}/${DISTRO_VERSION}/packages-microsoft-prod.deb"

echo "Fetching Microsoft package config from: ${MS_DEB_URL}"

sudo apt-get update -qq
sudo apt-get install -y -qq wget apt-transport-https

tmp="$(mktemp -d)"
# shellcheck disable=SC2064  # we want $tmp expanded now, not at trap time
trap "rm -rf '${tmp}'" EXIT

wget -q "${MS_DEB_URL}" -O "${tmp}/ms.deb"
sudo dpkg -i "${tmp}/ms.deb"

sudo apt-get update -qq
sudo apt-get install -y -qq powershell

# ---------------------------------------------------------------------------
# Post-install verification
# ---------------------------------------------------------------------------
if command -v pwsh > /dev/null 2>&1; then
    version="$(pwsh --version 2>&1 || true)"
    echo "pwsh installed successfully (${version})"
else
    echo "ERROR: pwsh install appeared to succeed but 'command -v pwsh' still fails." >&2
    echo "Check apt output above for errors, or install manually:" >&2
    echo "  https://learn.microsoft.com/powershell/scripting/install/installing-powershell" >&2
    exit 1
fi
