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

import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable, Iterator

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
# Diagnostic noise-drop warning + export
# ---------------------------------------------------------------------------


def _word_text(word: Any) -> str:
    """Best-effort text extraction from a ``Word`` (or test fake).

    The library ``Word`` exposes ``.text`` as a property; tests may pass
    ``SimpleNamespace`` fakes. Tolerate either, and falsy/missing text.
    """
    text = getattr(word, "text", "") or ""
    return str(text)


def format_noise_drop_warning(
    dropped_words: list[Any],
    source_name: str,
    diagnostic_flag_name: str,
    *,
    sample_size: int = 8,
) -> list[str]:
    """Format the always-on "likely noise" warning for stderr.

    ``dropped_words`` is the ``page.diagnostic_noise_dropped_words`` list
    (each entry is a ``Word`` clone with ``.text``). When non-empty, this
    builds a multi-line warning identifying the page, the count, a
    sample of dropped tokens (quoted, comma-separated), and a hint
    pointing the user at the diagnostic-export flag for the full
    breakdown. Returns ``[]`` when the list is empty.
    """
    if not dropped_words:
        return []
    count = len(dropped_words)
    samples = [_word_text(w) for w in dropped_words[:sample_size]]
    samples = [s for s in samples if s]  # drop blank tokens for readability
    sample_str = ", ".join(f'"{s}"' for s in samples) if samples else "(no text)"
    # ``+N more`` counts words beyond the sample window — not words that
    # were merely blank-filtered out of ``samples`` for display. Using
    # ``min(count, sample_size)`` keeps the suffix at zero whenever the
    # entire population already fit in the window.
    extra = f" (+{count - min(count, sample_size)} more)" if count > sample_size else ""
    return [
        (
            f"WARNING: {source_name}: dropped {count} word(s) during "
            "reorganize that look like figure-internal noise"
        ),
        f"  sample: {sample_str}{extra}",
        (
            f"  re-run with {diagnostic_flag_name} to write the full "
            "pure-OCR / post-noise / post-reorganize JSON+TXT bundle"
        ),
    ]


def write_diagnostic_snapshots(
    page: Any,
    *,
    pure_ocr_json: Path,
    pure_ocr_txt: Path,
    post_noise_json: Path,
    post_noise_txt: Path,
) -> tuple[list[Path], list[str]]:
    """Write the pure-OCR + post-noise diagnostic snapshots to disk.

    Returns ``(written_paths, notes)``. ``written_paths`` lists the
    files actually created. ``notes`` carries any user-facing messages
    (e.g. when a snapshot was unavailable because
    ``capture_diagnostics=False`` was passed at the library layer).

    Snapshots are written via ``json.dump(page.to_dict(), ...)`` rather
    than a hypothetical ``page.to_json_file`` since the library only
    exposes that helper on ``Document``. ``page.text`` powers the
    sibling ``.txt`` exports.
    """
    written: list[Path] = []
    notes: list[str] = []

    pure = getattr(page, "diagnostic_pure_ocr", None)
    if pure is not None:
        pure_ocr_json.write_text(
            json.dumps(pure.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        pure_ocr_txt.write_text(pure.text or "", encoding="utf-8")
        written.extend([pure_ocr_json, pure_ocr_txt])
    else:
        notes.append(
            "diagnostic_pure_ocr unavailable (capture_diagnostics=False); "
            "skipping pure-OCR snapshot files"
        )

    post = getattr(page, "diagnostic_post_noise_removal", None)
    if post is not None:
        post_noise_json.write_text(
            json.dumps(post.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        post_noise_txt.write_text(post.text or "", encoding="utf-8")
        written.extend([post_noise_json, post_noise_txt])
    else:
        notes.append(
            "diagnostic_post_noise_removal unavailable "
            "(capture_diagnostics=False); skipping post-noise snapshot files"
        )

    return written, notes


def diagnostic_output_paths(json_path: Path, txt_path: Path) -> dict[str, Path]:
    """Compute the diagnostic-export sibling filenames for a page.

    Given the existing post-reorganize ``.json`` / ``.txt`` paths, return
    the four new sibling paths the diagnostic export adds.
    """
    stem_json = json_path.with_suffix("")  # strip .json
    stem_txt = txt_path.with_suffix("")  # strip .txt
    return {
        "pure_ocr_json": stem_json.with_suffix(".pure-ocr.json"),
        "pure_ocr_txt": stem_txt.with_suffix(".pure-ocr.txt"),
        "post_noise_json": stem_json.with_suffix(".post-noise.json"),
        "post_noise_txt": stem_txt.with_suffix(".post-noise.txt"),
    }


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
