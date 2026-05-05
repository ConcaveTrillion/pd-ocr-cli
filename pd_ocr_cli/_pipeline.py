"""Pure-function pipeline helpers extracted from ``ocr_to_txt.main``.

These pieces don't need a model loaded and don't talk to the network or
heavy DL runtime. Pulling them into their own module keeps ``main()`` a
thin orchestration shell and lets the unit-test suite cover the
stem-by-stem transforms (path mirroring, text normalization, illustration
region selection, etc.) directly.

The CLI-facing exit-on-bad-input helpers (``validate_extract_illustrations``)
intentionally call ``sys.exit`` so callers don't have to translate
exceptions back into CLI return codes — tests use ``pytest.raises(SystemExit)``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterable, Iterator

from pd_ocr_cli._text_normalize import (
    normalize_curly_quotes as _normalize_curly_quotes,
)
from pd_ocr_cli._text_normalize import (
    normalize_em_dash as _normalize_em_dash,
)

# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------


def validate_extract_illustrations(args) -> None:
    """Exit if ``--extract-illustrations`` is paired with ``--layout-model none``.

    Cropping illustration regions needs a real layout model — refuse the
    combination rather than silently producing zero crops.
    """
    layout_enabled = args.layout_model != "none"
    if args.extract_illustrations and not layout_enabled:
        print(
            "ERROR: --extract-illustrations requires a layout model; drop --layout-model none.",
            file=sys.stderr,
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# Output-path resolution
# ---------------------------------------------------------------------------


def compute_mirror_root(inputs: Iterable[str], output_dir: Path | None) -> Path | None:
    """Return the common-prefix directory used for mirroring directory trees.

    Returns ``None`` when no input is a directory or when no ``output_dir``
    is set — in those cases ``resolve_dest_dir`` falls back to either
    ``output_dir`` directly or each image's parent.
    """
    if output_dir is None:
        return None
    input_dirs = [Path(i) for i in inputs if Path(i).is_dir()]
    if not input_dirs:
        return None
    return Path(os.path.commonpath([d.resolve() for d in input_dirs]))


def resolve_dest_dir(
    img_path: Path,
    output_dir: Path | None,
    mirror_root: Path | None,
) -> Path:
    """Pick the directory the .txt/.json/.jpg outputs for ``img_path`` go in.

    - When ``output_dir`` and ``mirror_root`` are both set, mirror the input
      tree relative to ``mirror_root``.
    - When only ``output_dir`` is set, all outputs go flat under it.
    - When neither is set, write next to the image (legacy behavior).
    """
    if output_dir and mirror_root:
        try:
            rel = img_path.resolve().relative_to(mirror_root)
            return output_dir / rel.parent
        except ValueError:
            return output_dir
    if output_dir:
        return output_dir
    return img_path.parent


def output_paths_for(img_path: Path, dest_dir: Path) -> tuple[Path, Path]:
    """Return ``(txt_path, json_path)`` siblings for ``img_path`` under ``dest_dir``."""
    txt = dest_dir / img_path.with_suffix(".txt").name
    json_ = dest_dir / img_path.with_suffix(".json").name
    return txt, json_


def illustration_crop_path(dest_dir: Path, stem: str, idx: int) -> Path:
    """Return the destination path for the ``idx``th illustration crop of ``stem``."""
    return dest_dir / f"i_{stem}_{idx:02d}.jpg"


# ---------------------------------------------------------------------------
# Text post-processing
# ---------------------------------------------------------------------------


def apply_text_normalizations(
    text: str | None,
    *,
    straight_quotes: bool,
    em_dash_to_double_hyphen: bool,
) -> str:
    """Apply the user-selected ``--straight-quotes`` / ``-ed`` cleanups.

    Tolerates a ``None`` page text (the OCR engine may yield no text on a
    blank page) by returning ``""``.
    """
    if not text:
        return ""
    if straight_quotes:
        text = _normalize_curly_quotes(text)
    if em_dash_to_double_hyphen:
        text = _normalize_em_dash(text)
    return text


# ---------------------------------------------------------------------------
# Layout-debug env scaffolding
# ---------------------------------------------------------------------------

_LAYOUT_DEBUG_ENV = "PD_OCR_LAYOUT_DEBUG"
_LAYOUT_DEBUG_FILE_ENV = "PD_OCR_LAYOUT_DEBUG_FILE"


def setup_layout_debug_env(args, dest_dir: Path, img_stem: str) -> Path | None:
    """Configure the layout-debug env vars and return the debug file path.

    Returns ``None`` when ``--layout-debug`` was not passed. The caller is
    responsible for calling :func:`clear_layout_debug_env` after the page
    finishes (typically in a ``finally`` block).
    """
    if not args.layout_debug:
        return None
    debug_dir = Path(args.layout_debug_dir) if args.layout_debug_dir else dest_dir
    debug_dir.mkdir(parents=True, exist_ok=True)
    debug_file = debug_dir / f"{img_stem}.layout-debug.txt"
    os.environ[_LAYOUT_DEBUG_ENV] = "1"
    os.environ[_LAYOUT_DEBUG_FILE_ENV] = str(debug_file)
    return debug_file


def clear_layout_debug_env() -> None:
    """Remove the layout-debug env vars set by :func:`setup_layout_debug_env`."""
    os.environ.pop(_LAYOUT_DEBUG_ENV, None)
    os.environ.pop(_LAYOUT_DEBUG_FILE_ENV, None)


# ---------------------------------------------------------------------------
# Reorg validation reporting
# ---------------------------------------------------------------------------


def format_drops_warning(drops: list[str], source_name: str, *, max_lines: int = 20) -> list[str]:
    """Format a "reorganize dropped N words" warning into stderr-ready lines.

    Returns an empty list when ``drops`` is empty so callers can branch on it.
    The first line is the headline; subsequent lines are indented details
    (truncated at ``max_lines`` with a "... (M more)" tail when needed).
    """
    if not drops:
        return []
    lines = [f"WARNING: reorganize dropped {len(drops)} word(s) in {source_name}:"]
    for entry in drops[:max_lines]:
        lines.append(f"  {entry}")
    if len(drops) > max_lines:
        lines.append(f"  ... ({len(drops) - max_lines} more)")
    return lines


# ---------------------------------------------------------------------------
# Illustration crop selection
# ---------------------------------------------------------------------------


def iter_crop_regions(
    regions: Iterable,
    confidence_threshold: float,
    crop_types: set,
) -> Iterator[tuple[int, object]]:
    """Yield ``(1-based_index, region)`` pairs for regions worth cropping.

    Filters by region type (must be in ``crop_types``) and minimum
    confidence. The 1-based index is what the on-disk filename uses
    (``i_<stem>_01.jpg``, ``02``, …) — keeping the index and selection
    logic together avoids drift between the two.
    """
    idx = 0
    for region in regions:
        if region.type not in crop_types:
            continue
        if region.confidence < confidence_threshold:
            continue
        idx += 1
        yield idx, region
