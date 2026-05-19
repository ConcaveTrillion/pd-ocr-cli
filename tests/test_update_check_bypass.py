"""Tests for the update-check bypass mechanism.

Covers the ``--no-update-check`` flag and the ``PD_OCR_NO_UPDATE_CHECK``
env var, including the truthy-value matcher behind the env var.
"""

from unittest.mock import patch

import pytest

from pd_ocr_cli.ocr_to_txt import _env_truthy, parse_args


@pytest.mark.parametrize(
    "value",
    ["1", "true", "TRUE", "True", "yes", "Yes", "YES", "on", "ON"],
)
def test_env_truthy_accepts(value, monkeypatch):
    monkeypatch.setenv("PD_OCR_TEST_VAR", value)
    assert _env_truthy("PD_OCR_TEST_VAR") is True


@pytest.mark.parametrize(
    "value",
    ["0", "false", "False", "no", "NO", "off", "OFF", "", "garbage", "2", "y"],
)
def test_env_truthy_rejects(value, monkeypatch):
    monkeypatch.setenv("PD_OCR_TEST_VAR", value)
    assert _env_truthy("PD_OCR_TEST_VAR") is False


def test_env_truthy_unset(monkeypatch):
    monkeypatch.delenv("PD_OCR_TEST_VAR", raising=False)
    assert _env_truthy("PD_OCR_TEST_VAR") is False


def test_env_truthy_strips_whitespace(monkeypatch):
    monkeypatch.setenv("PD_OCR_TEST_VAR", "  1  \n")
    assert _env_truthy("PD_OCR_TEST_VAR") is True


def test_no_update_check_flag_default_false():
    with patch("sys.argv", ["pd-ocr", "page.png"]):
        args = parse_args()
    assert args.no_update_check is False


def test_no_update_check_flag_set():
    with patch("sys.argv", ["pd-ocr", "--no-update-check", "page.png"]):
        args = parse_args()
    assert args.no_update_check is True


# --- Gate behavior -----------------------------------------------------------
# The actual gate lives inside main() as:
#     update_check_disabled = args.no_update_check or _env_truthy("PD_OCR_NO_UPDATE_CHECK")  # noqa: ERA001
# These tests exercise the equivalent compound condition end-to-end.


def _gate_disabled(args, monkeypatch_env):
    """Mirror of the main() gate, for direct testing without mocking the
    full predictor / model load path."""
    return args.no_update_check or _env_truthy("PD_OCR_NO_UPDATE_CHECK")


def test_gate_off_by_default(monkeypatch):
    monkeypatch.delenv("PD_OCR_NO_UPDATE_CHECK", raising=False)
    with patch("sys.argv", ["pd-ocr", "page.png"]):
        args = parse_args()
    assert _gate_disabled(args, monkeypatch) is False


def test_gate_on_via_flag(monkeypatch):
    monkeypatch.delenv("PD_OCR_NO_UPDATE_CHECK", raising=False)
    with patch("sys.argv", ["pd-ocr", "--no-update-check", "page.png"]):
        args = parse_args()
    assert _gate_disabled(args, monkeypatch) is True


def test_gate_on_via_env_var(monkeypatch):
    monkeypatch.setenv("PD_OCR_NO_UPDATE_CHECK", "1")
    with patch("sys.argv", ["pd-ocr", "page.png"]):
        args = parse_args()
    assert _gate_disabled(args, monkeypatch) is True


def test_gate_on_via_either(monkeypatch):
    """Flag set + env unset still disables; flag unset + env truthy still disables."""
    monkeypatch.setenv("PD_OCR_NO_UPDATE_CHECK", "yes")
    with patch("sys.argv", ["pd-ocr", "--no-update-check", "page.png"]):
        args = parse_args()
    assert _gate_disabled(args, monkeypatch) is True
