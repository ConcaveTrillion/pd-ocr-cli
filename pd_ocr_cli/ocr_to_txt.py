"""CLI: OCR images to .txt using fine-tuned DocTR detection + recognition models.

Usage
-----
Install as a uv tool (adds 'pd-ocr' to your PATH):
    uv tool install git+https://github.com/ConcaveTrillion/pd-ocr-cli
    pd-ocr --hf-repo CT2534/pd-ocr-models page.png

Run directly without installing:
    uvx --from git+https://github.com/ConcaveTrillion/pd-ocr-cli pd-ocr \\
        --hf-repo CT2534/pd-ocr-models page.png

With local model files:
    pd-ocr --detection model-det.pt --recognition model-reco.pt image.png

Model source (pick one)
-----------------------
--hf-repo REPO_ID           Download latest models from Hugging Face Hub.
                             e.g. --hf-repo CT2534/pd-ocr-models
--hf-repo REPO_ID \\
  --model-version TAG        Pin to a specific HF tag/revision.
                             e.g. --model-version v1.0
--detection / --recognition  Use local .pt files directly.

Downloaded models are cached in ~/.cache/huggingface/hub and reused on
subsequent runs.
"""

import argparse
import sys
from pathlib import Path


DEFAULT_HF_REPO = "CT2534/pd-ocr-models"
DEFAULT_DET_FILENAME = "detection/pd-all-detection-model-finetuned.pt"
DEFAULT_RECO_FILENAME = "recognition/pd-all-recognition-model-finetuned.pt"


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

    print(f"Downloading {filename} from {repo_id} (revision={revision or 'latest'})...")
    local_path = hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        revision=revision,
    )
    # Also download sidecar files if they exist
    for ext in (".arch", ".vocab"):
        sidecar = filename.rsplit(".", 1)[0] + ext
        try:
            hf_hub_download(repo_id=repo_id, filename=sidecar, revision=revision)
        except Exception:
            pass  # Sidecars are optional
    return Path(local_path)


def parse_args():
    p = argparse.ArgumentParser(
        description="OCR images to .txt using fine-tuned detection + recognition models."
    )

    src = p.add_argument_group("model source (use --hf-repo OR --detection/--recognition)")
    src.add_argument(
        "--hf-repo", metavar="REPO_ID", default=None,
        help=f"Hugging Face repo to download models from (e.g. {DEFAULT_HF_REPO})."
    )
    src.add_argument(
        "--model-version", metavar="TAG", default=None,
        help="HF repo revision/tag to use (default: latest). Requires --hf-repo."
    )
    src.add_argument(
        "--det-filename", metavar="PATH", default=DEFAULT_DET_FILENAME,
        help=f"Filename within the HF repo for the detection model (default: {DEFAULT_DET_FILENAME})."
    )
    src.add_argument(
        "--reco-filename", metavar="PATH", default=DEFAULT_RECO_FILENAME,
        help=f"Filename within the HF repo for the recognition model (default: {DEFAULT_RECO_FILENAME})."
    )
    src.add_argument(
        "--detection", "-d", metavar="PT_FILE", default=None,
        help="Path to a local detection .pt model file."
    )
    src.add_argument(
        "--recognition", "-r", metavar="PT_FILE", default=None,
        help="Path to a local recognition .pt model file."
    )

    p.add_argument(
        "--output-dir", "-o", metavar="DIR", default=None,
        help="Directory to write .txt files into (default: same directory as each image)."
    )
    p.add_argument(
        "images", nargs="+", metavar="IMAGE",
        help="One or more image files to process."
    )
    return p.parse_args()


def resolve_model_paths(args) -> tuple[Path, Path]:
    """Return (det_path, reco_path) from either HF Hub or local args."""
    if args.hf_repo:
        det_path = _hf_download(args.hf_repo, args.det_filename, args.model_version)
        reco_path = _hf_download(args.hf_repo, args.reco_filename, args.model_version)
        return det_path, reco_path

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

    print(
        "ERROR: provide either --hf-repo or both --detection and --recognition.",
        file=sys.stderr,
    )
    sys.exit(1)


def main():
    args = parse_args()

    det_path, reco_path = resolve_model_paths(args)

    output_dir = Path(args.output_dir) if args.output_dir else None
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)

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

    for img_arg in args.images:
        img_path = Path(img_arg)
        if not img_path.is_file():
            print(f"WARNING: skipping missing file: {img_path}", file=sys.stderr)
            continue

        dest_dir = output_dir if output_dir else img_path.parent
        out_path = dest_dir / img_path.with_suffix(".txt").name

        print(f"Processing {img_path} ...", end=" ", flush=True)
        try:
            doc = Document.from_image_ocr_via_doctr(
                img_path, source_identifier=img_path.name, predictor=predictor
            )
            text = doc.pages[0].text if doc.pages else ""
            out_path.write_text(text, encoding="utf-8")
            print(f"-> {out_path}")
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)

    print("Done.")


if __name__ == "__main__":
    main()
