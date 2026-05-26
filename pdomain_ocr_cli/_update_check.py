"""Background GitHub-tag check that prints an upgrade notice when a newer
release is available. Best-effort: any network or parse error is swallowed.
"""

import re
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from typing import Protocol, TypedDict, cast

try:
    _detected_version: str = _pkg_version("pdomain-ocr-cli")
except PackageNotFoundError:  # pragma: no cover - only fires if package metadata is missing
    _detected_version = "unknown"

VERSION: str = _detected_version

_GITHUB_REPO = "pdomain/pdomain-ocr-cli"
_INSTALL_URL = f"https://raw.githubusercontent.com/{_GITHUB_REPO}/main/install.sh"
_STABLE_TAG_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
_RELEASE_PREFIX_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")


class _TagRecord(TypedDict):
    name: str


class _UrlopenResponse(Protocol):
    def __enter__(self) -> "_UrlopenResponse": ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object | None,
    ) -> bool | None: ...

    def read(self) -> bytes: ...


def _parse_stable_tag(version: str) -> tuple[int, int, int] | None:
    """Parse strict stable tags like v1.2.3 or 1.2.3."""
    match = _STABLE_TAG_RE.match(version.strip())
    if not match:
        return None
    a, b, c = (int(p) for p in match.groups())
    return a, b, c


def _parse_release_prefix(version: str) -> tuple[int, int, int] | None:
    """Parse release prefix from versions like 1.2.3.dev1+abc."""
    match = _RELEASE_PREFIX_RE.match(version.strip())
    if not match:
        return None
    a, b, c = (int(p) for p in match.groups())
    return a, b, c


def _latest_stable_tag(tags: list[_TagRecord]) -> tuple[str, tuple[int, int, int]] | None:
    """Return (tag_name, parsed_version) for the highest stable semver tag."""
    best: tuple[str, tuple[int, int, int]] | None = None
    for tag in tags:
        name = tag["name"]
        parsed = _parse_stable_tag(name)
        if parsed is None:
            continue
        if best is None or parsed > best[1]:
            best = (name, parsed)
    return best


def _parse_tag_payload(payload: object) -> list[_TagRecord] | None:
    if not isinstance(payload, list) or not payload:
        return None

    raw_tags = cast("list[object]", payload)
    tags: list[_TagRecord] = []
    for item in raw_tags:
        if not isinstance(item, dict):
            return None
        tag = cast("dict[str, object]", item)
        name = tag.get("name")
        if not isinstance(name, str):
            return None
        tags.append({"name": name})
    return tags


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

        # ``per_page=100`` is GitHub's max; the default of 30 risks dropping
        # the newest stable tag off page 1 once the project accumulates more
        # than 30 tags (incl. dev/rc/draft tags), causing the update notice to
        # silently go stale.
        url = f"https://api.github.com/repos/{_GITHUB_REPO}/tags?per_page=100"
        # Identify ourselves explicitly. urllib's default ``Python-urllib/3.x``
        # User-Agent is generic and GitHub may rate-limit it more aggressively;
        # a clear application UA also helps GitHub diagnose abuse if it occurs.
        req = urllib.request.Request(  # noqa: S310  # https:// URL only; no file:// risk
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"pdomain-ocr-cli/{VERSION}",
            },
        )
        response = cast("_UrlopenResponse", urllib.request.urlopen(req, timeout=3))  # noqa: S310
        with response as resp:
            payload = cast("object", json.loads(resp.read()))
        # GitHub error responses (rate-limit, auth required, repo unavailable)
        # return a JSON *dict* like ``{"message": "API rate limit exceeded ...",
        # "documentation_url": ...}`` rather than the expected list of tag
        # dicts. A truthiness-only guard would let the dict through to
        # ``_latest_stable_tag`` which iterates dict keys (strings) and calls
        # ``str.get("name", "")`` -> AttributeError, masked by the broad
        # ``except Exception: pass`` below. Type-guard explicitly so the
        # update-check machinery degrades cleanly instead of silently dying.
        tags = _parse_tag_payload(payload)
        if tags is None:
            return
        latest_stable = _latest_stable_tag(tags)
        if latest_stable is None:
            return

        current = _parse_release_prefix(VERSION)
        if current is None:
            return

        latest_tag_name, latest = latest_stable
        # A dev/local-suffixed version (e.g. ``1.2.3.dev1+gHASH``) is a
        # *pre-release of* its release prefix — strictly less than the
        # matching stable tag (PEP 440: ``1.2.3.dev1 < 1.2.3``). Without
        # this check, ``_parse_release_prefix`` strips the suffix and the
        # naive ``latest > current`` comparison treats them as equal,
        # silently denying pre-release users the upgrade notice for the
        # very stable they were tracking toward.
        is_pre_release = _parse_stable_tag(VERSION) is None
        if latest > current or (is_pre_release and latest == current):
            notice = (
                f"\nNOTICE: A newer version of pd-ocr is available "
                f"({latest_tag_name}, you have {VERSION}).\n"
                f"  To upgrade, run:\n"
                f"    curl -sSL {_INSTALL_URL} | sh\n"
            )
            print(notice, file=sys.stderr)  # noqa: T201  # CLI output
    except Exception:  # noqa: BLE001 S110  # update check is best-effort; any failure is safe to swallow
        pass  # Version check is best-effort
