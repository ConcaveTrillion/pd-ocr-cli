"""Pure-function tests for the version-parsing helpers in
:mod:`pd_ocr_cli._update_check`.

These cover the network-free building blocks of the GitHub-tag check:
``_parse_stable_tag``, ``_parse_release_prefix``, and
``_latest_stable_tag``. The actual HTTP path in ``check_for_update`` is
exercised end-to-end by the slow integration tests.
"""

import pytest

from pd_ocr_cli._update_check import (
    _latest_stable_tag,
    _parse_release_prefix,
    _parse_stable_tag,
)


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("v1.2.3", (1, 2, 3)),
        ("1.2.3", (1, 2, 3)),
        ("v0.0.1", (0, 0, 1)),
        ("v10.20.30", (10, 20, 30)),
        ("  v1.2.3  ", (1, 2, 3)),  # surrounding whitespace tolerated
    ],
)
def test_parse_stable_tag_accepts(tag, expected):
    assert _parse_stable_tag(tag) == expected


@pytest.mark.parametrize(
    "tag",
    [
        "v1.2",  # missing patch
        "1.2",  # missing patch
        "v1.2.3-rc1",  # pre-release suffix not "stable"
        "v1.2.3.dev1",  # dev marker not "stable"
        "v1.2.3+local",  # local marker not "stable"
        "garbage",
        "",
        "v1.2.3.4",  # too many components
    ],
)
def test_parse_stable_tag_rejects(tag):
    assert _parse_stable_tag(tag) is None


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("1.2.3", (1, 2, 3)),
        ("v1.2.3", (1, 2, 3)),
        ("1.2.3.dev1+gabc1234", (1, 2, 3)),
        ("0.4.0+gXYZ", (0, 4, 0)),
    ],
)
def test_parse_release_prefix_accepts_dev_versions(version, expected):
    """``_parse_release_prefix`` is tolerant — it only needs N.N.N up front."""
    assert _parse_release_prefix(version) == expected


@pytest.mark.parametrize("version", ["", "garbage", "v1.2", "1.2"])
def test_parse_release_prefix_rejects(version):
    assert _parse_release_prefix(version) is None


def test_latest_stable_tag_picks_highest_semver():
    tags = [
        {"name": "v0.4.0"},
        {"name": "v1.2.3"},
        {"name": "v0.9.9"},
        {"name": "v1.2.10"},  # numeric, not lexicographic
    ]
    name, parsed = _latest_stable_tag(tags)
    assert name == "v1.2.10"
    assert parsed == (1, 2, 10)


def test_latest_stable_tag_skips_unparseable():
    tags = [
        {"name": "v0.4.0-rc1"},
        {"name": "0.5.0"},
        {"name": "garbage"},
        {"name": ""},
    ]
    assert _latest_stable_tag(tags) == ("0.5.0", (0, 5, 0))


def test_latest_stable_tag_returns_none_when_empty():
    assert _latest_stable_tag([]) is None


def test_latest_stable_tag_returns_none_when_no_stable_tags():
    tags = [{"name": "v1.0.0-rc1"}, {"name": "draft"}]
    assert _latest_stable_tag(tags) is None
