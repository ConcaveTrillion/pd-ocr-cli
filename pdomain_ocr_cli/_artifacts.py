from __future__ import annotations

import contextlib
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


def _fsync_parent_dir(path: Path) -> None:
    if os.name == "nt":  # pragma: no cover - Windows-only branch
        return
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(raw_tmp)
    try:
        try:
            view = memoryview(data)
            while view:
                written = os.write(fd, view)
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        tmp.chmod(0o644)
        os.replace(tmp, path)
        _fsync_parent_dir(path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()
        raise


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    atomic_write_bytes(path, text.encode(encoding))


class JsonDocumentLike(Protocol):
    def to_json_file(self, file_path: str | Path) -> None: ...


def atomic_write_json_document(path: Path, doc: JsonDocumentLike) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(raw_tmp)
    os.close(fd)
    try:
        doc.to_json_file(tmp)
        with tmp.open("rb") as fh:
            os.fsync(fh.fileno())
        tmp.chmod(0o644)
        os.replace(tmp, path)
        _fsync_parent_dir(path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()
        raise


@dataclass
class PageOutputTransaction:
    txt_path: Path
    json_path: Path
    extra_paths: list[str] = field(default_factory=list)

    def write_text_last(self, text: str) -> None:
        atomic_write_text(self.txt_path, text)
