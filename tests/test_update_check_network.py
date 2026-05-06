"""Tests for ``check_for_update`` — the GitHub-tag fetch + notice path.

The function is best-effort (any error is swallowed) and runs in a daemon
thread on every CLI invocation, so we exercise each branch of its logic
with a mocked ``urllib.request.urlopen`` rather than hitting GitHub.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from pd_ocr_cli import _update_check


class _FakeResponse:
    """Minimal stand-in for the ``urllib.request.urlopen`` context manager."""

    def __init__(self, body: bytes):
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake_urlopen(payload):
    """Return a callable that mimics ``urlopen`` for a JSON-serializable payload."""

    def _opener(req, timeout=None):
        return _FakeResponse(json.dumps(payload).encode("utf-8"))

    return _opener


def _fake_urlopen_raises(exc: Exception):
    def _opener(req, timeout=None):
        raise exc

    return _opener


# ---------------------------------------------------------------------------
# Early-return paths
# ---------------------------------------------------------------------------


def test_returns_silently_when_version_unknown(monkeypatch, capsys):
    monkeypatch.setattr(_update_check, "VERSION", "unknown")
    # urlopen must not be called — assign a sentinel that would fail the test.
    with patch("urllib.request.urlopen", side_effect=AssertionError("called")):
        _update_check.check_for_update()
    out, err = capsys.readouterr()
    assert out == ""
    assert err == ""


def test_returns_silently_when_tags_empty(monkeypatch, capsys):
    monkeypatch.setattr(_update_check, "VERSION", "0.5.0")
    with patch("urllib.request.urlopen", _fake_urlopen([])):
        _update_check.check_for_update()
    err = capsys.readouterr().err
    assert err == ""


def test_returns_silently_when_no_stable_tags(monkeypatch, capsys):
    monkeypatch.setattr(_update_check, "VERSION", "0.5.0")
    payload = [{"name": "v1.0.0-rc1"}, {"name": "draft"}]
    with patch("urllib.request.urlopen", _fake_urlopen(payload)):
        _update_check.check_for_update()
    err = capsys.readouterr().err
    assert err == ""


def test_returns_silently_when_current_version_unparseable(monkeypatch, capsys):
    monkeypatch.setattr(_update_check, "VERSION", "garbage-not-semver")
    payload = [{"name": "v1.0.0"}]
    with patch("urllib.request.urlopen", _fake_urlopen(payload)):
        _update_check.check_for_update()
    err = capsys.readouterr().err
    assert err == ""


# ---------------------------------------------------------------------------
# The "newer version available" notice
# ---------------------------------------------------------------------------


def test_prints_notice_when_newer_version_available(monkeypatch, capsys):
    monkeypatch.setattr(_update_check, "VERSION", "0.5.0")
    payload = [{"name": "v1.2.3"}, {"name": "v0.4.0"}]
    with patch("urllib.request.urlopen", _fake_urlopen(payload)):
        _update_check.check_for_update()
    err = capsys.readouterr().err
    assert "newer version of pd-ocr is available" in err
    assert "v1.2.3" in err  # latest tag
    assert "0.5.0" in err  # current version
    assert "curl -sSL" in err  # upgrade command included


def test_no_notice_when_current_equals_latest(monkeypatch, capsys):
    monkeypatch.setattr(_update_check, "VERSION", "1.2.3")
    payload = [{"name": "v1.2.3"}]
    with patch("urllib.request.urlopen", _fake_urlopen(payload)):
        _update_check.check_for_update()
    err = capsys.readouterr().err
    assert err == ""


def test_no_notice_when_current_is_newer_than_latest(monkeypatch, capsys):
    """A locally-built dev version may legitimately exceed any released tag."""
    monkeypatch.setattr(_update_check, "VERSION", "2.0.0")
    payload = [{"name": "v1.2.3"}]
    with patch("urllib.request.urlopen", _fake_urlopen(payload)):
        _update_check.check_for_update()
    err = capsys.readouterr().err
    assert err == ""


def test_notice_uses_dev_version_release_prefix(monkeypatch, capsys):
    """Dev versions like ``0.5.0.dev1+gabc`` compare on the N.N.N prefix."""
    monkeypatch.setattr(_update_check, "VERSION", "0.5.0.dev1+gabc1234")
    payload = [{"name": "v1.0.0"}]
    with patch("urllib.request.urlopen", _fake_urlopen(payload)):
        _update_check.check_for_update()
    err = capsys.readouterr().err
    assert "newer version" in err
    assert "v1.0.0" in err


def test_notice_when_dev_prefix_equals_latest_stable(monkeypatch, capsys):
    """A user on ``1.2.3.devN+gHASH`` is on a pre-release *of* 1.2.3 — the
    stable ``v1.2.3`` is therefore strictly newer (PEP 440: 1.2.3.dev1 <
    1.2.3) and the upgrade notice must fire. Stripping the dev/local
    suffix to compare bare ``(1,2,3) > (1,2,3)`` would silently miss this.
    """
    monkeypatch.setattr(_update_check, "VERSION", "1.2.3.dev1+gabc1234")
    payload = [{"name": "v1.2.3"}]
    with patch("urllib.request.urlopen", _fake_urlopen(payload)):
        _update_check.check_for_update()
    err = capsys.readouterr().err
    assert "newer version" in err, (
        f"dev pre-release of 1.2.3 must be told v1.2.3 stable is newer; got stderr: {err!r}"
    )
    assert "v1.2.3" in err
    assert "1.2.3.dev1+gabc1234" in err


# ---------------------------------------------------------------------------
# Best-effort error handling
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc",
    [
        ConnectionError("network down"),
        TimeoutError("dns lookup timed out"),
        ValueError("invalid json"),
        OSError("socket reset"),
    ],
)
def test_swallows_urlopen_errors(monkeypatch, capsys, exc):
    """Network or parse errors must not crash — the check is best-effort."""
    monkeypatch.setattr(_update_check, "VERSION", "0.5.0")
    with patch("urllib.request.urlopen", _fake_urlopen_raises(exc)):
        _update_check.check_for_update()  # must not raise
    err = capsys.readouterr().err
    assert err == ""


def test_swallows_malformed_json(monkeypatch, capsys):
    """Non-JSON response should be swallowed at the json.loads boundary."""
    monkeypatch.setattr(_update_check, "VERSION", "0.5.0")

    def _bad_opener(req, timeout=None):
        return _FakeResponse(b"<html>nope</html>")

    with patch("urllib.request.urlopen", _bad_opener):
        _update_check.check_for_update()
    err = capsys.readouterr().err
    assert err == ""


# ---------------------------------------------------------------------------
# Pagination: GitHub defaults to 30 tags per page; we must opt into the max
# (100) so the latest stable tag does not silently fall off page 1.
# ---------------------------------------------------------------------------


def test_tags_request_uses_per_page_100(monkeypatch):
    """The tags-API URL must include ``per_page=100`` so we don't silently
    miss the newest stable release once the project crosses 30 tags.
    """
    monkeypatch.setattr(_update_check, "VERSION", "0.5.0")

    captured: dict = {}

    def _capturing_opener(req, timeout=None):
        captured["url"] = req.full_url
        return _FakeResponse(b"[]")

    with patch("urllib.request.urlopen", _capturing_opener):
        _update_check.check_for_update()

    assert "url" in captured, "urlopen was not called"
    assert "per_page=100" in captured["url"], (
        f"tags URL must request per_page=100 (got: {captured['url']!r})"
    )


# ---------------------------------------------------------------------------
# User-Agent: GitHub may rate-limit the default ``Python-urllib/3.x`` UA more
# aggressively than a clearly-identified application UA. Set an explicit one.
# ---------------------------------------------------------------------------


def test_tags_request_sets_explicit_user_agent(monkeypatch):
    """The tags-API request must carry an explicit ``User-Agent`` header
    identifying ``pd-ocr-cli`` and its version, rather than relying on
    urllib's default ``Python-urllib/3.x`` (which GitHub may throttle).
    """
    monkeypatch.setattr(_update_check, "VERSION", "0.5.0")

    captured: dict = {}

    def _capturing_opener(req, timeout=None):
        # ``Request.headers`` keys are title-cased by urllib internals.
        captured["headers"] = dict(req.headers)
        captured["ua"] = req.get_header("User-agent")
        return _FakeResponse(b"[]")

    with patch("urllib.request.urlopen", _capturing_opener):
        _update_check.check_for_update()

    ua = captured.get("ua")
    assert ua is not None, (
        f"Request must set an explicit User-Agent header (headers seen: {captured.get('headers')!r})"
    )
    assert "pd-ocr-cli" in ua, f"User-Agent must identify pd-ocr-cli (got: {ua!r})"
    assert "0.5.0" in ua, f"User-Agent must include the package version (got: {ua!r})"
