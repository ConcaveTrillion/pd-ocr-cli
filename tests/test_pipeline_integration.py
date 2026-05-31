"""End-to-end OCR pipeline test against a pinned Hugging Face model.

Skipped by default — opt in with ``pytest --run-slow``. The first run
downloads ~166 MB of model weights from Hugging Face and caches them in
``~/.cache/huggingface/hub`` for subsequent runs.

Pinning the model revision (``PINNED_MODEL_REVISION``) gives reproducible
output for a fixed input image, so we can assert on actual recognized
tokens rather than a coarse "ran without crashing" smoke test.

The slow tests share a single session-scoped predictor. The CLI's
``_load_predictor`` seam is monkeypatched per test to hand back that
cached predictor, so ``main()`` runs in-process without reloading the
~150 MB OCR model for each case. Each test still drives ``main()``
through its full argparse / argv path so flag handling, exit codes, and
stderr/stdout messages stay covered.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from pdomain_ocr_cli import ocr_to_txt

FIXTURES_DIR = Path(__file__).parent / "fixtures"
TITLE_IMAGE = FIXTURES_DIR / "title_page_001.png"
TITLE_EXPECTED = FIXTURES_DIR / "title_page_001.expected.txt"

# Pin to a specific tag on the default HF repo so OCR output is reproducible.
PINNED_MODEL_REVISION = "v0.6"


pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def title_image_path() -> Path:
    if not TITLE_IMAGE.exists():
        pytest.skip(f"missing fixture image: {TITLE_IMAGE}")
    return TITLE_IMAGE


@pytest.fixture(scope="module")
def title_expected_text() -> str:
    if not TITLE_EXPECTED.exists():
        pytest.skip(f"missing expected text: {TITLE_EXPECTED}")
    return TITLE_EXPECTED.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def shared_predictor():
    """Build the fine-tuned DocTR predictor exactly once per pytest session.

    Uses the same code path ``main()`` takes — ``resolve_ocr_models`` to
    fetch the pinned weights, then ``_load_predictor`` to instantiate the
    detection+recognition pair. Subsequent slow tests reuse this object
    via monkeypatch instead of re-downloading or re-initialising.
    """
    args = SimpleNamespace(
        hf_repo=ocr_to_txt.DEFAULT_HF_REPO,
        model_version=PINNED_MODEL_REVISION,
        det_filename=ocr_to_txt.DEFAULT_DET_FILENAME,
        reco_filename=ocr_to_txt.DEFAULT_RECO_FILENAME,
        detection=None,
        recognition=None,
    )
    det_path, reco_path = ocr_to_txt.resolve_ocr_models(args)
    return ocr_to_txt._load_predictor(det_path, reco_path)


def _normalize_for_match(text: str) -> str:
    """Lowercase and collapse to a single-spaced word stream.

    OCR output line-wraps differently than ground truth, so direct
    equality is too brittle. Comparing whitespace-collapsed lowercase
    strings still catches all real recognition regressions while
    tolerating layout differences.
    """
    return " ".join(text.lower().split())


def _invoke_main(
    monkeypatch: pytest.MonkeyPatch,
    shared_predictor,
    image: Path,
    output_dir: Path,
    *extra_args: str,
) -> int:
    """Run ``ocr_to_txt.main()`` in-process with the shared predictor.

    Returns the ``SystemExit`` code (0 if ``main()`` returned normally).
    Replaces ``_load_predictor`` so the session-scoped predictor is
    reused — every other code path (argparse, layout resolution, the
    per-image loop, exit-code logic) runs unmocked, exactly as in a
    real ``pdomain-ocr`` invocation.
    """
    monkeypatch.setattr(ocr_to_txt, "_load_predictor", lambda det, reco: shared_predictor)
    argv = [
        "pdomain-ocr",
        "--no-update-check",
        "--model-version",
        PINNED_MODEL_REVISION,
        "--layout-model",
        "none",
        "--output-dir",
        str(output_dir),
        *extra_args,
        str(image),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    try:
        ocr_to_txt.main()
    except SystemExit as e:
        code = e.code
        return int(code) if isinstance(code, int) else 1
    return 0


def _invoke_main_default_layout(
    monkeypatch: pytest.MonkeyPatch,
    shared_predictor,
    image: Path,
    output_dir: Path,
    *extra_args: str,
) -> int:
    """Run ``ocr_to_txt.main()`` without forcing ``--layout-model none``."""
    monkeypatch.setattr(ocr_to_txt, "_load_predictor", lambda det, reco: shared_predictor)
    argv = [
        "pdomain-ocr",
        "--no-update-check",
        "--model-version",
        PINNED_MODEL_REVISION,
        "--output-dir",
        str(output_dir),
        *extra_args,
        str(image),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    try:
        ocr_to_txt.main()
    except SystemExit as e:
        code = e.code
        return int(code) if isinstance(code, int) else 1
    return 0


def test_ocr_title_page_recovers_expected_tokens(
    title_image_path: Path,
    title_expected_text: str,
    tmp_path: Path,
    shared_predictor,
    monkeypatch,
    capsys,
):
    """Pipeline should recover the major tokens from a clean title page.

    The title page reads:
        FRENCH FURNITURE
        AND DECORATION
        in the XVIIIth Century

    We assert on lowercased token presence rather than exact equality —
    the OCR engine may differ on punctuation, spacing, or roman-numeral
    glyphs, but every word should land in the output.
    """
    rc = _invoke_main(monkeypatch, shared_predictor, title_image_path, tmp_path)
    captured = capsys.readouterr()
    assert rc == 0, f"pdomain-ocr exited {rc}\nstdout:\n{captured.out}\nstderr:\n{captured.err}"

    out_txt = tmp_path / "title_page_001.txt"
    assert out_txt.exists(), f"expected output file missing: {out_txt}"

    ocr_text = out_txt.read_text(encoding="utf-8")
    assert ocr_text.strip(), "OCR output was empty"

    normalized_ocr = _normalize_for_match(ocr_text)
    expected_tokens = ["french", "furniture", "and", "decoration", "century"]
    missing = [t for t in expected_tokens if t not in normalized_ocr]
    assert not missing, (
        f"missing expected tokens {missing} in OCR output:\n{ocr_text}\n"
        f"expected ground truth:\n{title_expected_text}"
    )


def test_ocr_save_json_writes_sidecar(
    title_image_path: Path, tmp_path: Path, shared_predictor, monkeypatch, capsys
):
    """``--save-json`` produces a non-empty .json sidecar next to the .txt."""
    rc = _invoke_main(monkeypatch, shared_predictor, title_image_path, tmp_path, "--save-json")
    captured = capsys.readouterr()
    assert rc == 0, f"pdomain-ocr exited {rc}\nstdout:\n{captured.out}\nstderr:\n{captured.err}"

    out_json = tmp_path / "title_page_001.json"
    assert out_json.exists(), f"expected JSON sidecar missing: {out_json}"
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["source_lib"] == "pdomain_book_tools"
    assert payload["source_identifier"] == title_image_path.name
    assert payload["source_path"] == str(title_image_path)
    assert len(payload["pages"]) == 1


def test_ocr_no_reorg_runs_clean(
    title_image_path: Path, tmp_path: Path, shared_predictor, monkeypatch, capsys
):
    """``--no-reorg`` should also produce a usable .txt with the page tokens."""
    rc = _invoke_main(monkeypatch, shared_predictor, title_image_path, tmp_path, "--no-reorg")
    captured = capsys.readouterr()
    assert rc == 0, f"pdomain-ocr exited {rc}\nstdout:\n{captured.out}\nstderr:\n{captured.err}"
    out_txt = tmp_path / "title_page_001.txt"
    assert out_txt.exists()
    normalized = _normalize_for_match(out_txt.read_text(encoding="utf-8"))
    # Even without reorganize_page() the engine still recovers the title words.
    assert "french" in normalized
    assert "furniture" in normalized


def test_ocr_default_layout_model_runs_successfully(
    title_image_path: Path, tmp_path: Path, shared_predictor, monkeypatch, capsys
):
    rc = _invoke_main_default_layout(monkeypatch, shared_predictor, title_image_path, tmp_path)
    captured = capsys.readouterr()
    assert rc == 0, captured.out + captured.err
    assert "Layout model loaded:" in captured.out
    assert "layout:" in captured.out
    assert (tmp_path / "title_page_001.txt").exists()


def test_ocr_default_layout_debug_writes_report(
    title_image_path: Path, tmp_path: Path, shared_predictor, monkeypatch, capsys
):
    debug_dir = tmp_path / "debug"
    rc = _invoke_main_default_layout(
        monkeypatch,
        shared_predictor,
        title_image_path,
        tmp_path,
        "--layout-debug",
        "--layout-debug-dir",
        str(debug_dir),
    )
    captured = capsys.readouterr()
    assert rc == 0, captured.out + captured.err
    assert "layout-debug:" in captured.out
    assert (debug_dir / "title_page_001.layout-debug.txt").exists()


@pytest.mark.parametrize(
    ("fixture_name", "expected_tokens"),
    [
        ("title_page_001.png", ["french", "furniture", "decoration"]),
        ("two_column_page.png", ["left", "right"]),
        ("rotated_page.png", ["rotated"]),
        ("illustrated_page.png", ["illustrated", "figure"]),
    ],
)
def test_ocr_fixture_corpus_recovers_expected_tokens(
    fixture_name: str,
    expected_tokens: list[str],
    tmp_path: Path,
    shared_predictor,
    monkeypatch,
    capsys,
):
    image = FIXTURES_DIR / fixture_name
    if not image.exists():
        pytest.fail(f"missing required fixture: {image}")
    rc = _invoke_main(monkeypatch, shared_predictor, image, tmp_path)
    captured = capsys.readouterr()
    assert rc == 0, captured.out + captured.err
    text = (tmp_path / image.with_suffix(".txt").name).read_text(encoding="utf-8").lower()
    for token in expected_tokens:
        assert token in text


def test_ocr_fixture_corpus_blank_page_does_not_crash(
    tmp_path: Path, shared_predictor, monkeypatch, capsys
):
    image = FIXTURES_DIR / "blank_page.png"
    if not image.exists():
        pytest.fail(f"missing required fixture: {image}")
    rc = _invoke_main(monkeypatch, shared_predictor, image, tmp_path)
    captured = capsys.readouterr()
    assert rc == 0, captured.out + captured.err
    assert (tmp_path / "blank_page.txt").exists()


def test_ocr_save_reorganize_diagnostics_writes_full_bundle(
    title_image_path: Path, tmp_path: Path, shared_predictor, monkeypatch, capsys
):
    """``--save-json --save-reorganize-diagnostics --validate-reorg`` writes
    the post-reorganize pair plus pure-OCR + post-noise diagnostic pairs.

    Exercises the ``page.diagnostic_pure_ocr`` /
    ``diagnostic_post_noise_removal`` snapshot export path end to end and
    runs ``validate_word_preservation`` on the title page (no drops
    expected, but ``format_drops_warning`` is exercised regardless).
    """
    rc = _invoke_main(
        monkeypatch,
        shared_predictor,
        title_image_path,
        tmp_path,
        "--save-json",
        "--save-reorganize-diagnostics",
        "--validate-reorg",
    )
    captured = capsys.readouterr()
    assert rc == 0, f"pdomain-ocr exited {rc}\nstdout:\n{captured.out}\nstderr:\n{captured.err}"
    txt = tmp_path / "title_page_001.txt"
    json_ = tmp_path / "title_page_001.json"
    pure_ocr_json = tmp_path / "title_page_001.pure-ocr.json"
    pure_ocr_txt = tmp_path / "title_page_001.pure-ocr.txt"
    post_noise_json = tmp_path / "title_page_001.post-noise.json"
    post_noise_txt = tmp_path / "title_page_001.post-noise.txt"

    assert txt.exists()
    assert json_.exists()
    assert json_.stat().st_size > 0
    assert pure_ocr_json.exists()
    assert pure_ocr_json.stat().st_size > 0
    assert pure_ocr_txt.exists()
    assert post_noise_json.exists()
    assert post_noise_json.stat().st_size > 0
    assert post_noise_txt.exists()


def test_ocr_save_pre_reorg_json_alias_still_runs(
    title_image_path: Path, tmp_path: Path, shared_predictor, monkeypatch, capsys
):
    """The legacy ``--save-pre-reorg-json`` alias still triggers the same
    diagnostic export bundle (backward compatibility).
    """
    rc = _invoke_main(
        monkeypatch,
        shared_predictor,
        title_image_path,
        tmp_path,
        "--save-json",
        "--save-pre-reorg-json",
    )
    captured = capsys.readouterr()
    assert rc == 0, f"pdomain-ocr exited {rc}\nstdout:\n{captured.out}\nstderr:\n{captured.err}"
    assert (tmp_path / "title_page_001.json").exists()
    assert (tmp_path / "title_page_001.pure-ocr.json").exists()
    assert (tmp_path / "title_page_001.post-noise.json").exists()


def test_ocr_no_valid_images_exits_with_error(
    tmp_path: Path, shared_predictor, monkeypatch, capsys
):
    """A non-image input alone yields no work to do — pdomain-ocr exits 1."""
    bogus = tmp_path / "notes.txt"
    bogus.write_text("not an image", encoding="utf-8")
    rc = _invoke_main(monkeypatch, shared_predictor, bogus, tmp_path)
    captured = capsys.readouterr()
    assert rc == 1
    # Both messages land on stderr in the same run: the warning while
    # collecting (non-image file) and the final error (no valid images).
    assert "no valid image files found" in captured.err
    assert "skipping non-image file" in captured.err


def test_ocr_corrupt_image_continues_and_reports_error(
    tmp_path: Path, shared_predictor, monkeypatch, capsys
):
    """A bad image file fails per-page → exit 1 with an ERROR line on stderr.

    Exercises the per-image exception handler and the final non-zero exit
    branch (lines 494-500 / 507-508 in ocr_to_txt.main).
    """
    bad_png = tmp_path / "broken.png"
    # Valid suffix so collect_images keeps it, but the bytes are not a real PNG.
    bad_png.write_bytes(b"not really a png")
    rc = _invoke_main(monkeypatch, shared_predictor, bad_png, tmp_path)
    captured = capsys.readouterr()
    assert rc == 1
    assert "ERROR processing" in captured.err
    # The summary "Done (1 error(s))." is printed to stdout at the end.
    assert "1 error(s)" in captured.out


def test_ocr_corrupt_image_with_debug_prints_traceback(
    tmp_path: Path, shared_predictor, monkeypatch, capsys
):
    """``PD_OCR_DEBUG=1`` makes the per-page handler also print a traceback.

    Covers the ``if _env_truthy("PD_OCR_DEBUG"): traceback.print_exc()`` branch.
    """
    bad_png = tmp_path / "broken.png"
    bad_png.write_bytes(b"not really a png")

    monkeypatch.setenv("PD_OCR_DEBUG", "1")
    rc = _invoke_main(monkeypatch, shared_predictor, bad_png, tmp_path)
    captured = capsys.readouterr()
    assert rc == 1
    assert "ERROR processing" in captured.err
    # `traceback.print_exc` prints "Traceback (most recent call last):" header.
    assert "Traceback" in captured.err
