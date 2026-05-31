"""CLI: OCR images to .txt using fine-tuned DocTR detection + recognition models.

Usage
-----
Install and run (models download automatically):
    uv tool install git+https://github.com/pdomain/pdomain-ocr-cli
    pdomain-ocr page.png

Run directly without installing:
    uvx --from git+https://github.com/pdomain/pdomain-ocr-cli pdomain-ocr page.png

Multiple images:
    pdomain-ocr page1.png page2.png page3.png

Process a whole directory:
    pdomain-ocr images/

Process a directory tree recursively:
    pdomain-ocr --recursive images/ -o output/

Write output to a specific directory (mirrors input structure for directories):
    pdomain-ocr -o output/ page.png

Also save the reorganized OCR document as JSON alongside the .txt:
    pdomain-ocr --save-json page.png

Options
-------
--model-version TAG          Pin to a specific model version/tag.
--hf-repo REPO_ID            Use a different Hugging Face repo.
--detection / --recognition  Use local .pt files instead of downloading.
--recursive / -r / -R        Recurse into subdirectories.
--straight-quotes            Convert curly quotes to straight ASCII quotes.
--em-dash-to-double-hyphen   Convert em dash to double hyphen (--).
--no-update-check            Skip the background GitHub-tag upgrade-notice request.
                             Also: PD_OCR_NO_UPDATE_CHECK=1 env var.
--no-reorg                   Skip Page.reorganize_page() (raw OCR output).
--save-reorganize-diagnostics
                             With --save-json: also write the pure-OCR and
                             post-noise-removal snapshots as JSON + TXT
                             siblings (six files total per page when
                             combined with --save-json). Old alias:
                             --save-pre-reorg-json.
--validate-reorg             Warn if reorganize_page drops any OCR words.
--experimental-drop-layout-words / --edl
                             [experimental] Enable drop of figure-
                             internal OCR words during reorganize:
                             lines fully inside detected figure regions
                             with no body-text overlap (Step Layout-2b),
                             and figure-internal heuristic noise
                             (Step B2). Default OFF: all OCR words are
                             preserved. Footnote/header/footer/abandoned
                             regions are NEVER dropped, regardless of
                             this flag.
--layout-model {none,contour,pp-doclayout-plus-l}
                             Layout detector backend (default pp-doclayout-plus-l).
--layout-checkpoint PATH     Fine-tuned PP-DocLayout checkpoint (path or HF repo).
--layout-confidence THRESH   Region confidence threshold (default 0.5).
--extract-illustrations      Crop figure/decoration/table regions to i_<stem>_<n>.jpg.
--no-illustration-placeholders
                             Suppress empty figure/decoration/table placeholder
                             blocks in the reorganized output (caption text is
                             still preserved). No effect with --no-reorg.
--layout-debug[-dir]         Write layout debug text alongside outputs.

Downloaded models are cached in ~/.cache/huggingface/hub and reused on
subsequent runs.
"""

import argparse
import importlib
import math
import shutil as _shutil
import subprocess as _subprocess
import sys
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

from pdomain_ocr_cli import _startup_notices
from pdomain_ocr_cli._artifacts import (
    atomic_write_bytes,
    atomic_write_json_document,
    atomic_write_text,
)
from pdomain_ocr_cli._batch_plan import (
    BatchPlanError,
    build_batch_plan,
    positive_int,
)
from pdomain_ocr_cli._batch_plan import (
    collect_images as _collect_images,
)
from pdomain_ocr_cli._hf_models import (
    DEFAULT_DET_FILENAME,
    DEFAULT_HF_REPO,
    DEFAULT_RECO_FILENAME,
    det_source_descriptor,
    prefetch_layout_files,
    reco_source_descriptor,
    resolve_layout_source,
    resolve_ocr_models,
    silence_transformers_load_chatter,
)
from pdomain_ocr_cli._model_security import model_security_warnings
from pdomain_ocr_cli._pipeline import (
    apply_text_normalizations,
    clear_layout_debug_env,
    diagnostic_output_paths,
    format_drops_warning,
    format_noise_drop_warning,
    illustration_crop_path,
    iter_crop_regions,
    setup_layout_debug_env,
    validate_extract_illustrations,
    write_diagnostic_snapshots,
)
from pdomain_ocr_cli._policy import build_run_policy
from pdomain_ocr_cli._runtime import BatchRuntimeError, DefaultRuntimeSession, RuntimeSession
from pdomain_ocr_cli._update_check import VERSION as _VERSION
from pdomain_ocr_cli._update_check import check_for_update as _check_for_update

# Compatibility patch points for existing GPU-nudge tests and downstream users.
shutil = _shutil
subprocess = _subprocess

if TYPE_CHECKING:
    from pdomain_ocr_cli._batch_plan import PageJob


@dataclass
class _CliArgs:
    detection: str | None
    recognition: str | None
    hf_repo: str
    model_version: str | None
    det_filename: str
    reco_filename: str
    output_dir: str | None
    save_json: bool
    no_reorg: bool
    save_reorganize_diagnostics: bool
    validate_reorg: bool
    experimental_drop_layout_words: bool
    recursive: bool
    straight_quotes: bool
    em_dash_to_double_hyphen: bool
    extract_illustrations: bool
    no_illustration_placeholders: bool
    layout_debug: bool
    layout_debug_dir: str | None
    layout_model: str
    layout_checkpoint: str | None
    layout_confidence: float
    no_update_check: bool
    batch_pages: int
    inputs: list[str]


class _RegionLike(Protocol):
    L: int
    R: int
    T: int
    B: int
    type: object
    confidence: float


class _PageLayoutLike(Protocol):
    regions: Sequence[_RegionLike]
    inference_ms: int | float


