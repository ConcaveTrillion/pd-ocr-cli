from __future__ import annotations

from pathlib import Path

import pytest

from pdomain_ocr_cli._batch_plan import BatchPlanError, build_batch_plan, positive_int


def _is_image(path: Path) -> bool:
    return path.suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}


def test_positive_int_rejects_zero_and_negative() -> None:
    with pytest.raises(ValueError, match="positive integer"):
        positive_int("0")
    with pytest.raises(ValueError, match="positive integer"):
        positive_int("-1")
    assert positive_int("2") == 2


def test_batch_plan_rejects_flat_output_collisions(tmp_path: Path) -> None:
    a = tmp_path / "a" / "page.png"
    b = tmp_path / "b" / "page.png"
    a.parent.mkdir()
    b.parent.mkdir()
    a.write_bytes(b"png")
    b.write_bytes(b"png")

    with pytest.raises(BatchPlanError, match="output path collision"):
        build_batch_plan(
            inputs=[str(a), str(b)],
            recursive=False,
            output_dir=tmp_path / "out",
            is_image_file=_is_image,
            batch_pages=4,
        )


def test_batch_plan_rejects_layout_debug_collisions(tmp_path: Path) -> None:
    a = tmp_path / "a" / "page.png"
    b = tmp_path / "b" / "page.png"
    a.parent.mkdir()
    b.parent.mkdir()
    a.write_bytes(b"png")
    b.write_bytes(b"png")

    with pytest.raises(BatchPlanError, match="layout-debug"):
        build_batch_plan(
            inputs=[str(a), str(b)],
            recursive=False,
            output_dir=None,
            is_image_file=_is_image,
            batch_pages=4,
            layout_debug=True,
            layout_debug_dir=tmp_path / "debug",
        )


def test_batch_plan_rejects_default_layout_debug_artifact_collisions(
    tmp_path: Path,
) -> None:
    a = tmp_path / "a" / "page.png"
    b = tmp_path / "b" / "page.layout-debug.png"
    a.parent.mkdir()
    b.parent.mkdir()
    a.write_bytes(b"png")
    b.write_bytes(b"png")

    with pytest.raises(BatchPlanError, match="output path collision"):
        build_batch_plan(
            inputs=[str(a), str(b)],
            recursive=False,
            output_dir=tmp_path / "out",
            is_image_file=_is_image,
            batch_pages=4,
            layout_debug=True,
        )


def test_batch_plan_rejects_same_artifact_with_different_path_spelling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "run"
    root.mkdir()
    a = root / "a" / "page.png"
    b = root / "b" / "page.layout-debug.png"
    a.parent.mkdir()
    b.parent.mkdir()
    a.write_bytes(b"png")
    b.write_bytes(b"png")
    out = root / "out"
    monkeypatch.chdir(root)

    with pytest.raises(BatchPlanError, match="output path collision"):
        build_batch_plan(
            inputs=[str(a), str(b)],
            recursive=False,
            output_dir=out,
            is_image_file=_is_image,
            batch_pages=4,
            layout_debug=True,
            layout_debug_dir=Path("out"),
        )


def test_batch_plan_precomputes_mirrored_jobs(tmp_path: Path) -> None:
    root = tmp_path / "images"
    nested = root / "ch1"
    nested.mkdir(parents=True)
    img = nested / "page.png"
    img.write_bytes(b"png")
    out = tmp_path / "out"

    plan = build_batch_plan(
        inputs=[str(root)],
        recursive=True,
        output_dir=out,
        is_image_file=_is_image,
        batch_pages=2,
    )

    assert len(plan.jobs) == 1
    assert plan.jobs[0].image_path == img
    assert plan.jobs[0].dest_dir == out / "ch1"
    assert plan.jobs[0].txt_path == out / "ch1" / "page.txt"
    assert plan.jobs[0].json_path == out / "ch1" / "page.json"
    assert plan.mirror_root == root.resolve()
    assert plan.chunk_size == 2


def test_batch_plan_rejects_invalid_batch_size() -> None:
    with pytest.raises(BatchPlanError, match="--batch-pages must be >= 1"):
        build_batch_plan(
            inputs=["unused.png"],
            recursive=False,
            output_dir=None,
            is_image_file=_is_image,
            batch_pages=0,
        )
