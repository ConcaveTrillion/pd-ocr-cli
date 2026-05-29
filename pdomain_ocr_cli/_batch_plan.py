from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


class BatchPlanError(ValueError):
    pass


@dataclass(frozen=True)
class PageJob:
    image_path: Path
    dest_dir: Path
    txt_path: Path
    json_path: Path


@dataclass(frozen=True)
class BatchPlan:
    jobs: tuple[PageJob, ...]
    mirror_root: Path | None
    chunk_size: int


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"expected a positive integer; got {value!r}") from exc
    if parsed < 1:
        raise ValueError(f"expected a positive integer; got {value!r}")
    return parsed


def collect_images(
    inputs: list[str],
    recursive: bool,
    *,
    is_image_file: Callable[[Path], bool],
) -> list[Path]:
    images: list[Path] = []
    seen: set[Path] = set()

    def add(path: Path) -> None:
        key = path.resolve()
        if key in seen:
            return
        seen.add(key)
        images.append(path)

    for raw in inputs:
        path = Path(raw)
        if path.is_file():
            if is_image_file(path):
                add(path)
            else:
                print(f"WARNING: skipping non-image file: {path}", file=sys.stderr)  # noqa: T201
        elif path.is_dir():
            pattern = "**/*" if recursive else "*"
            for child in sorted(path.glob(pattern)):
                if child.is_file() and is_image_file(child):
                    add(child)
        else:
            print(f"WARNING: skipping missing path: {path}", file=sys.stderr)  # noqa: T201
    return images


def compute_mirror_root(inputs: list[str], output_dir: Path | None) -> Path | None:
    if output_dir is None:
        return None
    input_dirs = [Path(raw).resolve() for raw in inputs if Path(raw).is_dir()]
    if not input_dirs:
        return None
    try:
        return Path(os.path.commonpath(input_dirs))
    except ValueError:
        print(  # noqa: T201
            "WARNING: input directories have no common ancestor; writing outputs flat under --output-dir instead of mirroring.",
            file=sys.stderr,
        )
        return None


def resolve_dest_dir(
    image_path: Path,
    output_dir: Path | None,
    mirror_root: Path | None,
) -> Path:
    if output_dir is not None and mirror_root is not None:
        try:
            rel = image_path.resolve().relative_to(mirror_root)
            return output_dir / rel.parent
        except ValueError:
            return output_dir
    if output_dir is not None:
        return output_dir
    return image_path.parent


def output_paths_for(image_path: Path, dest_dir: Path) -> tuple[Path, Path]:
    return (
        dest_dir / image_path.with_suffix(".txt").name,
        dest_dir / image_path.with_suffix(".json").name,
    )


def build_batch_plan(
    *,
    inputs: list[str],
    recursive: bool,
    output_dir: Path | None,
    is_image_file: Callable[[Path], bool],
    batch_pages: int,
) -> BatchPlan:
    if batch_pages < 1:
        raise BatchPlanError(f"--batch-pages must be >= 1; got {batch_pages}")

    images = collect_images(inputs, recursive, is_image_file=is_image_file)
    if not images:
        raise BatchPlanError("no valid image files found.")

    mirror_root = compute_mirror_root(inputs, output_dir)
    jobs: list[PageJob] = []
    seen_outputs: dict[Path, Path] = {}
    collisions: list[str] = []

    for image_path in images:
        dest_dir = resolve_dest_dir(image_path, output_dir, mirror_root)
        txt_path, json_path = output_paths_for(image_path, dest_dir)
        for artifact_path in (txt_path, json_path):
            previous = seen_outputs.get(artifact_path)
            if previous is not None and previous.resolve() != image_path.resolve():
                collisions.append(f"{artifact_path} from {previous} and {image_path}")
            seen_outputs[artifact_path] = image_path
        jobs.append(
            PageJob(
                image_path=image_path,
                dest_dir=dest_dir,
                txt_path=txt_path,
                json_path=json_path,
            )
        )

    if collisions:
        raise BatchPlanError(f"output path collision: {'; '.join(collisions)}")

    return BatchPlan(jobs=tuple(jobs), mirror_root=mirror_root, chunk_size=batch_pages)