class _LayoutDetectorLike(Protocol):
    def detect(self, img_path: Path) -> _PageLayoutLike: ...


class _PageLike(Protocol):
    text: str | None
    words: Sequence[object]
    diagnostic_pure_ocr: object
    diagnostic_post_noise_removal: object

    def reorganize_page(
        self,
        *,
        layout: _PageLayoutLike | None = ...,
        drop_layout_words: bool = ...,
        emit_illustration_placeholders: bool = ...,
    ) -> None: ...


class _Cv2ImageLike(Protocol):
    size: int

    def __getitem__(self, key: tuple[slice, slice]) -> "_Cv2ImageLike": ...


class _BytesConvertible(Protocol):
    def __bytes__(self) -> bytes: ...


class _Cv2Like(Protocol):
    def imread(self, path: str) -> _Cv2ImageLike | None: ...

    def imencode(self, ext: str, image: _Cv2ImageLike) -> tuple[bool, _BytesConvertible]: ...


_ValidateWordPreservation = Callable[[list[object], list[object]], list[str]]


class _FormatsModuleLike(Protocol):
    is_image_file: Callable[[Path], bool]


class _DoctrSupportModuleLike(Protocol):
    get_finetuned_torch_doctr_predictor: Callable[[Path, Path], object]


class _LayoutModuleLike(Protocol):
    get_detector: Callable[..., _LayoutDetectorLike]


class _ReorganizeUtilsModuleLike(Protocol):
    validate_word_preservation: _ValidateWordPreservation


class _RegionTypeLike(Protocol):
    figure: object
    decoration: object
    table: object


class _LayoutTypesModuleLike(Protocol):
    RegionType: _RegionTypeLike


class _DocumentModuleLike(Protocol):
    Document: object


class _DocumentClassLike(Protocol):
    from_image_ocr_via_doctr: Callable[..., object]


class _SinglePageDoc:
    """Minimal document wrapper around a single ``Page``.

    Provides the same ``to_json_file`` surface as ``Document`` so the
    per-page JSON-sidecar write path can remain unchanged after the
    migration to batch OCR.  The emitted JSON has the same envelope shape
    as ``Document.to_dict()`` / ``Document.to_json_file()``.
    """

    _page: object
    _source_identifier: str
    _source_path: Path | None

    def __init__(
        self, page: object, *, source_identifier: str = "", source_path: Path | None = None
    ) -> None:
        self._page = page
        self._source_identifier = source_identifier
        self._source_path = source_path

    def to_json_file(self, file_path: "str | Path") -> None:
        """Write a document-envelope JSON identical to ``Document.to_json_file``."""
        import json as _json

        def _empty_dict() -> dict[str, object]:
            return {}

        page_dict = cast("Callable[[], object]", getattr(self._page, "to_dict", _empty_dict))()
        envelope = {
            "source_lib": "pdomain_book_tools",
            "source_identifier": self._source_identifier,
            "source_path": str(self._source_path) if self._source_path is not None else None,
            "pages": [page_dict],
        }
        with open(file_path, "w", encoding="utf-8") as f:
            _json.dump(envelope, f, ensure_ascii=False, indent=2)


def _load_is_image_file() -> Callable[[Path], bool]:
    module = cast(
        "_FormatsModuleLike",
        cast("object", importlib.import_module("pdomain_book_tools.image_processing.formats")),
    )
    return module.is_image_file


_IS_IMAGE_FILE = _load_is_image_file()


def _coerce_cli_args(args: argparse.Namespace) -> _CliArgs:
    return _CliArgs(
        detection=cast("str | None", args.detection),
        recognition=cast("str | None", args.recognition),
        hf_repo=cast("str", args.hf_repo),
        model_version=cast("str | None", args.model_version),
        det_filename=cast("str", args.det_filename),
        reco_filename=cast("str", args.reco_filename),
        output_dir=cast("str | None", args.output_dir),
        save_json=cast("bool", args.save_json),
        no_reorg=cast("bool", args.no_reorg),
        save_reorganize_diagnostics=cast("bool", args.save_reorganize_diagnostics),
        validate_reorg=cast("bool", args.validate_reorg),
        experimental_drop_layout_words=cast("bool", args.experimental_drop_layout_words),
        recursive=cast("bool", args.recursive),
        straight_quotes=cast("bool", args.straight_quotes),
        em_dash_to_double_hyphen=cast("bool", args.em_dash_to_double_hyphen),
        extract_illustrations=cast("bool", args.extract_illustrations),
        no_illustration_placeholders=cast("bool", args.no_illustration_placeholders),
        layout_debug=cast("bool", args.layout_debug),
        layout_debug_dir=cast("str | None", args.layout_debug_dir),
        layout_model=cast("str", args.layout_model),
        layout_checkpoint=cast("str | None", args.layout_checkpoint),
        layout_confidence=cast("float", args.layout_confidence),
        no_update_check=cast("bool", args.no_update_check),
        batch_pages=cast("int", args.batch_pages),
        inputs=cast("list[str]", args.inputs),
    )


def _detect_torch_device() -> str:
    """Pick the best available torch device for the layout model."""
    try:
        import torch
    except ImportError:
        return "cpu"

    cuda = getattr(torch, "cuda", None)
    cuda_is_available = getattr(cuda, "is_available", None)
    if callable(cuda_is_available) and cast("Callable[[], bool]", cuda_is_available)():
        return "cuda"

    backends = getattr(torch, "backends", None)
    mps = getattr(backends, "mps", None)
    mps_is_available = getattr(mps, "is_available", None)
    if callable(mps_is_available) and cast("Callable[[], bool]", mps_is_available)():
        return "mps"
    return "cpu"


