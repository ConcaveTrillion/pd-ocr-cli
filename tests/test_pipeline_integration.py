"""End-to-end OCR pipeline test against a pinned Hugging Face model.

Skipped by default — opt in with ``pytest --run-slow``. The first run
downloads ~166 MB of model weights from Hugging Face and caches them in
``~/.cache/huggingface/hub`` for subsequent runs.

Pinning the model revision (``PINNED_MODEL_REVISION``) gives reproducible
output for a fixed input image, so we can assert on actual recognized
tokens rather than a coarse "ran without crashing" smoke test.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
TITLE_IMAGE = FIXTURES_DIR / "title_page_001.png"
TITLE_EXPECTED = FIXTURES_DIR / "title_page_001.expected.txt"

# Pin to a specific tag on the default HF repo so OCR output is reproducible.
PINNED_MODEL_REVISION = "v0.6"

# Coverage config lives at the repo root next to pyproject.toml. With
# `parallel = true` set there, pytest-cov auto-combines child-process
# coverage into the parent run when the child sees this env var.
PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


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


def _normalize_for_match(text: str) -> str:
    """Lowercase and collapse to a single-spaced word stream.

    OCR output line-wraps differently than ground truth, so direct
    equality is too brittle. Comparing whitespace-collapsed lowercase
    strings still catches all real recognition regressions while
    tolerating layout differences.
    """
    return " ".join(text.lower().split())


def _run_pd_ocr(image: Path, output_dir: Path, *extra_args: str) -> subprocess.CompletedProcess:
    """Invoke the CLI as a subprocess in the current venv.

    Sets ``COVERAGE_PROCESS_START`` so the child also records coverage —
    pytest-cov merges the per-process datafiles at session end.
    """
    cmd = [
        sys.executable,
        "-m",
        "pd_ocr_cli.ocr_to_txt",
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
    env = {**os.environ, "COVERAGE_PROCESS_START": str(PYPROJECT)}
    return subprocess.run(cmd, capture_output=True, text=True, timeout=600, env=env)


def test_ocr_title_page_recovers_expected_tokens(
    title_image_path: Path, title_expected_text: str, tmp_path: Path
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
    result = _run_pd_ocr(title_image_path, tmp_path)
    assert result.returncode == 0, (
        f"pd-ocr exited {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

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


def test_ocr_save_json_writes_sidecar(title_image_path: Path, tmp_path: Path):
    """``--save-json`` produces a non-empty .json sidecar next to the .txt."""
    result = _run_pd_ocr(title_image_path, tmp_path, "--save-json")
    assert result.returncode == 0, (
        f"pd-ocr exited {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

    out_json = tmp_path / "title_page_001.json"
    assert out_json.exists(), f"expected JSON sidecar missing: {out_json}"
    assert out_json.stat().st_size > 0, "JSON sidecar was empty"


def test_ocr_no_reorg_runs_clean(title_image_path: Path, tmp_path: Path):
    """``--no-reorg`` should also produce a usable .txt with the page tokens."""
    result = _run_pd_ocr(title_image_path, tmp_path, "--no-reorg")
    assert result.returncode == 0, (
        f"pd-ocr exited {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    out_txt = tmp_path / "title_page_001.txt"
    assert out_txt.exists()
    normalized = _normalize_for_match(out_txt.read_text(encoding="utf-8"))
    # Even without reorganize_page() the engine still recovers the title words.
    assert "french" in normalized
    assert "furniture" in normalized


def test_ocr_save_reorganize_diagnostics_writes_full_bundle(title_image_path: Path, tmp_path: Path):
    """``--save-json --save-reorganize-diagnostics --validate-reorg`` writes
    the post-reorganize pair plus pure-OCR + post-noise diagnostic pairs.

    Exercises the ``page.diagnostic_pure_ocr`` /
    ``diagnostic_post_noise_removal`` snapshot export path end to end and
    runs ``validate_word_preservation`` on the title page (no drops
    expected, but ``format_drops_warning`` is exercised regardless).
    """
    result = _run_pd_ocr(
        title_image_path,
        tmp_path,
        "--save-json",
        "--save-reorganize-diagnostics",
        "--validate-reorg",
    )
    assert result.returncode == 0, (
        f"pd-ocr exited {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    txt = tmp_path / "title_page_001.txt"
    json_ = tmp_path / "title_page_001.json"
    pure_ocr_json = tmp_path / "title_page_001.pure-ocr.json"
    pure_ocr_txt = tmp_path / "title_page_001.pure-ocr.txt"
    post_noise_json = tmp_path / "title_page_001.post-noise.json"
    post_noise_txt = tmp_path / "title_page_001.post-noise.txt"

    assert txt.exists()
    assert json_.exists() and json_.stat().st_size > 0
    assert pure_ocr_json.exists() and pure_ocr_json.stat().st_size > 0
    assert pure_ocr_txt.exists()
    assert post_noise_json.exists() and post_noise_json.stat().st_size > 0
    assert post_noise_txt.exists()


def test_ocr_save_pre_reorg_json_alias_still_runs(title_image_path: Path, tmp_path: Path):
    """The legacy ``--save-pre-reorg-json`` alias still triggers the same
    diagnostic export bundle (backward compatibility).
    """
    result = _run_pd_ocr(
        title_image_path,
        tmp_path,
        "--save-json",
        "--save-pre-reorg-json",
    )
    assert result.returncode == 0, (
        f"pd-ocr exited {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert (tmp_path / "title_page_001.json").exists()
    assert (tmp_path / "title_page_001.pure-ocr.json").exists()
    assert (tmp_path / "title_page_001.post-noise.json").exists()


def test_ocr_no_valid_images_exits_with_error(tmp_path: Path):
    """A non-image input alone yields no work to do — pd-ocr exits 1."""
    bogus = tmp_path / "notes.txt"
    bogus.write_text("not an image", encoding="utf-8")
    result = _run_pd_ocr(bogus, tmp_path)
    assert result.returncode == 1
    # Both messages land on stderr in the same run: the warning while
    # collecting (non-image file) and the final error (no valid images).
    assert "no valid image files found" in result.stderr
    assert "skipping non-image file" in result.stderr


def test_ocr_corrupt_image_continues_and_reports_error(tmp_path: Path):
    """A bad image file fails per-page → exit 1 with an ERROR line on stderr.

    Exercises the per-image exception handler and the final non-zero exit
    branch (lines 494-500 / 507-508 in ocr_to_txt.main).
    """
    bad_png = tmp_path / "broken.png"
    # Valid suffix so collect_images keeps it, but the bytes are not a real PNG.
    bad_png.write_bytes(b"not really a png")
    result = _run_pd_ocr(bad_png, tmp_path)
    assert result.returncode == 1
    assert "ERROR processing" in result.stderr
    # The summary "Done (1 error(s))." is printed to stdout at the end.
    assert "1 error(s)" in result.stdout


def test_ocr_corrupt_image_with_debug_prints_traceback(tmp_path: Path):
    """``PD_OCR_DEBUG=1`` makes the per-page handler also print a traceback.

    Covers the ``if _env_truthy("PD_OCR_DEBUG"): traceback.print_exc()`` branch.
    """
    bad_png = tmp_path / "broken.png"
    bad_png.write_bytes(b"not really a png")

    cmd = [
        sys.executable,
        "-m",
        "pd_ocr_cli.ocr_to_txt",
        "--no-update-check",
        "--model-version",
        PINNED_MODEL_REVISION,
        "--layout-model",
        "none",
        "--output-dir",
        str(tmp_path),
        str(bad_png),
    ]
    env = {
        **os.environ,
        "COVERAGE_PROCESS_START": str(PYPROJECT),
        "PD_OCR_DEBUG": "1",
    }
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, env=env)
    assert result.returncode == 1
    assert "ERROR processing" in result.stderr
    # `traceback.print_exc` prints "Traceback (most recent call last):" header.
    assert "Traceback" in result.stderr
