"""Shared pytest configuration.

Adds a ``--run-slow`` opt-in so the heavy end-to-end OCR tests (which pull
a pinned model from Hugging Face the first time they run) stay out of the
default ``make test`` loop.
"""

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-slow",
        action="store_true",
        default=False,
        help="Run tests marked @pytest.mark.slow (downloads a pinned model the first time).",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-slow"):
        return
    skip_slow = pytest.mark.skip(reason="slow test; pass --run-slow to enable")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)