# ---------------------------------------------------------------------------
# Lazy-import indirection — the only purpose of these tiny wrappers is to
# give tests a single attribute to ``monkeypatch`` so ``main()`` can run end
# to end without loading torch / DocTR / pdomain_book_tools / cv2.
# ---------------------------------------------------------------------------


def _load_predictor(det_path: Path, reco_path: Path) -> object:
    """Import doctr support and build the fine-tuned predictor."""
    module = cast(
        "_DoctrSupportModuleLike",
        cast("object", importlib.import_module("pdomain_book_tools.ocr.doctr_support")),
    )
    return module.get_finetuned_torch_doctr_predictor(det_path, reco_path)


def _load_layout_detector(args: _CliArgs, device: str) -> _LayoutDetectorLike:
    """Import the layout module and instantiate the configured detector."""
    _ = silence_transformers_load_chatter()
    module = cast(
        "_LayoutModuleLike", cast("object", importlib.import_module("pdomain_book_tools.layout"))
    )

    return module.get_detector(
        args.layout_model,
        device=device,
        confidence=args.layout_confidence,
        checkpoint_path=args.layout_checkpoint,
    )


def _load_validate_word_preservation() -> _ValidateWordPreservation:
    """Return the ``validate_word_preservation`` reorganize-checker."""
    module = cast(
        "_ReorganizeUtilsModuleLike",
        cast("object", importlib.import_module("pdomain_book_tools.ocr.reorganize_page_utils")),
    )
    return module.validate_word_preservation


def _load_illustration_deps() -> tuple[_Cv2Like, set[object]]:
    """Return ``(cv2_module, crop_types_set)`` used during illustration cropping."""
    cv2_module = cast("_Cv2Like", cast("object", importlib.import_module("cv2")))
    types_module = cast(
        "_LayoutTypesModuleLike",
        cast("object", importlib.import_module("pdomain_book_tools.layout.types")),
    )
    region_type = types_module.RegionType
    figure = region_type.figure
    decoration = region_type.decoration
    table = region_type.table
    return cv2_module, {figure, decoration, table}


def _pick_device() -> str:
    """Return the hardware device string via ``pdomain_ops.gpu.device.pick_device``."""
    module = cast(
        "object",
        importlib.import_module("pdomain_ops.gpu.device"),
    )
    fn = cast("Callable[[], str]", module.pick_device)  # pyright: ignore[reportAttributeAccessIssue]  # module loaded via importlib; attrs not visible to type checker
    return fn()


def _run_doctr_batch(
    images: list[object],
    *,
    predictor: object,
    device: str,
    build_smaller: "Callable[[int, int], object] | None" = None,
    source_identifiers: "list[str] | None" = None,
) -> "list[_PageLike | None]":
    """Delegate to ``pdomain_ops.gpu.doctr_batch.run_doctr_batch``.

    This thin wrapper is the monkeypatch seam for unit tests: tests replace
    ``_run_doctr_batch`` without needing to touch the ops library.
    """
    module = cast(
        "object",
        importlib.import_module("pdomain_ops.gpu.doctr_batch"),
    )
    fn = cast(
        "Callable[..., list[_PageLike | None]]",
        module.run_doctr_batch,  # pyright: ignore[reportAttributeAccessIssue]  # module loaded via importlib; attrs not visible to type checker
    )
    try:
        return fn(
            images,
            predictor=predictor,
            device=device,
            build_smaller=build_smaller,
            source_identifiers=source_identifiers,
        )
    except AttributeError as exc:
        if "from_images_ocr_via_doctr" not in str(exc):
            raise
        return _run_doctr_batch_single_image_compat(
            images,
            predictor=predictor,
            source_identifiers=source_identifiers,
        )


def _run_doctr_batch_single_image_compat(
    images: Sequence[object],
    *,
    predictor: object,
    source_identifiers: Sequence[str] | None,
) -> list[_PageLike | None]:
    """Fallback for older pdomain-book-tools without the batch OCR entry point."""
    if source_identifiers is None:
        identifiers = [str(i) for i in range(len(images))]
    else:
        identifiers = list(source_identifiers)
        if len(identifiers) != len(images):
            raise ValueError(
                f"source_identifiers length ({len(identifiers)}) must match images length ({len(images)})"
            )

    module = cast(
        "_DocumentModuleLike",
        cast("object", importlib.import_module("pdomain_book_tools.ocr.document")),
    )
    document = cast(
        "_DocumentClassLike",
        module.Document,
    )
    from_image = document.from_image_ocr_via_doctr

    pages: list[_PageLike | None] = []
    for image, source_identifier in zip(images, identifiers, strict=True):
        doc = from_image(
            image,
            source_identifier=source_identifier,
            predictor=predictor,
        )
        doc_pages = cast("Sequence[_PageLike]", getattr(doc, "pages", ()))
        pages.append(doc_pages[0] if doc_pages else None)
    return pages


def _create_runtime_session(det_path: Path, reco_path: Path) -> RuntimeSession[_PageLike]:
    predictor = _load_predictor(det_path, reco_path)
    if predictor is None:
        raise RuntimeError("failed to load models.")
    return DefaultRuntimeSession(
        predictor=predictor,
        device=_pick_device(),
        runner=_run_doctr_batch,
    )


def _start_update_check_thread(disabled: bool) -> threading.Thread | None:
    """Spawn the background GitHub-tag check unless suppressed."""
    return _startup_notices.start_update_check_thread(
        disabled=disabled,
        check_for_update=_check_for_update,
    )


def _env_truthy(name: str) -> bool:
    """True if the env var is set to a truthy value (1/true/yes/on, case-insensitive)."""
    return _startup_notices.env_truthy(name)


