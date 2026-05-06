"""Argparse coverage beyond ``test_update_check_bypass``.

Confirms defaults, accepted choices, alias handling, and required-input
behavior for the ``pd-ocr`` CLI.
"""

from unittest.mock import patch

import pytest

from pd_ocr_cli._hf_models import (
    DEFAULT_DET_FILENAME,
    DEFAULT_HF_REPO,
    DEFAULT_RECO_FILENAME,
)
from pd_ocr_cli.ocr_to_txt import parse_args


def _argv(*args):
    return patch("sys.argv", ["pd-ocr", *args])


def test_defaults_with_single_input():
    with _argv("page.png"):
        args = parse_args()

    assert args.inputs == ["page.png"]
    assert args.output_dir is None
    assert args.save_json is False
    assert args.no_reorg is False
    assert args.save_reorganize_diagnostics is False
    assert args.validate_reorg is False
    assert args.experimental_drop_layout_words is False
    assert args.recursive is False
    assert args.straight_quotes is False
    assert args.em_dash_to_double_hyphen is False
    assert args.extract_illustrations is False
    assert args.layout_debug is False
    assert args.layout_debug_dir is None
    assert args.layout_model == "pp-doclayout-plus-l"
    assert args.layout_checkpoint is None
    assert args.layout_confidence == 0.5
    assert args.hf_repo == DEFAULT_HF_REPO
    assert args.model_version is None
    assert args.det_filename == DEFAULT_DET_FILENAME
    assert args.reco_filename == DEFAULT_RECO_FILENAME
    assert args.detection is None
    assert args.recognition is None


def test_inputs_required():
    with _argv(), pytest.raises(SystemExit):
        parse_args()


def test_multiple_inputs_collected():
    with _argv("a.png", "b.png", "dir/"):
        args = parse_args()
    assert args.inputs == ["a.png", "b.png", "dir/"]


@pytest.mark.parametrize("flag", ["-r", "-R", "--recursive"])
def test_recursive_aliases(flag):
    with _argv(flag, "imgs/"):
        args = parse_args()
    assert args.recursive is True


@pytest.mark.parametrize("flag", ["-sq", "--straight-quotes"])
def test_straight_quotes_aliases(flag):
    with _argv(flag, "page.png"):
        args = parse_args()
    assert args.straight_quotes is True


@pytest.mark.parametrize("flag", ["-ed", "--em-dash-to-double-hyphen"])
def test_em_dash_aliases(flag):
    with _argv(flag, "page.png"):
        args = parse_args()
    assert args.em_dash_to_double_hyphen is True


@pytest.mark.parametrize("choice", ["none", "contour", "pp-doclayout-plus-l"])
def test_layout_model_choices_accepted(choice):
    with _argv("--layout-model", choice, "page.png"):
        args = parse_args()
    assert args.layout_model == choice


def test_layout_model_invalid_choice_rejected():
    with _argv("--layout-model", "fancy-model", "page.png"), pytest.raises(SystemExit):
        parse_args()


def test_layout_confidence_parsed_as_float():
    with _argv("--layout-confidence", "0.25", "page.png"):
        args = parse_args()
    assert args.layout_confidence == pytest.approx(0.25)


@pytest.mark.parametrize("boundary", ["0", "0.0", "1", "1.0"])
def test_layout_confidence_accepts_inclusive_bounds(boundary):
    with _argv("--layout-confidence", boundary, "page.png"):
        args = parse_args()
    assert args.layout_confidence == pytest.approx(float(boundary))


@pytest.mark.parametrize(
    "bad",
    ["nan", "NaN", "inf", "-inf", "Infinity", "-1", "-0.0001", "1.0001", "50", "not-a-number"],
)
def test_layout_confidence_rejects_out_of_range_or_nonfinite(bad):
    """B21: argparse must reject nan/inf/negative/>1 with a clear error."""
    with _argv("--layout-confidence", bad, "page.png"), pytest.raises(SystemExit):
        parse_args()


def test_output_dir_alias_short():
    with _argv("-o", "out/", "page.png"):
        args = parse_args()
    assert args.output_dir == "out/"


def test_output_dir_alias_long():
    with _argv("--output-dir", "out/", "page.png"):
        args = parse_args()
    assert args.output_dir == "out/"


def test_save_json_and_reorganize_diagnostics_flag_new_name():
    with _argv("--save-json", "--save-reorganize-diagnostics", "page.png"):
        args = parse_args()
    assert args.save_json is True
    assert args.save_reorganize_diagnostics is True


def test_save_json_and_pre_reorg_alias_still_accepted():
    """The old --save-pre-reorg-json name maps to save_reorganize_diagnostics."""
    with _argv("--save-json", "--save-pre-reorg-json", "page.png"):
        args = parse_args()
    assert args.save_json is True
    assert args.save_reorganize_diagnostics is True


def test_no_reorg_and_validate_reorg_independent():
    with _argv("--no-reorg", "--validate-reorg", "page.png"):
        args = parse_args()
    assert args.no_reorg is True
    assert args.validate_reorg is True


def test_experimental_drop_layout_words_flag():
    """Parsed when present; defaults False (verified in test_defaults_with_single_input)."""
    with _argv("--experimental-drop-layout-words", "page.png"):
        args = parse_args()
    assert args.experimental_drop_layout_words is True


@pytest.mark.parametrize("flag", ["--experimental-drop-layout-words", "--edl"])
def test_experimental_drop_layout_words_aliases(flag):
    """Both the long form and the ``--edl`` alias parse identically.

    Note: argparse treats ``--edl`` as a long-form option string. A
    single-dash ``-edl`` would be interpreted by argparse as a combined
    short-flag sequence and would silently misbehave once any of
    ``-e``, ``-d``, or ``-l`` is also defined (``-d`` already exists
    as the short for ``--detection``), so the alias is intentionally
    spelled with two dashes.
    """
    with _argv(flag, "page.png"):
        args = parse_args()
    assert args.experimental_drop_layout_words is True
    # Sanity: every other flag still has its default value, so the alias
    # only flips the one attribute it's wired to.
    assert args.no_reorg is False
    assert args.save_json is False
    assert args.validate_reorg is False


def test_extract_illustrations_flag():
    with _argv("--extract-illustrations", "page.png"):
        args = parse_args()
    assert args.extract_illustrations is True


def test_layout_debug_with_explicit_dir():
    with _argv("--layout-debug", "--layout-debug-dir", "dbg/", "page.png"):
        args = parse_args()
    assert args.layout_debug is True
    assert args.layout_debug_dir == "dbg/"


def test_local_pt_model_paths():
    with _argv("--detection", "det.pt", "--recognition", "rec.pt", "page.png"):
        args = parse_args()
    assert args.detection == "det.pt"
    assert args.recognition == "rec.pt"


def test_short_local_pt_model_aliases():
    with _argv("-d", "det.pt", "-g", "rec.pt", "page.png"):
        args = parse_args()
    assert args.detection == "det.pt"
    assert args.recognition == "rec.pt"


def test_hf_repo_and_model_version():
    with _argv("--hf-repo", "user/repo", "--model-version", "v1.2.3", "page.png"):
        args = parse_args()
    assert args.hf_repo == "user/repo"
    assert args.model_version == "v1.2.3"


def test_custom_det_and_reco_filenames():
    with _argv(
        "--det-filename",
        "alt/det.pt",
        "--reco-filename",
        "alt/rec.pt",
        "page.png",
    ):
        args = parse_args()
    assert args.det_filename == "alt/det.pt"
    assert args.reco_filename == "alt/rec.pt"
