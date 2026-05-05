"""Argparse-shaped adapters around :mod:`pd_book_tools.hf`.

The canonical model-resolution primitives live in ``pd_book_tools.hf`` so
pd-ocr-cli, pd-ocr-labeler, and pd-prep-for-pgdp share them. This module keeps
only the argparse-flavoured wrappers that the CLI's ``ocr_to_txt`` driver
needs — the kwargs-shaped functions in ``pd_book_tools.hf`` are the right
target for non-CLI callers.
"""

from __future__ import annotations

import sys
from pathlib import Path

from pd_book_tools.hf import (
    DEFAULT_DET_FILENAME,
    DEFAULT_HF_REPO,
    DEFAULT_RECO_FILENAME,
    LAYOUT_MODEL_FILES,
    OCR_MODEL_SIDECARS,
    hf_download,
    prefetch_layout_files,
    short_revision,
    silence_transformers_load_chatter,
    suppress_hf_unauth_warning,
)
from pd_book_tools.hf import (
    resolve_layout_source as _resolve_layout_source_kwargs,
)
from pd_book_tools.hf import (
    resolve_ocr_models as _resolve_ocr_models_kwargs,
)

__all__ = [
    "DEFAULT_DET_FILENAME",
    "DEFAULT_HF_REPO",
    "DEFAULT_RECO_FILENAME",
    "LAYOUT_MODEL_FILES",
    "OCR_MODEL_SIDECARS",
    "det_source_descriptor",
    "hf_download",
    "prefetch_layout_files",
    "reco_source_descriptor",
    "resolve_layout_source",
    "resolve_ocr_models",
    "short_revision",
    "silence_transformers_load_chatter",
    "suppress_hf_unauth_warning",
]


# ---------------------------------------------------------------------------
# OCR detection + recognition models — argparse adapter
# ---------------------------------------------------------------------------


def resolve_ocr_models(args) -> tuple[Path, Path]:
    """Return ``(det_path, reco_path)`` from argparse-shaped CLI args.

    Validates the partial-input case (one of ``--detection``/``--recognition``
    set without the other) before delegating to
    :func:`pd_book_tools.hf.resolve_ocr_models`.
    """
    if bool(args.detection) != bool(args.recognition):
        which = "--detection" if args.detection else "--recognition"
        print(
            f"ERROR: {which} requires its counterpart. Provide both --detection and --recognition.",
            file=sys.stderr,
        )
        sys.exit(1)

    det = Path(args.detection) if args.detection else None
    reco = Path(args.recognition) if args.recognition else None

    try:
        return _resolve_ocr_models_kwargs(
            repo=args.hf_repo,
            revision=args.model_version,
            det_filename=args.det_filename,
            reco_filename=args.reco_filename,
            detection_path=det,
            recognition_path=reco,
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


def det_source_descriptor(args, det_path: Path) -> str:
    """Human-readable source string for the detection model."""
    if args.detection:
        return str(det_path)
    return f"{args.hf_repo}/{args.det_filename}@{short_revision(args.model_version)}"


def reco_source_descriptor(args, reco_path: Path) -> str:
    """Human-readable source string for the recognition model."""
    if args.recognition:
        return str(reco_path)
    return f"{args.hf_repo}/{args.reco_filename}@{short_revision(args.model_version)}"


# ---------------------------------------------------------------------------
# Layout model — argparse adapter
# ---------------------------------------------------------------------------


def resolve_layout_source(args) -> tuple[str | None, str | None, str]:
    """Return ``(repo, revision, descriptor)`` from argparse-shaped args."""
    return _resolve_layout_source_kwargs(args.layout_model, args.layout_checkpoint)