# ---------------------------------------------------------------------------
# GPU-availability nudge
# ---------------------------------------------------------------------------
# Process-cached so a test or a caller invoking ``main()`` repeatedly never
# re-runs the (potentially) blocking ``nvidia-smi`` subprocess. The cache
# is busted across processes (CLI restart) — that's the right granularity
# because hardware doesn't change mid-run.
_GPU_NUDGE_CACHE = _startup_notices.GPU_NUDGE_CACHE


def _should_nudge_gpu_install() -> bool:
    """Return True if a one-line "GPU available, but installed CPU-only" nudge should fire.

    Logic:
    1. ``PD_OCR_NO_GPU_NUDGE=1`` short-circuits to False (user opt-out).
    2. If ``cupy`` imports cleanly, the GPU stack is already wired up — no nudge.
    3. Otherwise, check whether ``nvidia-smi`` exists AND exits 0 within 2s.
       If yes, the host has a GPU but pdomain-ocr was installed CPU-only → nudge.
    4. Any unexpected error in the probe path swallows silently and returns
       False — a printing-helper bug must never break ``pdomain-ocr`` itself.

    The result is cached for the life of the process (see ``_GPU_NUDGE_CACHE``)
    so that callers invoking ``main()`` more than once (e.g. in a test loop)
    do not re-spawn ``nvidia-smi``.
    """
    return _startup_notices.should_nudge_gpu_install(cache=_GPU_NUDGE_CACHE)


def _maybe_print_gpu_nudge() -> None:
    """Print the one-line GPU-install nudge to stderr when applicable.

    Wraps ``_should_nudge_gpu_install`` so the print site is also
    bullet-proof against unexpected errors (it never raises).
    """
    _startup_notices.maybe_print_gpu_nudge(should_nudge=_should_nudge_gpu_install)


def _confidence_threshold(s: str) -> float:
    """Argparse type for --layout-confidence: finite float in [0.0, 1.0].

    Plain ``type=float`` happily accepts ``nan``, ``inf``, ``-inf``,
    negatives, and values >1. ``nan`` silently disables the crop
    filter (every ``x < nan`` is False, so every region passes);
    ``inf`` / out-of-range values silently produce zero crops. Reject
    these at the CLI boundary with a clear message rather than letting
    them propagate into the layout backend. (B21)
    """
    try:
        v = float(s)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"--layout-confidence must be a finite number in [0, 1]; got {s!r}"
        ) from exc
    if not math.isfinite(v) or not 0.0 <= v <= 1.0:
        raise argparse.ArgumentTypeError(
            f"--layout-confidence must be a finite number in [0, 1]; got {s!r}"
        )
    return v


