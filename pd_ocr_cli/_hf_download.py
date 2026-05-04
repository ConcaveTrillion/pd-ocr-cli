"""HuggingFace Hub download wrapper used for OCR / layout model artifacts.

Adds a friendly "Downloading X from Y" line on cold cache, fetches optional
``.arch`` / ``.vocab`` sidecars when present, and silences only HF Hub's
unauthenticated-requests advisory (other warnings still surface).
"""

import contextlib
import logging
import sys
from pathlib import Path


@contextlib.contextmanager
def _suppress_hf_unauth_warning():
    """Suppress only HF Hub's unauthenticated advisory warning.

    Public model downloads intentionally support anonymous access, so this
    warning is noisy for normal users. Other HF warnings should still surface.
    """

    class _HFUnauthWarningFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            msg = record.getMessage().lower()
            return not ("unauthenticated requests" in msg and "hf hub" in msg and "hf_token" in msg)

    logger = logging.getLogger("huggingface_hub.utils._http")
    filt = _HFUnauthWarningFilter()
    logger.addFilter(filt)
    try:
        yield
    finally:
        logger.removeFilter(filt)


def hf_download(
    repo_id: str,
    filename: str,
    revision: str | None,
    sidecars: tuple[str, ...] = (),
) -> Path:
    """Download ``filename`` from ``repo_id`` at ``revision`` (or latest).

    Returns the local cached path. If ``sidecars`` is given, also fetch
    those sidecar extensions (e.g. ``(".arch", ".vocab")``) when they
    exist in the repo — missing sidecars are silently skipped. Use only
    for file types that conventionally carry sidecars (OCR ``.pt``
    checkpoints); layout files don't need them.
    """
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print(
            "ERROR: huggingface_hub is required for --hf-repo. "
            "Install it with: pip install huggingface_hub",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        from huggingface_hub import _CACHED_NO_EXIST, try_to_load_from_cache

        cached = try_to_load_from_cache(repo_id=repo_id, filename=filename, revision=revision)
        already_cached = cached is not None and cached is not _CACHED_NO_EXIST
    except Exception:
        already_cached = False

    if not already_cached:
        print(f"Downloading {filename} from {repo_id} (revision={revision or 'latest'})...")

    with _suppress_hf_unauth_warning():
        local_path = hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            revision=revision,
        )

    if sidecars:
        try:
            from huggingface_hub.utils import EntryNotFoundError as _HFNotFound
        except ImportError:
            _HFNotFound = Exception  # older hub versions: treat all as optional

        for ext in sidecars:
            sidecar = filename.rsplit(".", 1)[0] + ext
            try:
                with _suppress_hf_unauth_warning():
                    hf_hub_download(repo_id=repo_id, filename=sidecar, revision=revision)
            except _HFNotFound:
                pass  # Sidecar not present in repo
    return Path(local_path)
