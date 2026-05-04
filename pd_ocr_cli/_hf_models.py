"""Model resolution / prefetch helpers — OCR (detection + recognition) and
layout. Both kinds share the same primitive (:func:`hf_download` from
:mod:`pd_ocr_cli._hf_download`); this module is the orchestration layer
that knows the OCR and layout repo conventions.
"""

import sys
from pathlib import Path

from pd_ocr_cli._hf_download import hf_download

DEFAULT_HF_REPO = "CT2534/pd-ocr-models"
DEFAULT_DET_FILENAME = "detection/pd-all-detection-model-finetuned.pt"
DEFAULT_RECO_FILENAME = "recognition/pd-all-recognition-model-finetuned.pt"

# Sidecars the trainer writes alongside each OCR ``.pt`` checkpoint
# (architecture name + vocab string). pd-book-tools prefers these over
# heuristic detection when present, so always try to fetch them with the
# main OCR weights. Layout files don't carry sidecars.
OCR_MODEL_SIDECARS = (".arch", ".vocab")

# HF transformers files needed for an RT-DETR layout model. Pre-fetching
# all three guarantees the later ``from_pretrained()`` call inside the
# adapter is a cache hit.
LAYOUT_MODEL_FILES = ("config.json", "preprocessor_config.json", "model.safetensors")


def short_revision(rev: str | None) -> str:
    """Compact revision string for display (8-char prefix or 'latest')."""
    if not rev:
        return "latest"
    return rev[:8] if len(rev) > 8 else rev


# ---------------------------------------------------------------------------
# OCR detection + recognition models
# ---------------------------------------------------------------------------


def resolve_ocr_models(args) -> tuple[Path, Path]:
    """Return (det_path, reco_path) from either local args or HF Hub."""
    if bool(args.detection) != bool(args.recognition):
        which = "--detection" if args.detection else "--recognition"
        print(
            f"ERROR: {which} requires its counterpart. Provide both --detection and --recognition.",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.detection and args.recognition:
        det_path = Path(args.detection)
        reco_path = Path(args.recognition)
        if not det_path.is_file():
            print(f"ERROR: detection model not found: {det_path}", file=sys.stderr)
            sys.exit(1)
        if not reco_path.is_file():
            print(f"ERROR: recognition model not found: {reco_path}", file=sys.stderr)
            sys.exit(1)
        return det_path, reco_path

    det_path = hf_download(
        args.hf_repo, args.det_filename, args.model_version, sidecars=OCR_MODEL_SIDECARS
    )
    reco_path = hf_download(
        args.hf_repo, args.reco_filename, args.model_version, sidecars=OCR_MODEL_SIDECARS
    )
    return det_path, reco_path


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
# Layout model
# ---------------------------------------------------------------------------


def resolve_layout_source(args) -> tuple[str | None, str | None, str]:
    """Return (repo, revision, descriptor) for the configured layout model.

    repo/revision are None for backends that don't pull from HF Hub
    (``none``, ``contour``, local checkpoint path). The descriptor is a
    human-readable string for the loaded-line.
    """
    if args.layout_model == "none":
        return (None, None, "")
    if args.layout_model == "contour":
        return (None, None, "contour (built-in)")
    # pp-doclayout-plus-l
    if args.layout_checkpoint:
        ckpt = Path(args.layout_checkpoint)
        if ckpt.exists():
            return (None, None, str(ckpt))
        return (args.layout_checkpoint, None, f"{args.layout_checkpoint}@latest")
    from pd_book_tools.layout.adapters.pp_doclayout import PPDocLayoutPlusLDetector

    repo = PPDocLayoutPlusLDetector.HF_REPO
    revision = PPDocLayoutPlusLDetector.HF_REVISION
    return (repo, revision, f"{repo}@{short_revision(revision)}")


def prefetch_layout_files(repo: str, revision: str | None) -> None:
    """Pre-download the HF transformers files for the layout model.

    Ensures the later ``from_pretrained()`` call inside the adapter is a
    cache hit, so the only progress bar the user sees during this phase
    is the friendly per-file HF Hub download bar (with size + ETA), not
    transformers' in-memory weight-loading bar.
    """
    for fname in LAYOUT_MODEL_FILES:
        hf_download(repo, fname, revision)


def silence_transformers_load_chatter() -> None:
    """Disable transformers' verbose logging + in-memory weight progress bar."""
    try:
        from transformers.utils import logging as _hf_logging

        _hf_logging.set_verbosity_error()
        _hf_logging.disable_progress_bar()
    except Exception:
        pass  # transformers not installed yet, or older version
