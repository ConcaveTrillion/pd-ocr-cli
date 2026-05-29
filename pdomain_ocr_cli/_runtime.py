from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, Protocol, TypeVar

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path


class RuntimeSetupError(RuntimeError):
    """Raised when runtime startup fails before page processing begins."""


class BatchRuntimeError(RuntimeError):
    """Raised when a batch OCR call fails or returns an invalid shape."""


@dataclass(frozen=True)
class DecodedImage:
    path: Path
    array: object
    source_identifier: str


PageT = TypeVar("PageT")
PageT_co = TypeVar("PageT_co", covariant=True)


class BatchRunner(Protocol[PageT_co]):
    def __call__(
        self,
        images: list[object],
        *,
        predictor: object,
        device: str,
        source_identifiers: list[str],
    ) -> Sequence[PageT_co | None]: ...


class RuntimeSession(Protocol[PageT]):
    predictor: object
    device: str

    def run_batch(
        self,
        images: list[object],
        *,
        source_identifiers: list[str],
    ) -> list[PageT | None]: ...


def validate_batch_result_count(pages: Sequence[object | None], expected: int) -> None:
    if len(pages) != expected:
        raise BatchRuntimeError(f"batch returned {len(pages)} page(s) for {expected} image(s)")


def run_batch_checked(
    runner: BatchRunner[PageT],
    images: list[object],
    *,
    predictor: object,
    device: str,
    source_identifiers: list[str],
) -> list[PageT | None]:
    try:
        pages = list(
            runner(
                images,
                predictor=predictor,
                device=device,
                source_identifiers=source_identifiers,
            )
        )
    except Exception as exc:
        raise BatchRuntimeError(str(exc)) from exc
    validate_batch_result_count(pages, len(images))
    return pages


@dataclass
class DefaultRuntimeSession(Generic[PageT]):
    predictor: object
    device: str
    runner: BatchRunner[PageT]

    def run_batch(
        self,
        images: list[object],
        *,
        source_identifiers: list[str],
    ) -> list[PageT | None]:
        return run_batch_checked(
            self.runner,
            images,
            predictor=self.predictor,
            device=self.device,
            source_identifiers=source_identifiers,
        )
