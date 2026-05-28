"""Tests for ``--batch-pages`` / ``run_doctr_batch`` integration.

TDD test file written *before* implementation.

These tests verify:
1. Chunking: 5 images with ``--batch-pages 2`` calls ``_run_doctr_batch``
   with chunk sizes [2, 2, 1] in order, and all pages appear in output in order.
2. Per-page post-processing runs per page (reorganize_page called per page).
3. Output-equivalence: same text regardless of batch size.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from pdomain_ocr_cli import ocr_to_txt

FIXTURES_DIR = Path(__file__).parent / "fixtures"
TITLE_IMAGE = FIXTURES_DIR / "title_page_001.png"


# ---------------------------------------------------------------------------
# Fake Page that records calls
# ---------------------------------------------------------------------------


class _FakePage:
    def __init__(self, text: str = "FAKE TEXT"):
        self.text = text
        self.words = []
        self.reorganize_page = MagicMock(return_value=None)
        self.diagnostic_pure_ocr = None
        self.diagnostic_post_noise_removal = None
        self.diagnostic_noise_dropped_words = []
        self.diagnostic_noise_dropped_count = 0


# ---------------------------------------------------------------------------
# Shared patching helper
# ---------------------------------------------------------------------------


def _patch_common(monkeypatch, tmp_path, *, batch_page_texts: list[str] | None = None):
    """Wire up all heavy dependencies and a recording ``_run_doctr_batch``.

    ``batch_page_texts``: list of texts, one per image in input order.
    Defaults to ``["PAGE_N"]`` for each position.

    Returns a ``SimpleNamespace`` with:
    - ``batch_calls``: recorded calls to ``_run_doctr_batch``
    - ``batch_page_texts``: the texts list used
    - ``fake_predictor``: the predictor object passed through
    """
    if not TITLE_IMAGE.exists():
        pytest.skip(f"missing fixture image: {TITLE_IMAGE}")

    # Disable update check / nudge
    monkeypatch.setattr(ocr_to_txt, "_check_for_update", lambda: None)
    monkeypatch.setattr(ocr_to_txt, "_start_update_check_thread", lambda disabled: None)
    monkeypatch.setattr(ocr_to_txt, "_should_nudge_gpu_install", lambda: False)

    # Fake model paths
    fake_det = tmp_path / "fake-det.pt"
    fake_reco = tmp_path / "fake-reco.pt"
    fake_det.write_bytes(b"")
    fake_reco.write_bytes(b"")

    monkeypatch.setattr(ocr_to_txt, "resolve_ocr_models", lambda args: (fake_det, fake_reco))
    monkeypatch.setattr(
        ocr_to_txt,
        "resolve_layout_source",
        lambda args: ("fake/layout-repo", "v0", "fake/layout-repo@v0"),
    )
    monkeypatch.setattr(ocr_to_txt, "prefetch_layout_files", lambda repo, rev: None)
    monkeypatch.setattr(ocr_to_txt, "_detect_torch_device", lambda: "cpu")

    fake_predictor = object()
    monkeypatch.setattr(ocr_to_txt, "_load_predictor", lambda det, reco: fake_predictor)

    monkeypatch.setattr(
        ocr_to_txt,
        "_load_layout_detector",
        lambda args, device: MagicMock(
            detect=MagicMock(return_value=SimpleNamespace(regions=[], inference_ms=1))
        ),
    )
    monkeypatch.setattr(
        ocr_to_txt,
        "_load_validate_word_preservation",
        lambda: MagicMock(return_value=[]),
    )

    # Track calls to _run_doctr_batch and return appropriate fake Pages
    batch_calls: list[dict] = []
    page_counter = [0]

    texts = batch_page_texts or []

    def _fake_run_doctr_batch(
        images, *, predictor, device, build_smaller=None, source_identifiers=None
    ):
        chunk_size = len(images)
        chunk_pages = []
        for _ in range(chunk_size):
            idx = page_counter[0]
            text = texts[idx] if idx < len(texts) else f"PAGE_{idx}"
            chunk_pages.append(_FakePage(text=text))
            page_counter[0] += 1
        batch_calls.append(
            {
                "chunk_size": chunk_size,
                "predictor": predictor,
                "device": device,
                "source_identifiers": source_identifiers,
            }
        )
        return chunk_pages

    monkeypatch.setattr(ocr_to_txt, "_run_doctr_batch", _fake_run_doctr_batch)
    # Also mock _pick_device since it's the pdomain-ops one
    monkeypatch.setattr(ocr_to_txt, "_pick_device", lambda: "cpu")

    return SimpleNamespace(
        batch_calls=batch_calls,
        batch_page_texts=texts,
        fake_predictor=fake_predictor,
        det_path=fake_det,
        reco_path=fake_reco,
    )


def _run_main(monkeypatch, *argv: str) -> None:
    monkeypatch.setattr(sys, "argv", ["pd-ocr", *argv])
    ocr_to_txt.main()


# ---------------------------------------------------------------------------
# Chunking test
# ---------------------------------------------------------------------------


def test_batch_pages_chunking_calls_run_doctr_batch_with_correct_chunk_sizes(monkeypatch, tmp_path):
    """5 images with ``--batch-pages 2`` -> run_doctr_batch called 3 times.

    Chunk sizes must be [2, 2, 1] and all 5 pages must appear in output.
    """
    # Create 5 fake images
    imgs = []
    for i in range(5):
        img = tmp_path / f"page_{i:02d}.png"
        shutil.copy(TITLE_IMAGE, img)
        imgs.append(img)

    out = tmp_path / "out"
    texts = [f"TEXT_{i}" for i in range(5)]
    ns = _patch_common(monkeypatch, tmp_path, batch_page_texts=texts)

    _run_main(
        monkeypatch,
        "--no-update-check",
        "--layout-model",
        "none",
        "--batch-pages",
        "2",
        "-o",
        str(out),
        *[str(img) for img in imgs],
    )

    # Three batches: [2, 2, 1]
    assert len(ns.batch_calls) == 3
    assert ns.batch_calls[0]["chunk_size"] == 2
    assert ns.batch_calls[1]["chunk_size"] == 2
    assert ns.batch_calls[2]["chunk_size"] == 1

    # All pages appear in output in order
    for i, img in enumerate(imgs):
        txt_path = out / f"{img.stem}.txt"
        assert txt_path.exists(), f"missing output for {img.stem}"
        assert txt_path.read_text() == f"TEXT_{i}", f"wrong text for {img.stem}"


def test_batch_pages_predictor_passed_through(monkeypatch, tmp_path):
    """The caller-built predictor must be forwarded to every run_doctr_batch call."""
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"
    ns = _patch_common(monkeypatch, tmp_path)

    _run_main(
        monkeypatch,
        "--no-update-check",
        "--layout-model",
        "none",
        "--batch-pages",
        "4",
        "-o",
        str(out),
        str(img),
    )

    assert len(ns.batch_calls) == 1
    assert ns.batch_calls[0]["predictor"] is ns.fake_predictor


def test_batch_pages_reorganize_called_per_page(monkeypatch, tmp_path):
    """reorganize_page must be called once per page, not once per batch."""
    imgs = []
    for i in range(3):
        img = tmp_path / f"page_{i:02d}.png"
        shutil.copy(TITLE_IMAGE, img)
        imgs.append(img)

    out = tmp_path / "out"
    _patch_common(monkeypatch, tmp_path, batch_page_texts=["T0", "T1", "T2"])

    # Track individual fake pages returned by batches
    returned_pages: list[_FakePage] = []
    real_run_batch = ocr_to_txt._run_doctr_batch  # type: ignore[attr-defined]  # set by monkeypatch

    def _recording_batch(images, *, predictor, device, build_smaller=None, source_identifiers=None):
        pages = real_run_batch(
            images,
            predictor=predictor,
            device=device,
            build_smaller=build_smaller,
            source_identifiers=source_identifiers,
        )
        returned_pages.extend(pages)
        return pages

    monkeypatch.setattr(ocr_to_txt, "_run_doctr_batch", _recording_batch)

    _run_main(
        monkeypatch,
        "--no-update-check",
        "--layout-model",
        "none",
        "--batch-pages",
        "2",
        "-o",
        str(out),
        *[str(img) for img in imgs],
    )

    # 3 pages -> reorganize_page called once per page
    assert len(returned_pages) == 3
    for page in returned_pages:
        page.reorganize_page.assert_called_once()


# ---------------------------------------------------------------------------
# Output equivalence
# ---------------------------------------------------------------------------


def test_batch_pages_equivalence_different_sizes(monkeypatch, tmp_path):
    """Same output text regardless of --batch-pages 1 vs 4."""
    imgs = []
    for i in range(4):
        img = tmp_path / f"page_{i:02d}.png"
        shutil.copy(TITLE_IMAGE, img)
        imgs.append(img)

    texts = [f"CONTENT_{i}" for i in range(4)]

    # Run with batch_pages=1
    out1 = tmp_path / "out1"
    ns1 = _patch_common(monkeypatch, tmp_path, batch_page_texts=texts)
    _run_main(
        monkeypatch,
        "--no-update-check",
        "--layout-model",
        "none",
        "--batch-pages",
        "1",
        "-o",
        str(out1),
        *[str(img) for img in imgs],
    )

    # Run with batch_pages=4
    out4 = tmp_path / "out4"
    ns4 = _patch_common(monkeypatch, tmp_path, batch_page_texts=texts)
    _run_main(
        monkeypatch,
        "--no-update-check",
        "--layout-model",
        "none",
        "--batch-pages",
        "4",
        "-o",
        str(out4),
        *[str(img) for img in imgs],
    )

    for img in imgs:
        t1 = (out1 / f"{img.stem}.txt").read_text()
        t4 = (out4 / f"{img.stem}.txt").read_text()
        assert t1 == t4, f"text differs for {img.stem}: {t1!r} vs {t4!r}"

    # batch_pages=1 -> 4 separate batches; batch_pages=4 -> 1 batch
    assert len(ns1.batch_calls) == 4
    assert len(ns4.batch_calls) == 1


# ---------------------------------------------------------------------------
# Default batch-pages value
# ---------------------------------------------------------------------------


def test_batch_pages_default_is_4(monkeypatch, tmp_path):
    """With no ``--batch-pages``, default=4 means a single batch for <=4 images."""
    imgs = []
    for i in range(3):
        img = tmp_path / f"page_{i:02d}.png"
        shutil.copy(TITLE_IMAGE, img)
        imgs.append(img)

    out = tmp_path / "out"
    ns = _patch_common(monkeypatch, tmp_path, batch_page_texts=["A", "B", "C"])

    _run_main(
        monkeypatch,
        "--no-update-check",
        "--layout-model",
        "none",
        "-o",
        str(out),
        *[str(img) for img in imgs],
    )

    # 3 images, default batch=4 -> single call with all 3
    assert len(ns.batch_calls) == 1
    assert ns.batch_calls[0]["chunk_size"] == 3
