"""Tests for ``--batch-pages`` / ``run_doctr_batch`` integration.

These tests verify:
1. Chunking: 5 images with ``--batch-pages 2`` calls ``_run_doctr_batch``
   with chunk sizes [2, 2, 1] in order, and all pages appear in output in order.
2. Per-page post-processing runs per page (reorganize_page called per page).
3. Output-equivalence: same text regardless of batch size.
"""

from __future__ import annotations

import pytest

from pdomain_ocr_cli import ocr_to_txt


def test_batch_pages_chunking_calls_run_doctr_batch_with_correct_chunk_sizes(
    mock_heavy_deps, run_main, make_images, tmp_path
):
    """5 images with ``--batch-pages 2`` -> run_doctr_batch called 3 times.

    Chunk sizes must be [2, 2, 1] and all 5 pages must appear in output.
    """
    imgs = make_images(5)
    out = tmp_path / "out"
    texts = [f"TEXT_{i}" for i in range(5)]
    ns = mock_heavy_deps(texts=texts)
    run_main(
        "--no-update-check",
        "--layout-model",
        "none",
        "--batch-pages",
        "2",
        "-o",
        str(out),
        *[str(i) for i in imgs],
    )
    assert [c["chunk_size"] for c in ns.batch_calls] == [2, 2, 1]
    for i, img in enumerate(imgs):
        assert (out / f"{img.stem}.txt").read_text() == f"TEXT_{i}"


def test_batch_pages_predictor_passed_through(mock_heavy_deps, run_main, make_images, tmp_path):
    """The caller-built predictor must be forwarded to every run_doctr_batch call."""
    imgs = make_images(1)
    out = tmp_path / "out"
    ns = mock_heavy_deps()
    run_main(
        "--no-update-check",
        "--layout-model",
        "none",
        "--batch-pages",
        "4",
        "-o",
        str(out),
        str(imgs[0]),
    )
    assert len(ns.batch_calls) == 1
    assert ns.batch_calls[0]["predictor"] is ns.predictor


def test_batch_pages_reorganize_called_per_page(mock_heavy_deps, run_main, make_images, tmp_path):
    """reorganize_page must be called once per page, not once per batch."""
    imgs = make_images(3)
    out = tmp_path / "out"
    ns = mock_heavy_deps(texts=["T0", "T1", "T2"])
    run_main(
        "--no-update-check",
        "--layout-model",
        "none",
        "--batch-pages",
        "2",
        "-o",
        str(out),
        *[str(i) for i in imgs],
    )
    assert len(ns.captured_pages) == 3
    for page in ns.captured_pages:
        page.reorganize_page.assert_called_once()


def test_batch_pages_equivalence_different_sizes(mock_heavy_deps, run_main, make_images, tmp_path):
    """Same output text regardless of --batch-pages 1 vs 4."""
    imgs = make_images(4)
    texts = [f"CONTENT_{i}" for i in range(4)]

    # Run with batch_pages=1
    out1 = tmp_path / "out1"
    ns1 = mock_heavy_deps(texts=texts)
    run_main(
        "--no-update-check",
        "--layout-model",
        "none",
        "--batch-pages",
        "1",
        "-o",
        str(out1),
        *[str(i) for i in imgs],
    )

    # Run with batch_pages=4
    out4 = tmp_path / "out4"
    ns4 = mock_heavy_deps(texts=texts)
    run_main(
        "--no-update-check",
        "--layout-model",
        "none",
        "--batch-pages",
        "4",
        "-o",
        str(out4),
        *[str(i) for i in imgs],
    )

    for img in imgs:
        t1 = (out1 / f"{img.stem}.txt").read_text()
        t4 = (out4 / f"{img.stem}.txt").read_text()
        assert t1 == t4, f"text differs for {img.stem}: {t1!r} vs {t4!r}"

    # batch_pages=1 -> 4 separate batches; batch_pages=4 -> 1 batch
    assert len(ns1.batch_calls) == 4
    assert len(ns4.batch_calls) == 1


def test_batch_pages_default_is_4(mock_heavy_deps, run_main, make_images, tmp_path):
    """With no ``--batch-pages``, default=4 means a single batch for <=4 images."""
    imgs = make_images(3)
    out = tmp_path / "out"
    ns = mock_heavy_deps(texts=["A", "B", "C"])
    run_main(
        "--no-update-check",
        "--layout-model",
        "none",
        "-o",
        str(out),
        *[str(i) for i in imgs],
    )
    assert len(ns.batch_calls) == 1
    assert ns.batch_calls[0]["chunk_size"] == 3


def test_main_rejects_flat_output_collision_before_model_resolution(
    monkeypatch, run_main, tmp_path, capsys
):
    a = tmp_path / "a" / "page.png"
    b = tmp_path / "b" / "page.png"
    a.parent.mkdir()
    b.parent.mkdir()
    a.write_bytes(b"not decoded")
    b.write_bytes(b"not decoded")
    out = tmp_path / "out"

    monkeypatch.setattr(ocr_to_txt, "_IS_IMAGE_FILE", lambda path: path.suffix == ".png")

    def fail_model_resolution(args):
        raise AssertionError("model resolution should not run")

    monkeypatch.setattr(ocr_to_txt, "resolve_ocr_models", fail_model_resolution)

    with pytest.raises(SystemExit) as exc_info:
        run_main("--no-update-check", "-o", str(out), str(a), str(b))

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "output path collision" in err
    assert str(out / "page.txt") in err
