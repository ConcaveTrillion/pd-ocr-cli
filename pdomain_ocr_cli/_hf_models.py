"""Argparse-shaped adapters around :mod:`pdomain_book_tools.hf`.

The canonical model-resolution primitives live in ``pdomain_book_tools.hf`` so
pdomain-ocr-cli, pdomain-ocr-labeler, and pdomain-prep-for-pgdp share them. This module keeps
only the argparse-flavoured wrappers that the CLI's ``ocr_to_txt`` driver
needs — the kwargs-shaped functions in ``pdomain_book_tools.hf`` are the right
target for non-CLI callers.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Protocol, cast


class _HfArgs(Protocol):
    detection: str | None
    recognition: str | None
    hf_repo: str
    model_version: str | None
    det_filename: str
    reco_filename: str
    layout_model: str
    layout_checkpoint: str | None


class _PdBookToolsHfModule(Protocol):
    DEFAULT_DET_FILENAME: str
    DEFAULT_HF_REPO: str
    DEFAULT_RECO_FILENAME: str
    LAYOUT_MODEL_FILES: tuple[str, ...]
    OCR_MODEL_SIDECARS: tuple[str, ...]

    def hf_download(self, *args: object, **kwargs: object) -> object: ...

    def prefetch_layout_files(self, *args: object, **kwargs: object) -> object: ...

    def resolve_layout_source(
        self, layout_model: str, layout_checkpoint: str | None = None
    ) -> tuple[str | None, str | None, str]: ...

    def resolve_ocr_models(
        self,
        *,
        repo: str = "pdomain/pdomain-ocr-models",
        revision: str | None = None,
        det_filename: str = "detection/pdomain-all-detection-model-finetuned.pt",
        reco_filename: str = "recognition/pdomain-all-recognition-model-finetuned.pt",
        detection_path: Path | None = None,
        recognition_path: Path | None = None,
    ) -> tuple[Path, Path]: ...

    def short_revision(self, rev: str | None) -> str: ...

    def silence_transformers_load_chatter(self, *args: object, **kwargs: object) -> object: ...

    def suppress_hf_unauth_warning(self, *args: object, **kwargs: object) -> object: ...


_HF = cast("_PdBookToolsHfModule", cast("object", importlib.import_module("pdomain_book_tools.hf")))

DEFAULT_DET_FILENAME = _HF.DEFAULT_DET_FILENAME
DEFAULT_HF_REPO = _HF.DEFAULT_HF_REPO
DEFAULT_RECO_FILENAME = _HF.DEFAULT_RECO_FILENAME
LAYOUT_MODEL_FILES = _HF.LAYOUT_MODEL_FILES
OCR_MODEL_SIDECARS = _HF.OCR_MODEL_SIDECARS
hf_download = _HF.hf_download
prefetch_layout_files = _HF.prefetch_layout_files
short_revision = _HF.short_revision
silence_transformers_load_chatter = _HF.silence_transformers_load_chatter
suppress_hf_unauth_warning = _HF.suppress_hf_unauth_warning
_resolve_layout_source_kwargs = _HF.resolve_layout_source
_resolve_ocr_models_kwargs = _HF.resolve_ocr_models

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


def resolve_ocr_models(args: _HfArgs) -> tuple[Path, Path]:
    """Return ``(det_path, reco_path)`` from argparse-shaped CLI args.

    Validates the partial-input case (one of ``--detection``/``--recognition``
    set without the other) before delegating to
    :func:`pdomain_book_tools.hf.resolve_ocr_models`.
    """
    if bool(args.detection) != bool(args.recognition):
        which = "--detection" if args.detection else "--recognition"
        print(  # noqa: T201  # CLI output
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
        print(f"ERROR: {exc}", file=sys.stderr)  # noqa: T201  # CLI output
        sys.exit(1)


def det_source_descriptor(args: _HfArgs, det_path: Path) -> str:
    """Human-readable source string for the detection model."""
    if args.detection:
        return str(det_path)
    return f"{args.hf_repo}/{args.det_filename}@{short_revision(args.model_version)}"


def reco_source_descriptor(args: _HfArgs, reco_path: Path) -> str:
    """Human-readable source string for the recognition model."""
    if args.recognition:
        return str(reco_path)
    return f"{args.hf_repo}/{args.reco_filename}@{short_revision(args.model_version)}"


# ---------------------------------------------------------------------------
# Layout model — argparse adapter
# ---------------------------------------------------------------------------


def resolve_layout_source(args: _HfArgs) -> tuple[str | None, str | None, str]:
    """Return ``(repo, revision, descriptor)`` from argparse-shaped args."""
    return _resolve_layout_source_kwargs(args.layout_model, args.layout_checkpoint)
