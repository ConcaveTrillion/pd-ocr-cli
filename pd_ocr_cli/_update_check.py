"""Background GitHub-tag check that prints an upgrade notice when a newer
release is available. Best-effort: any network or parse error is swallowed.
"""

import re
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    VERSION = _pkg_version("pd-ocr-cli")
except PackageNotFoundError:  # pragma: no cover - only fires if package metadata is missing
    VERSION = "unknown"

_GITHUB_REPO = "ConcaveTrillion/pd-ocr-cli"
_INSTALL_URL = f"https://raw.githubusercontent.com/{_GITHUB_REPO}/main/install.sh"
_STABLE_TAG_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
_RELEASE_PREFIX_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")


def _parse_stable_tag(version: str) -> tuple[int, int, int] | None:
    """Parse strict stable tags like v1.2.3 or 1.2.3."""
    match = _STABLE_TAG_RE.match(version.strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def _parse_release_prefix(version: str) -> tuple[int, int, int] | None:
    """Parse release prefix from versions like 1.2.3.dev1+abc."""
    match = _RELEASE_PREFIX_RE.match(version.strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def _latest_stable_tag(tags: list[dict]) -> tuple[str, tuple[int, int, int]] | None:
    """Return (tag_name, parsed_version) for the highest stable semver tag."""
    best: tuple[str, tuple[int, int, int]] | None = None
    for tag in tags:
        name = tag.get("name", "")
        parsed = _parse_stable_tag(name)
        if parsed is None:
            continue
        if best is None or parsed > best[1]:
            best = (name, parsed)
    return best


def check_for_update() -> None:
    """Print a notice (to stderr) if a newer release tag is available on GitHub.

    Runs in a background thread — never blocks startup.
    Silently suppressed on any network or parse error.
    """
    if VERSION == "unknown":
        return
    try:
        import json
        import urllib.request

        url = f"https://api.github.com/repos/{_GITHUB_REPO}/tags"
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            tags = json.loads(resp.read())
        if not tags:
            return
        latest_stable = _latest_stable_tag(tags)
        if latest_stable is None:
            return

        current = _parse_release_prefix(VERSION)
        if current is None:
            return

        latest_tag_name, latest = latest_stable
        if latest > current:
            print(
                f"\nNOTICE: A newer version of pd-ocr is available ({latest_tag_name}, "
                f"you have {VERSION}).\n"
                f"  To upgrade, run:\n"
                f"    curl -sSL {_INSTALL_URL} | sh\n",
                file=sys.stderr,
            )
    except Exception:
        pass  # Version check is best-effort
