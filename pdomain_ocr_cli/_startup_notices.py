from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable


class UpdateArgs(Protocol):
    no_update_check: bool


def env_truthy(name: str) -> bool:
    """True when an environment variable uses a common opt-in value."""
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def update_check_disabled(args: UpdateArgs) -> bool:
    return args.no_update_check or env_truthy("PD_OCR_NO_UPDATE_CHECK")


def start_update_check_thread(
    *,
    disabled: bool,
    check_for_update: Callable[[], None],
) -> threading.Thread | None:
    if disabled:
        return None
    thread = threading.Thread(target=check_for_update, daemon=True)
    thread.start()
    return thread


# Process-cached so repeated main() calls do not respawn nvidia-smi.
GPU_NUDGE_CACHE: dict[str, bool] = {}


def should_nudge_gpu_install(cache: dict[str, bool] | None = None) -> bool:
    """Return True when an NVIDIA host looks like a CPU-only pdomain-ocr install."""
    cache = GPU_NUDGE_CACHE if cache is None else cache
    if "result" in cache:
        return cache["result"]

    def _probe() -> bool:
        if env_truthy("PD_OCR_NO_GPU_NUDGE"):
            return False
        try:
            import cupy as cupy_module  # pyright: ignore[reportMissingImports]  # optional GPU dep

            _ = cupy_module
        except ImportError:
            pass
        except BaseException:  # noqa: BLE001  # broken optional GPU dep must stay silent
            return False
        else:
            return False

        if shutil.which("nvidia-smi") is None:
            return False
        try:
            proc = subprocess.run(
                ["nvidia-smi"],  # noqa: S607  # nvidia-smi is intentionally resolved from PATH
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return proc.returncode == 0

    try:
        result = _probe()
    except BaseException:  # noqa: BLE001  # the nudge helper must never break OCR startup
        result = False
    cache["result"] = result
    return result


def maybe_print_gpu_nudge(
    should_nudge: Callable[[], bool] = should_nudge_gpu_install,
) -> None:
    """Print the GPU-install nudge when applicable, never raising."""
    try:
        if should_nudge():
            print(  # noqa: T201  # CLI output
                (
                    "pdomain-ocr: NVIDIA GPU detected but pdomain-ocr was installed CPU-only.\n"
                    + "        Re-run the install script to switch to GPU (requires CUDA >= 12.4):\n"
                    + "          curl -sSL https://raw.githubusercontent.com/pdomain/pdomain-ocr-cli/main/install.sh | sh\n"
                    + "        Set PD_OCR_NO_GPU_NUDGE=1 to silence this message."
                ),
                file=sys.stderr,
            )
    except BaseException:  # noqa: BLE001 S110  # notice helper must never crash pdomain-ocr
        pass