def _positive_batch_pages(s: str) -> int:
    try:
        return positive_int(s)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def parse_args() -> argparse.Namespace:
    """Parse and return the CLI arguments for ``pdomain-ocr``."""
    p = argparse.ArgumentParser(
        description="OCR images to .txt using fine-tuned detection + recognition models."
    )
    _ = p.add_argument("--version", action="version", version=f"%(prog)s {_VERSION}")

    src = p.add_argument_group("model source (use --hf-repo OR --detection/--recognition)")
    _ = src.add_argument(
        "--hf-repo",
        metavar="REPO_ID",
        default=DEFAULT_HF_REPO,
        help=f"Hugging Face repo to download models from (default: {DEFAULT_HF_REPO}).",
    )
    _ = src.add_argument(
        "--model-version",
        metavar="TAG",
        default=None,
        help="HF repo revision/tag to use (default: latest). Requires --hf-repo.",
    )
    _ = src.add_argument(
        "--det-filename",
        metavar="PATH",
        default=DEFAULT_DET_FILENAME,
        help=f"Filename within the HF repo for the detection model (default: {DEFAULT_DET_FILENAME}).",
    )
    _ = src.add_argument(
        "--reco-filename",
        metavar="PATH",
        default=DEFAULT_RECO_FILENAME,
        help=f"Filename within the HF repo for the recognition model (default: {DEFAULT_RECO_FILENAME}).",
    )
    _ = src.add_argument(
        "--detection",
        "-d",
        metavar="PT_FILE",
        default=None,
        help="Path to a local detection .pt model file.",
    )
    _ = src.add_argument(
        "--recognition",
        "-g",
        metavar="PT_FILE",
        default=None,
        help="Path to a local recognition .pt model file.",
    )

    _ = p.add_argument(
        "--output-dir",
        "-o",
        metavar="DIR",
        default=None,
        help="Directory to write .txt files into (default: same directory as each image).",
    )
    _ = p.add_argument(
        "--save-json",
        action="store_true",
        default=False,
        help="Also save the reorganized OCR document as a .json file alongside the .txt.",
    )
    _ = p.add_argument(
        "--no-reorg",
        action="store_true",
        default=False,
        help=(
            "Skip Page.reorganize_page(). Emits raw OCR output (the .txt and "
            ".json reflect the OCR engine's structure with no header/footer "
            "extraction, column splitting, or paragraph reordering)."
        ),
    )
    _ = p.add_argument(
        "--save-reorganize-diagnostics",
        "--save-pre-reorg-json",
        dest="save_reorganize_diagnostics",
        action="store_true",
        default=False,
        help=(
            "When --save-json is set and reorganize is enabled, also write "
            "the full diagnostic bundle alongside the regular .txt / .json: "
            "<image>.pure-ocr.json + <image>.pure-ocr.txt (literal OCR "
            "output before any pipeline mutation), and "
            "<image>.post-noise.json + <image>.post-noise.txt (state after "
            "figure-noise removal but before reorg-proper). Useful for "
            "auditing what the reorganize step preserved, dropped, or "
            "rearranged. The old name --save-pre-reorg-json is accepted "
            "as a backward-compatible alias."
        ),
    )
    _ = p.add_argument(
        "--validate-reorg",
        action="store_true",
        default=False,
        help=(
            "After reorganize_page(), assert that every OCR word present "
            "before reorganize is still present after (by text + bbox). "
            "Mismatches print a WARNING; the .txt/.json are still written."
        ),
    )
    _ = p.add_argument(
        "--experimental-drop-layout-words",
        "--edl",
        action="store_true",
        default=False,
        help=(
            "[experimental] Enable drop of figure-internal OCR words "
            "during reorganize: lines fully inside detected figure "
            "regions with no body-text overlap (Step Layout-2b), and "
            "figure-internal heuristic noise (Step B2). Default is "
            "OFF: all OCR words are preserved. Note: footnote / "
            "header / footer / abandoned regions are NEVER dropped, "
            "regardless of this flag — only figure-internal drops "
            "are opt-in. Short alias: --edl."
        ),
    )
    _ = p.add_argument(
        "--recursive",
        "-r",
        "-R",
        action="store_true",
        default=False,
        help="Recurse into subdirectories when a directory is given as input.",
    )
    _ = p.add_argument(
        "--straight-quotes",
        "-sq",
        action="store_true",
        default=False,
        help="Convert curly quotes in OCR text output to straight ASCII quotes.",
    )
    _ = p.add_argument(
        "--em-dash-to-double-hyphen",
        "-ed",
        action="store_true",
        default=False,
        help="Convert em dash in OCR text output to double hyphen (--).",
    )
    _ = p.add_argument(
        "--no-update-check",
        action="store_true",
        default=False,
        help=(
            "Skip the background GitHub-tag check that prints an upgrade "
            "notice when a newer release is available. Use to avoid the "
            "outbound api.github.com request entirely (e.g. offline runs). "
            "Can also be set via the PD_OCR_NO_UPDATE_CHECK=1 env var."
        ),
    )
    _ = p.add_argument(
        "--batch-pages",
        type=_positive_batch_pages,
        default=4,
        metavar="N",
        help=(
            "Number of pages to send to the OCR engine in a single batch call. "
            "Higher values improve GPU throughput; lower values reduce peak VRAM "
            "usage. OOM is handled automatically via backoff in pdomain-ops. "
            "Must be >= 1. Default: 4."
        ),
    )
    _ = p.add_argument(
        "--layout-model",
        default="pp-doclayout-plus-l",
        choices=["none", "contour", "pp-doclayout-plus-l"],
        help=(
            "Layout-detector backend. Layout detection always runs (its "
            "output is fed into Page.reorganize_page() as a hint so captions "
            "get wrapped, high-confidence headers/footers get role-labeled "
            "and woven into the page boundaries (not dropped), and "
            "tables/figures get tagged). Pass `--layout-model none` to "
            "skip layout detection. Default: pp-doclayout-plus-l."
        ),
    )
    _ = p.add_argument(
        "--layout-checkpoint",
        default=None,
        metavar="PATH_OR_REPO",
        help=(
            "Path or HF repo for a fine-tuned layout checkpoint. Overrides "
            "the default PP-DocLayout_plus-L weights."
        ),
    )
    _ = p.add_argument(
        "--layout-confidence",
        type=_confidence_threshold,
        default=0.5,
        metavar="THRESHOLD",
        help="Confidence threshold for layout detections (0..1). Default 0.5.",
    )
    _ = p.add_argument(
        "--extract-illustrations",
        action="store_true",
        default=False,
        help=(
            "Write i_<stem>_<n>.jpg crops for figure / decoration / table "
            "regions alongside the .txt. Requires a layout model "
            "(error if combined with --layout-model none)."
        ),
    )
    _ = p.add_argument(
        "--no-illustration-placeholders",
        action="store_true",
        default=False,
        help=(
            "Suppress the empty placeholder block that each high-confidence "
            "figure / decoration / table region otherwise contributes to the "
            "reorganized output (a stray blank paragraph in the .txt; an "
            "[Illustration: ...] wrapper downstream). Caption text is NOT "
            "dropped — caption words are preserved alongside the surrounding "
            "body text. Default OFF: placeholders are emitted so "
            "pdomain-prep-for-pgdp can anchor [Illustration: ...] serialisation. "
            "Has no effect with --no-reorg."
        ),
    )
    _ = p.add_argument(
        "--layout-debug",
        action="store_true",
        default=False,
        help=(
            "Write step-by-step layout debug text files (X-axis 3-group lines, "
            "squeezed side-flow diagnostics)."
        ),
    )
    _ = p.add_argument(
        "--layout-debug-dir",
        metavar="DIR",
        default=None,
        help=(
            "Directory for layout debug text files. "
            "Defaults to each image output directory when --layout-debug is enabled."
        ),
    )
    _ = p.add_argument(
        "inputs",
        nargs="+",
        metavar="IMAGE_OR_DIR",
        help="One or more image files or directories to process.",
    )
    return p.parse_args()


def collect_images(inputs: list[str], recursive: bool) -> list[Path]:
    """Expand files and directories into deduplicated image paths."""
    return _collect_images(inputs, recursive, is_image_file=_IS_IMAGE_FILE)


