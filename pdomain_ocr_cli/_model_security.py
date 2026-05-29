from __future__ import annotations

from typing import Protocol

from pdomain_ocr_cli._hf_models import DEFAULT_HF_REPO


class ModelSecurityArgs(Protocol):
    hf_repo: str
    model_version: str | None
    detection: str | None
    recognition: str | None
    layout_checkpoint: str | None


def model_security_warnings(args: ModelSecurityArgs) -> tuple[str, ...]:
    warnings: list[str] = []
    uses_local_ocr_checkpoints = bool(args.detection or args.recognition)
    if (
        args.hf_repo == DEFAULT_HF_REPO
        and args.model_version is None
        and not uses_local_ocr_checkpoints
    ):
        warnings.append(
            "warning: using mutable latest OCR model revision; for reproducible and safer runs, "
            + "pass --model-version pinned to a trusted tag or commit."
        )
    if args.hf_repo != DEFAULT_HF_REPO:
        warnings.append(
            "warning: custom Hugging Face OCR repo is a model trust boundary; only use repos you "
            + "trust because PyTorch checkpoint loading can execute code."
        )
    if uses_local_ocr_checkpoints:
        warnings.append(
            "warning: local PyTorch checkpoint paths are trusted executable inputs; only pass "
            + ".pt files from trusted sources."
        )
    if args.layout_checkpoint:
        warnings.append(
            "warning: layout checkpoint is a model trust boundary; only use trusted local paths "
            + "or Hugging Face repos."
        )
    return tuple(warnings)
