"""CLI: OCR images to .txt using fine-tuned DocTR detection + recognition models.

Usage
-----
Install and run (models download automatically):
    uv tool install git+https://github.com/ConcaveTrillion/pd-ocr-cli
    pd-ocr page.png

Run directly without installing:
    uvx --from git+https://github.com/ConcaveTrillion/pd-ocr-cli pd-ocr page.png

Multiple images:
    pd-ocr page1.png page2.png page3.png

Process a whole directory:
    pd-ocr images/

Process a directory tree recursively:
    pd-ocr --recursive images/ -o output/

Write output to a specific directory (mirrors input structure for directories):
    pd-ocr -o output/ page.png

Also save the reorganized OCR document as JSON alongside the .txt:
    pd-ocr --save-json page.png

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
--layout-debug[-dir]         Write layout debug text alongside outputs.

Downloaded models are cached in ~/.cache/huggingface/hub and reused on
subsequent runs.
"""

import argparse
import os
import sys
import threading
from pathlib import Path

from pd_ocr_cli._hf_models import (
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
from pd_ocr_cli._pipeline import (
    apply_text_normalizations,
    clear_layout_debug_env,
    compute_mirror_root,
    diagnostic_output_paths,
    format_drops_warning,
    format_noise_drop_warning,
    illustration_crop_path,
    iter_crop_regions,
    output_paths_for,
    resolve_dest_dir,
    setup_layout_debug_env,
    validate_extract_illustrations,
    write_diagnostic_snapshots,
)
from pd_ocr_cli._update_check import VERSION as _VERSION
from pd_ocr_cli._update_check import check_for_update as _check_for_update

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


def _detect_torch_device() -> str:
    """Pick the best available torch device for the layout model."""
    try:
        import torch
    except ImportError:
        return "cpu"
    if torch.cuda.is_available():
        return "cuda"
    mps = getattr(torch.backends, "mps", None)
    if mps is not None and getattr(mps, "is_available", lambda: False)():
        return "mps"
    return "cpu"


# ---------------------------------------------------------------------------
# Lazy-import indirection — the only purpose of these tiny wrappers is to
# give tests a single attribute to ``monkeypatch`` so ``main()`` can run end
# to end without loading torch / DocTR / pd_book_tools / cv2.
# ---------------------------------------------------------------------------


def _load_predictor(det_path: Path, reco_path: Path):
    """Import doctr support and build the fine-tuned predictor."""
    from pd_book_tools.ocr.doctr_support import get_finetuned_torch_doctr_predictor

    return get_finetuned_torch_doctr_predictor(det_path, reco_path)


def _load_layout_detector(args, device: str):
    """Import the layout module and instantiate the configured detector."""
    silence_transformers_load_chatter()
    from pd_book_tools.layout import get_detector

    return get_detector(
        args.layout_model,
        device=device,
        confidence=args.layout_confidence,
        checkpoint_path=args.layout_checkpoint,
    )


def _load_document_factory():
    """Return the ``Document.from_image_ocr_via_doctr`` callable."""
    from pd_book_tools.ocr.document import Document

    return Document.from_image_ocr_via_doctr


def _load_validate_word_preservation():
    """Return the ``validate_word_preservation`` reorganize-checker."""
    from pd_book_tools.ocr.reorganize_page_utils import validate_word_preservation

    return validate_word_preservation


def _load_illustration_deps() -> tuple[object, set]:
    """Return ``(cv2_module, crop_types_set)`` used during illustration cropping."""
    import cv2 as _cv2
    from pd_book_tools.layout.types import RegionType

    return _cv2, {RegionType.figure, RegionType.decoration, RegionType.table}


def _start_update_check_thread(disabled: bool) -> threading.Thread | None:
    """Spawn the background GitHub-tag check unless suppressed."""
    if disabled:
        return None
    thread = threading.Thread(target=_check_for_update, daemon=True)
    thread.start()
    return thread


def _env_truthy(name: str) -> bool:
    """True if the env var is set to a truthy value (1/true/yes/on, case-insensitive)."""
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def parse_args():
    p = argparse.ArgumentParser(
        description="OCR images to .txt using fine-tuned detection + recognition models."
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {_VERSION}")

    src = p.add_argument_group("model source (use --hf-repo OR --detection/--recognition)")
    src.add_argument(
        "--hf-repo",
        metavar="REPO_ID",
        default=DEFAULT_HF_REPO,
        help=f"Hugging Face repo to download models from (default: {DEFAULT_HF_REPO}).",
    )
    src.add_argument(
        "--model-version",
        metavar="TAG",
        default=None,
        help="HF repo revision/tag to use (default: latest). Requires --hf-repo.",
    )
    src.add_argument(
        "--det-filename",
        metavar="PATH",
        default=DEFAULT_DET_FILENAME,
        help=f"Filename within the HF repo for the detection model (default: {DEFAULT_DET_FILENAME}).",
    )
    src.add_argument(
        "--reco-filename",
        metavar="PATH",
        default=DEFAULT_RECO_FILENAME,
        help=f"Filename within the HF repo for the recognition model (default: {DEFAULT_RECO_FILENAME}).",
    )
    src.add_argument(
        "--detection",
        "-d",
        metavar="PT_FILE",
        default=None,
        help="Path to a local detection .pt model file.",
    )
    src.add_argument(
        "--recognition",
        "-g",
        metavar="PT_FILE",
        default=None,
        help="Path to a local recognition .pt model file.",
    )

    p.add_argument(
        "--output-dir",
        "-o",
        metavar="DIR",
        default=None,
        help="Directory to write .txt files into (default: same directory as each image).",
    )
    p.add_argument(
        "--save-json",
        action="store_true",
        default=False,
        help="Also save the reorganized OCR document as a .json file alongside the .txt.",
    )
    p.add_argument(
        "--no-reorg",
        action="store_true",
        default=False,
        help=(
            "Skip Page.reorganize_page(). Emits raw OCR output (the .txt and "
            ".json reflect the OCR engine's structure with no header/footer "
            "extraction, column splitting, or paragraph reordering)."
        ),
    )
    p.add_argument(
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
    p.add_argument(
        "--validate-reorg",
        action="store_true",
        default=False,
        help=(
            "After reorganize_page(), assert that every OCR word present "
            "before reorganize is still present after (by text + bbox). "
            "Mismatches print a WARNING; the .txt/.json are still written."
        ),
    )
    p.add_argument(
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
    p.add_argument(
        "--recursive",
        "-r",
        "-R",
        action="store_true",
        default=False,
        help="Recurse into subdirectories when a directory is given as input.",
    )
    p.add_argument(
        "--straight-quotes",
        "-sq",
        action="store_true",
        default=False,
        help="Convert curly quotes in OCR text output to straight ASCII quotes.",
    )
    p.add_argument(
        "--em-dash-to-double-hyphen",
        "-ed",
        action="store_true",
        default=False,
        help="Convert em dash in OCR text output to double hyphen (--).",
    )
    p.add_argument(
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
    p.add_argument(
        "--layout-model",
        default="pp-doclayout-plus-l",
        choices=["none", "contour", "pp-doclayout-plus-l"],
        help=(
            "Layout-detector backend. Layout detection always runs (its "
            "output is fed into Page.reorganize_page() as a hint so captions "
            "get wrapped, high-confidence headers/footers get stripped, "
            "and tables/figures get tagged). Pass `--layout-model none` to "
            "skip layout detection. Default: pp-doclayout-plus-l."
        ),
    )
    p.add_argument(
        "--layout-checkpoint",
        default=None,
        metavar="PATH_OR_REPO",
        help=(
            "Path or HF repo for a fine-tuned layout checkpoint. Overrides "
            "the default PP-DocLayout_plus-L weights."
        ),
    )
    p.add_argument(
        "--layout-confidence",
        type=float,
        default=0.5,
        metavar="THRESHOLD",
        help="Confidence threshold for layout detections (0..1). Default 0.5.",
    )
    p.add_argument(
        "--extract-illustrations",
        action="store_true",
        default=False,
        help=(
            "Write i_<stem>_<n>.jpg crops for figure / decoration / table "
            "regions alongside the .txt. Requires a layout model "
            "(error if combined with --layout-model none)."
        ),
    )
    p.add_argument(
        "--layout-debug",
        action="store_true",
        default=False,
        help=(
            "Write step-by-step layout debug text files (X-axis 3-group lines, "
            "squeezed side-flow diagnostics)."
        ),
    )
    p.add_argument(
        "--layout-debug-dir",
        metavar="DIR",
        default=None,
        help=(
            "Directory for layout debug text files. "
            "Defaults to each image output directory when --layout-debug is enabled."
        ),
    )
    p.add_argument(
        "inputs",
        nargs="+",
        metavar="IMAGE_OR_DIR",
        help="One or more image files or directories to process.",
    )
    return p.parse_args()


def collect_images(inputs: list[str], recursive: bool) -> list[Path]:
    """Expand files and directories into a flat list of image paths."""
    images = []
    for inp in inputs:
        p = Path(inp)
        if p.is_file():
            if p.suffix.lower() in IMAGE_SUFFIXES:
                images.append(p)
            else:
                print(f"WARNING: skipping non-image file: {p}", file=sys.stderr)
        elif p.is_dir():
            pattern = "**/*" if recursive else "*"
            for child in sorted(p.glob(pattern)):
                if child.is_file() and child.suffix.lower() in IMAGE_SUFFIXES:
                    images.append(child)
        else:
            print(f"WARNING: skipping missing path: {p}", file=sys.stderr)
    return images


def main():
    args = parse_args()

    validate_extract_illustrations(args)
    layout_enabled = args.layout_model != "none"

    # Fire version check in background — result printed before first blocking work.
    # Suppressed by --no-update-check or PD_OCR_NO_UPDATE_CHECK=1 (offline runs).
    update_check_disabled = args.no_update_check or _env_truthy("PD_OCR_NO_UPDATE_CHECK")
    _update_thread = _start_update_check_thread(disabled=update_check_disabled)

    print("Resolving model files...", flush=True)
    det_path, reco_path = resolve_ocr_models(args)

    layout_repo: str | None = None
    layout_revision: str | None = None
    layout_descriptor = ""
    if layout_enabled:
        layout_repo, layout_revision, layout_descriptor = resolve_layout_source(args)
        if layout_repo is not None:
            prefetch_layout_files(layout_repo, layout_revision)

    output_dir = Path(args.output_dir) if args.output_dir else None

    print("Importing deep-learning runtime (PyTorch + DocTR)...", flush=True)
    device = _detect_torch_device()

    print("Loading OCR models (detection + recognition)...", flush=True)
    try:
        predictor = _load_predictor(det_path, reco_path)
    except ImportError as e:
        print(f"ERROR: pd_book_tools not importable: {e}", file=sys.stderr)
        sys.exit(1)
    if predictor is None:
        print("ERROR: failed to load models.", file=sys.stderr)
        sys.exit(1)
    print(f"Detection model loaded:   {det_source_descriptor(args, det_path)} (device={device})")
    print(f"Recognition model loaded: {reco_source_descriptor(args, reco_path)} (device={device})")

    layout_detector = None
    if layout_enabled:
        print("Loading layout model...", flush=True)
        try:
            layout_detector = _load_layout_detector(args, device)
        except (ImportError, ValueError) as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
        print(f"Layout model loaded:      {layout_descriptor} (device={device})")
    else:
        print("Layout detection disabled (--layout-model none).")

    cv2 = None
    crop_types: set = set()
    if args.extract_illustrations:
        cv2, crop_types = _load_illustration_deps()

    document_factory = _load_document_factory()

    images = collect_images(args.inputs, args.recursive)
    if not images:
        print("ERROR: no valid image files found.", file=sys.stderr)
        sys.exit(1)

    mirror_root = compute_mirror_root(args.inputs, output_dir)

    errors = 0
    for img_path in images:
        dest_dir = resolve_dest_dir(img_path, output_dir, mirror_root)
        dest_dir.mkdir(parents=True, exist_ok=True)

        out_path, json_path = output_paths_for(img_path, dest_dir)

        print(f"Processing {img_path} ...", end=" ", flush=True)
        debug_file = setup_layout_debug_env(args, dest_dir, img_path.stem)

        try:
            doc = document_factory(img_path, source_identifier=img_path.name, predictor=predictor)
            page = doc.pages[0] if doc.pages else None
            if page is None:
                print("WARNING: no pages in result", file=sys.stderr)
                continue

            page_layout = None
            if layout_detector is not None:
                page_layout = layout_detector.detect(img_path)
                print(
                    f"  layout: {len(page_layout.regions)} regions ({page_layout.inference_ms} ms)",
                    flush=True,
                )

            # Snapshot pre-reorg word list when --validate-reorg is on. The
            # diagnostic-export bundle is written from the library's own
            # post-reorganize ``page.diagnostic_pure_ocr`` /
            # ``diagnostic_post_noise_removal`` snapshots, so we no longer
            # need a manual pre-reorg JSON dump here.
            do_reorg = not args.no_reorg and callable(getattr(page, "reorganize_page", None))
            want_diagnostic_export = (
                do_reorg and args.save_json and args.save_reorganize_diagnostics
            )
            pre_reorg_words: list = []
            if do_reorg and args.validate_reorg:
                pre_reorg_words = list(page.words)

            if do_reorg:
                drop_layout_words = args.experimental_drop_layout_words
                if page_layout is not None:
                    page.reorganize_page(
                        layout=page_layout,
                        drop_layout_words=drop_layout_words,
                    )
                else:
                    page.reorganize_page(drop_layout_words=drop_layout_words)

                # Always-on noise-drop warning. The library populates
                # ``diagnostic_noise_dropped_*`` regardless of whether the
                # snapshot ``Page`` clones were captured, so this fires
                # even when capture_diagnostics=False is wired through in
                # the future.
                dropped = list(getattr(page, "diagnostic_noise_dropped_words", []) or [])
                if dropped:
                    for line in format_noise_drop_warning(
                        dropped,
                        img_path.name,
                        diagnostic_flag_name="--save-json --save-reorganize-diagnostics",
                    ):
                        print(line, file=sys.stderr)

                if args.validate_reorg:
                    validate_word_preservation = _load_validate_word_preservation()
                    drops = validate_word_preservation(pre_reorg_words, list(page.words))
                    for line in format_drops_warning(drops, img_path.name):
                        print(line, file=sys.stderr)

            text = apply_text_normalizations(
                page.text,
                straight_quotes=args.straight_quotes,
                em_dash_to_double_hyphen=args.em_dash_to_double_hyphen,
            )
            if not text:
                print(f"WARNING: empty text result for {img_path}", file=sys.stderr)
            out_path.write_text(text, encoding="utf-8")

            extra_paths: list[str] = []
            if args.save_json:
                doc.to_json_file(json_path)
                extra_paths.append(str(json_path))
            if want_diagnostic_export:
                diag_paths = diagnostic_output_paths(json_path, out_path)
                written, notes = write_diagnostic_snapshots(
                    page,
                    json_path=json_path,
                    txt_path=out_path,
                    pure_ocr_json=diag_paths["pure_ocr_json"],
                    pure_ocr_txt=diag_paths["pure_ocr_txt"],
                    post_noise_json=diag_paths["post_noise_json"],
                    post_noise_txt=diag_paths["post_noise_txt"],
                )
                for note in notes:
                    print(f"WARNING: {img_path.name}: {note}", file=sys.stderr)
                extra_paths.extend(str(p) for p in written)
            if args.layout_debug and debug_file is not None:
                extra_paths.append(f"layout-debug: {debug_file}")

            if args.extract_illustrations and page_layout is not None and cv2 is not None:
                source_img = cv2.imread(str(img_path))
                if source_img is None:
                    print(
                        f"WARNING: could not re-read {img_path} for illustration crops",
                        file=sys.stderr,
                    )
                else:
                    for crop_idx, region in iter_crop_regions(
                        page_layout.regions, args.layout_confidence, crop_types
                    ):
                        crop = source_img[
                            max(0, region.T) : max(0, region.B),
                            max(0, region.L) : max(0, region.R),
                        ]
                        if crop.size == 0:
                            continue
                        crop_path = illustration_crop_path(dest_dir, img_path.stem, crop_idx)
                        cv2.imwrite(str(crop_path), crop)
                        extra_paths.append(str(crop_path))

            tag = " (no-reorg)" if args.no_reorg else ""
            if extra_paths:
                print(f"-> {out_path}, {', '.join(extra_paths)}{tag}")
            else:
                print(f"-> {out_path}{tag}")
        except Exception as e:
            print(f"ERROR processing {img_path}: {e}", file=sys.stderr)
            if _env_truthy("PD_OCR_DEBUG"):
                import traceback

                traceback.print_exc(file=sys.stderr)
            errors += 1
        finally:
            clear_layout_debug_env()

    if _update_thread is not None:
        _update_thread.join(timeout=3)
    if errors:
        print(f"Done ({errors} error(s)).")
        sys.exit(1)
    print("Done.")


if __name__ == "__main__":
    main()
