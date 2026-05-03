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

Downloaded models are cached in ~/.cache/huggingface/hub and reused on
subsequent runs.
"""

import argparse
import contextlib
import logging
import os
import re
import sys
import threading
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path

try:
    _VERSION = _pkg_version("pd-ocr-cli")
except PackageNotFoundError:
    _VERSION = "unknown"

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


def _check_for_update() -> None:
    """Print a notice (to stderr) if a newer release tag is available on GitHub.

    Runs in a background thread — never blocks startup.
    Silently suppressed on any network or parse error.
    """
    if _VERSION == "unknown":
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

        current = _parse_release_prefix(_VERSION)
        if current is None:
            return

        latest_tag_name, latest = latest_stable
        if latest > current:
            print(
                f"\nNOTICE: A newer version of pd-ocr is available ({latest_tag_name}, "
                f"you have {_VERSION}).\n"
                f"  To upgrade, run:\n"
                f"    curl -sSL {_INSTALL_URL} | sh\n",
                file=sys.stderr,
            )
    except Exception:
        pass  # Version check is best-effort


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


DEFAULT_HF_REPO = "CT2534/pd-ocr-models"
DEFAULT_DET_FILENAME = "detection/pd-all-detection-model-finetuned.pt"
DEFAULT_RECO_FILENAME = "recognition/pd-all-recognition-model-finetuned.pt"
_CURLY_TO_STRAIGHT_TRANSLATION = str.maketrans(
    {
        "\u2018": "'",  # left single quote
        "\u2019": "'",  # right single quote / apostrophe
        "\u201a": "'",  # single low-9 quote
        "\u201b": "'",  # single high-reversed-9 quote
        "\u201c": '"',  # left double quote
        "\u201d": '"',  # right double quote
        "\u201e": '"',  # double low-9 quote
        "\u201f": '"',  # double high-reversed-9 quote
    }
)


def _normalize_curly_quotes(text: str) -> str:
    """Convert common curly quote variants to straight ASCII quotes."""
    return text.translate(_CURLY_TO_STRAIGHT_TRANSLATION)


def _normalize_em_dash(text: str) -> str:
    """Convert em dash to ASCII double hyphen."""
    return text.replace("\u2014", "--")


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


def _hf_download(repo_id: str, filename: str, revision: str | None) -> Path:
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
    # Also download sidecar files if they exist; only swallow 404 errors
    try:
        from huggingface_hub.utils import EntryNotFoundError as _HFNotFound
    except ImportError:
        _HFNotFound = Exception  # older hub versions: treat all as optional

    for ext in (".arch", ".vocab"):
        sidecar = filename.rsplit(".", 1)[0] + ext
        try:
            with _suppress_hf_unauth_warning():
                hf_hub_download(repo_id=repo_id, filename=sidecar, revision=revision)
        except _HFNotFound:
            pass  # Sidecar not present in repo
    return Path(local_path)


def parse_args():
    p = argparse.ArgumentParser(
        description="OCR images toh .txt using fine-tuned detection + recognition models."
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
        "inputs",
        nargs="+",
        metavar="IMAGE_OR_DIR",
        help="One or more image files or directories to process.",
    )
    return p.parse_args()


def resolve_model_paths(args) -> tuple[Path, Path]:
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

    det_path = _hf_download(args.hf_repo, args.det_filename, args.model_version)
    reco_path = _hf_download(args.hf_repo, args.reco_filename, args.model_version)
    return det_path, reco_path


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


def describe_model_selection(args, det_path: Path, reco_path: Path) -> str:
    """Return a human-readable description of the model artifacts in use."""
    if args.detection and args.recognition:
        return f"Using local models:\n  detection: {det_path}\n  recognition: {reco_path}"

    revision = args.model_version or "latest"
    return (
        f"Using models from {args.hf_repo} (revision={revision}):\n"
        f"  detection: {args.det_filename}\n"
        f"  recognition: {args.reco_filename}"
    )


def main():
    args = parse_args()

    # Fire version check in background — result printed before first blocking work
    _update_thread = threading.Thread(target=_check_for_update, daemon=True)
    _update_thread.start()

    det_path, reco_path = resolve_model_paths(args)
    print(describe_model_selection(args, det_path, reco_path))

    output_dir = Path(args.output_dir) if args.output_dir else None

    try:
        from pd_book_tools.ocr.doctr_support import get_finetuned_torch_doctr_predictor
    except ImportError as e:
        print(f"ERROR: pd_book_tools not importable: {e}", file=sys.stderr)
        sys.exit(1)

    print("Loading models...")
    predictor = get_finetuned_torch_doctr_predictor(det_path, reco_path)
    if predictor is None:
        print("ERROR: failed to load models.", file=sys.stderr)
        sys.exit(1)
    print("Models loaded.")

    from pd_book_tools.ocr.document import Document

    images = collect_images(args.inputs, args.recursive)
    if not images:
        print("ERROR: no valid image files found.", file=sys.stderr)
        sys.exit(1)

    # Determine a common input root for directory mirroring (only when inputs
    # include at least one directory and an output_dir is set).
    input_dirs = [Path(i) for i in args.inputs if Path(i).is_dir()]
    if input_dirs and output_dir:
        mirror_root = Path(os.path.commonpath([d.resolve() for d in input_dirs]))
    else:
        mirror_root = None

    errors = 0
    for img_path in images:
        if output_dir and mirror_root:
            try:
                rel = img_path.resolve().relative_to(mirror_root)
                dest_dir = output_dir / rel.parent
            except ValueError:
                dest_dir = output_dir
        elif output_dir:
            dest_dir = output_dir
        else:
            dest_dir = img_path.parent
        dest_dir.mkdir(parents=True, exist_ok=True)

        out_path = dest_dir / img_path.with_suffix(".txt").name
        json_path = dest_dir / img_path.with_suffix(".json").name

        print(f"Processing {img_path} ...", end=" ", flush=True)
        try:
            doc = Document.from_image_ocr_via_doctr(
                img_path, source_identifier=img_path.name, predictor=predictor
            )
            page = doc.pages[0] if doc.pages else None
            if page is None:
                print("WARNING: no pages in result", file=sys.stderr)
                continue
            if callable(getattr(page, "reorganize_page", None)):
                page.reorganize_page()
            text = page.text
            if args.straight_quotes and text:
                text = _normalize_curly_quotes(text)
            if args.em_dash_to_double_hyphen and text:
                text = _normalize_em_dash(text)
            if not text:
                print(f"WARNING: empty text result for {img_path}", file=sys.stderr)
            out_path.write_text(text or "", encoding="utf-8")
            if args.save_json:
                doc.to_json_file(json_path)
                print(f"-> {out_path}, {json_path}")
            else:
                print(f"-> {out_path}")
        except Exception as e:
            print(f"ERROR processing {img_path}: {e}", file=sys.stderr)
            errors += 1

    if errors:
        print(f"Done ({errors} error(s)).")
        _update_thread.join(timeout=3)
        sys.exit(1)
    _update_thread.join(timeout=3)
    print("Done.")


if __name__ == "__main__":
    main()