def main() -> None:
    """Entry point for the ``pdomain-ocr`` CLI command."""
    raw_args = parse_args()
    args = _coerce_cli_args(raw_args)

    validate_extract_illustrations(args)
    policy = build_run_policy(args)
    for warning in policy.warnings:
        print(warning, file=sys.stderr)  # noqa: T201  # CLI output
    for warning in model_security_warnings(args):
        print(warning, file=sys.stderr)  # noqa: T201  # CLI output

    output_dir = Path(args.output_dir) if args.output_dir else None
    try:
        batch_plan = build_batch_plan(
            inputs=args.inputs,
            recursive=args.recursive,
            output_dir=output_dir,
            is_image_file=_IS_IMAGE_FILE,
            batch_pages=args.batch_pages,
            layout_debug=policy.layout_debug_announced,
            layout_debug_dir=(
                Path(args.layout_debug_dir)
                if policy.layout_debug_announced and args.layout_debug_dir
                else None
            ),
        )
    except BatchPlanError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)  # noqa: T201  # CLI output
        sys.exit(1)

    # Fire version check in background — result printed before first blocking work.
    # Suppressed by --no-update-check or PD_OCR_NO_UPDATE_CHECK=1 (offline runs).
    _update_thread = _start_update_check_thread(
        disabled=_startup_notices.update_check_disabled(args)
    )

    # One-line nudge for users who have an NVIDIA GPU but installed
    # pdomain-ocr without the [gpu] extra — surfaces the opt-in path so the
    # GPU isn't silently left on the table. Suppressible via
    # PD_OCR_NO_GPU_NUDGE=1. The probe itself is bullet-proof: any
    # error (missing nvidia-smi, hung subprocess, broken CuPy) is
    # swallowed so the nudge never breaks the actual OCR run.
    _maybe_print_gpu_nudge()

    print("Resolving model files...", flush=True)  # noqa: T201  # CLI output
    try:
        det_path, reco_path = resolve_ocr_models(args)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001  # normalize all resolver failures to CLI stderr
        print(f"ERROR resolving OCR model files: {exc}", file=sys.stderr)  # noqa: T201
        sys.exit(1)

    layout_repo: str | None = None
    layout_revision: str | None = None
    layout_descriptor = ""
    if policy.layout_needed:
        try:
            layout_repo, layout_revision, layout_descriptor = resolve_layout_source(args)
            if layout_repo is not None:
                _ = prefetch_layout_files(layout_repo, layout_revision)
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001  # normalize all resolver failures to CLI stderr
            print(f"ERROR resolving layout model files: {exc}", file=sys.stderr)  # noqa: T201
            sys.exit(1)

    print("Importing deep-learning runtime (PyTorch + DocTR)...", flush=True)  # noqa: T201  # CLI output
    device = _detect_torch_device()

    print("Loading OCR models (detection + recognition)...", flush=True)  # noqa: T201  # CLI output
    try:
        runtime_session = _create_runtime_session(det_path, reco_path)
    except ImportError as e:
        print(f"ERROR: pdomain_book_tools not importable: {e}", file=sys.stderr)  # noqa: T201  # CLI output
        sys.exit(1)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)  # noqa: T201  # CLI output
        sys.exit(1)
    print(f"Detection model loaded:   {det_source_descriptor(args, det_path)} (device={device})")  # noqa: T201  # CLI output
    print(f"Recognition model loaded: {reco_source_descriptor(args, reco_path)} (device={device})")  # noqa: T201  # CLI output

    layout_detector = None
    if policy.layout_needed:
        print("Loading layout model...", flush=True)  # noqa: T201  # CLI output
        try:
            layout_detector = _load_layout_detector(args, device)
        except (ImportError, ValueError) as e:
            print(f"ERROR: {e}", file=sys.stderr)  # noqa: T201  # CLI output
            sys.exit(1)
        print(f"Layout model loaded:      {layout_descriptor} (device={device})")  # noqa: T201  # CLI output
    elif policy.layout_configured:
        print("Layout detection skipped (--no-reorg).")  # noqa: T201  # CLI output
    else:
        print("Layout detection disabled (--layout-model none).")  # noqa: T201  # CLI output

    cv2_module: _Cv2Like | None = None
    crop_types: set[object] = set()
    if args.extract_illustrations:
        cv2_module, crop_types = _load_illustration_deps()

    validate_word_preservation = (
        _load_validate_word_preservation() if policy.validate_reorg else None
    )

    # Lazily OCR images in chunks of ``args.batch_pages``.  Each chunk is
    # fed to the runtime session (which owns batch-size sizing and OOM
    # backoff) and returns one book-tools ``Page`` per image in the chunk.
    # Chunking is interleaved with per-page post-processing (via the inner
    # generator loop) so that a ``KeyboardInterrupt`` during post-processing
    # stops the pipeline at the current chunk boundary — subsequent chunks
    # are never OCR'd.
    chunk_size = batch_plan.chunk_size

    errors = 0
    processed = 0
    interrupted = False

    # Outer loop: one chunk at a time.  A ``break`` or propagated
    # ``KeyboardInterrupt`` from the inner per-page loop exits both loops
    # without OCR'ing the remaining chunks.
    def _record_error(img_path: object, exc: BaseException) -> None:
        """Emit per-image error to stderr (and traceback under PD_OCR_DEBUG)."""
        print()  # noqa: T201  # CLI output — close unterminated "Processing X ..." line
        print(f"ERROR processing {img_path}: {exc}", file=sys.stderr)  # noqa: T201  # CLI output
        if _env_truthy("PD_OCR_DEBUG"):
            import traceback

            traceback.print_exc(file=sys.stderr)

    # cv2 + numpy are always present with the doctr/gpu deps that this code path
    # requires.  Import once here (lazy, to avoid pulling heavy GPU libs at
    # module import time) rather than re-importing on every chunk iteration.
    import cv2  # optional [gpu] dep; always present with doctr
    import numpy as np

    outer_break = False
    jobs = batch_plan.jobs
    for chunk_start in range(0, len(jobs), chunk_size):
        if outer_break:
            break
        chunk = jobs[chunk_start : chunk_start + chunk_size]

        # Decode each image in the chunk individually so that a corrupt image
        # is caught here — as a per-image error — rather than inside
        # ``_run_doctr_batch`` where it would abort the entire chunk.

        survivor_jobs: list[PageJob] = []
        survivor_arrays: list[object] = []
        survivor_ids: list[str] = []
        for job in chunk:
            img_path = job.image_path
            try:
                raw = img_path.read_bytes()
                arr = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
                if arr is None:
                    raise ValueError(  # noqa: TRY301  # raise inside try is intentional: outer except unifies all decode failures
                        "cv2.imdecode returned None -- image bytes are not a valid image format"
                    )
            except Exception as e:  # noqa: BLE001  # per-image decode error: catch all, report, continue
                # Print the "Processing X ..." prefix here (for decode failures)
                # so that each failed image's output stays on its own terminated
                # line before the next image is considered.  For successful
                # decodes we defer the print to the post-processing loop below so
                # the ``Processing X ... -> out.txt`` pattern is preserved.
                print(f"Processing {img_path} ...", end=" ", flush=True)  # noqa: T201  # CLI output
                _record_error(img_path, e)
                errors += 1
                continue
            survivor_jobs.append(job)
            survivor_arrays.append(arr)
            survivor_ids.append(img_path.name)

        if not survivor_arrays:
            # Every image in this chunk failed at decode; skip the batch call.
            continue

        try:
            chunk_pages = runtime_session.run_batch(
                survivor_arrays,
                source_identifiers=survivor_ids,
            )
        except BatchRuntimeError as exc:
            print(  # noqa: T201  # CLI output
                f"ERROR processing batch {chunk_start // chunk_size + 1}: {exc}",
                file=sys.stderr,
            )
            errors += len(survivor_jobs)
            continue
        for job, page in zip(survivor_jobs, chunk_pages, strict=True):
            img_path = job.image_path
            print(f"Processing {img_path} ...", end=" ", flush=True)  # noqa: T201  # CLI output
            debug_file = None
            dest_dir = job.dest_dir
            out_path = job.txt_path
            json_path = job.json_path

            try:
                # ``dest_dir.mkdir`` operates on a user-supplied path (``-o`` or
                # a mirror under it); keep it inside the per-image ``try`` so a
                # filesystem failure (e.g. ``-o`` is a regular file, or a
                # mirror collides with an existing file) is recorded as one
                # per-image error rather than aborting the whole batch. (B14)
                dest_dir.mkdir(parents=True, exist_ok=True)

                # ``setup_layout_debug_env`` calls ``mkdir`` on a user-supplied
                # path; keep it inside the per-image ``try`` so an unwritable
                # ``--layout-debug-dir`` is recorded as one per-image error
                # rather than aborting the whole batch.
                debug_file = (
                    setup_layout_debug_env(args, dest_dir, img_path.stem)
                    if policy.layout_debug_announced
                    else None
                )
                if page is None:
                    # Close the ``Processing X ...`` line (printed with
                    # end=" ") before the warning so subsequent stdout
                    # doesn't concatenate onto it. Tally as a per-image
                    # error so an all-empty batch exits non-zero rather
                    # than misleading shell scripts that branch on $?.
                    print()  # noqa: T201  # CLI output
                    print(f"WARNING: no pages in result for {img_path}", file=sys.stderr)  # noqa: T201  # CLI output
                    errors += 1
                    continue

                page_layout = None
                if layout_detector is not None:
                    page_layout = layout_detector.detect(img_path)
                    print(  # noqa: T201  # CLI output
                        f"  layout: {len(page_layout.regions)} regions ({page_layout.inference_ms} ms)",
                        flush=True,
                    )

                # Snapshot pre-reorg word list when --validate-reorg is on. The
                # diagnostic-export bundle is written from the library's own
                # post-reorganize ``page.diagnostic_pure_ocr`` /
                # ``diagnostic_post_noise_removal`` snapshots, so we no longer
                # need a manual pre-reorg JSON dump here.
                reorganize_page = page.reorganize_page
                pre_reorg_words: list[object] = []
                if policy.validate_reorg:
                    pre_reorg_words = list(page.words)

                if policy.do_reorg:
                    if page_layout is not None:
                        reorganize_page(
                            layout=page_layout,
                            drop_layout_words=policy.drop_layout_words,
                            emit_illustration_placeholders=policy.emit_illustration_placeholders,
                        )
                    else:
                        reorganize_page(
                            drop_layout_words=policy.drop_layout_words,
                            emit_illustration_placeholders=policy.emit_illustration_placeholders,
                        )

                    # Always-on noise-drop warning. The library populates
                    # ``diagnostic_noise_dropped_*`` regardless of whether the
                    # snapshot ``Page`` clones were captured, so this fires
                    # even when capture_diagnostics=False is wired through in
                    # the future.
                    dropped_raw = getattr(page, "diagnostic_noise_dropped_words", None)
                    dropped = list(cast("Sequence[object]", dropped_raw)) if dropped_raw else []
                    if dropped:
                        for line in format_noise_drop_warning(
                            dropped,
                            img_path.name,
                            diagnostic_flag_name="--save-json --save-reorganize-diagnostics",
                        ):
                            print(line, file=sys.stderr)  # noqa: T201  # CLI output

                    if validate_word_preservation is not None:
                        drops = validate_word_preservation(pre_reorg_words, list(page.words))
                        for line in format_drops_warning(drops, img_path.name):
                            print(line, file=sys.stderr)  # noqa: T201  # CLI output

                text = apply_text_normalizations(
                    page.text,
                    straight_quotes=args.straight_quotes,
                    em_dash_to_double_hyphen=args.em_dash_to_double_hyphen,
                )
                if not text:
                    print(f"WARNING: empty text result for {img_path}", file=sys.stderr)  # noqa: T201  # CLI output

                # The canonical ``.txt`` is written *last* (after the json
                # sidecar, diagnostic snapshots, and illustration crops) so
                # that any per-image failure leaves the output directory
                # without a ``.txt`` for that page. External pipelines key
                # on ``.txt`` existence to mean "this page completed
                # successfully"; an orphan ``.txt`` next to a missing
                # sidecar would silently masquerade as a clean run.
                # (Code-review B19.) Combined with the B18 atomic-write
                # invariant on the ``.txt`` itself, the per-page artifact
                # set is now all-or-nothing.
                extra_paths: list[str] = []
                if args.save_json:
                    # ``_SinglePageDoc.to_json_file`` writes a document-envelope
                    # JSON (same shape as Document.to_json_file) so downstream
                    # consumers see an identical format. Atomic write: sibling
                    # temp + os.replace (Code-review B18).
                    doc = _SinglePageDoc(
                        page, source_identifier=img_path.name, source_path=img_path
                    )
                    atomic_write_json_document(json_path, doc)
                    extra_paths.append(str(json_path))
                if policy.want_diagnostic_export:
                    diag_paths = diagnostic_output_paths(json_path, out_path)
                    written, notes = write_diagnostic_snapshots(
                        page,
                        pure_ocr_json=diag_paths["pure_ocr_json"],
                        pure_ocr_txt=diag_paths["pure_ocr_txt"],
                        post_noise_json=diag_paths["post_noise_json"],
                        post_noise_txt=diag_paths["post_noise_txt"],
                    )
                    for note in notes:
                        print(f"WARNING: {img_path.name}: {note}", file=sys.stderr)  # noqa: T201  # CLI output
                    extra_paths.extend(str(p) for p in written)
                # Only advertise the layout-debug artifact when reorganize_page
                # actually ran — that is the codepath in pdomain-book-tools that
                # writes the report. With ``--no-reorg`` (or any other reason
                # ``do_reorg`` is False) the file never materialises, so the
                # success line must not point at it. (B9)
                if policy.layout_debug_announced and debug_file is not None:
                    extra_paths.append(f"layout-debug: {debug_file}")

                if (
                    args.extract_illustrations
                    and page_layout is not None
                    and cv2_module is not None
                ):
                    source_img = cv2_module.imread(str(img_path))
                    if source_img is None:
                        print(  # noqa: T201  # CLI output
                            f"WARNING: could not re-read {img_path} for illustration crops",
                            file=sys.stderr,
                        )
                    else:
                        for crop_pair in iter_crop_regions(
                            page_layout.regions,
                            args.layout_confidence,
                            crop_types,
                        ):
                            crop_idx, raw_region = cast("tuple[int, object]", crop_pair)
                            region = cast("_RegionLike", raw_region)
                            crop = source_img[
                                max(0, region.T) : max(0, region.B),
                                max(0, region.L) : max(0, region.R),
                            ]
                            if crop.size == 0:
                                continue
                            crop_path = illustration_crop_path(dest_dir, img_path.stem, crop_idx)
                            ok, encoded = cv2_module.imencode(".jpg", crop)
                            if not ok:
                                print(  # noqa: T201  # CLI output
                                    f"WARNING: cv2.imencode failed for {crop_path}",
                                    file=sys.stderr,
                                )
                                continue
                            atomic_write_bytes(crop_path, bytes(encoded))
                            extra_paths.append(str(crop_path))

                # B19: ``.txt`` is written *last* so a failure in any prior
                # sidecar/crop step leaves no orphan ``.txt``. B18: still
                # atomic, so a SIGKILL/OOM/ENOSPC mid-rename never leaves a
                # truncated ``.txt`` at the canonical path.
                atomic_write_text(out_path, text)

                tag = " (no-reorg)" if args.no_reorg else ""
                if extra_paths:
                    print(f"-> {out_path}, {', '.join(extra_paths)}{tag}")  # noqa: T201  # CLI output
                else:
                    print(f"-> {out_path}{tag}")  # noqa: T201  # CLI output
                processed += 1
            except KeyboardInterrupt:
                # ``KeyboardInterrupt`` inherits from ``BaseException`` and so
                # is NOT caught by the ``except Exception`` branch below. Without
                # this branch, Ctrl-C mid-batch escapes the for-loop entirely,
                # skipping the end-of-batch summary, the update-thread join, and
                # the deterministic exit code. (B20)
                print()  # close the unterminated ``Processing X ...`` line  # noqa: T201  # CLI output
                interrupted = True
                outer_break = True
                break
            except Exception as e:  # noqa: BLE001  # per-image error: catch all, report, continue batch
                # ``_record_error`` closes the unterminated ``Processing X ...``
                # stdout line (printed with ``end=" "``) before the stderr
                # message so subsequent output starts on its own line. (B17)
                _record_error(img_path, e)
                errors += 1
            finally:
                clear_layout_debug_env()

    if _update_thread is not None:
        _update_thread.join(timeout=3)
    if interrupted:
        print(  # noqa: T201  # CLI output
            f"Interrupted after {processed}/{len(jobs)} image(s); {errors} error(s) so far.",
            file=sys.stderr,
        )
        sys.exit(130)
    if errors:
        print(f"Done ({errors} error(s)).")  # noqa: T201  # CLI output
        sys.exit(1)
    print("Done.")  # noqa: T201  # CLI output


if __name__ == "__main__":
    main()
