from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FULL_SHA_REF = re.compile(r"@[0-9a-f]{40}$")


def _workflow_uses_refs(path: Path) -> list[str]:
    return re.findall(r"uses:\s*([^\s]+)", path.read_text(encoding="utf-8"))


def test_release_runs_ci_before_build() -> None:
    text = (REPO / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "make ci-slow" in text
    assert text.index("make ci-slow") < text.index("uv build")


def test_release_uses_env_for_ref_name_in_shell() -> None:
    text = (REPO / ".github/workflows/release.yml").read_text(encoding="utf-8")
    run_blocks = [line for line in text.splitlines() if "client_payload[tag]" in line]
    assert all("${{ github.ref_name }}" not in line for line in run_blocks)
    assert "RELEASE_TAG: ${{ github.ref_name }}" in text


def test_ci_declares_supported_python_matrix() -> None:
    text = (REPO / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert 'python-version: ["3.11", "3.12", "3.13"]' in text
    assert "UV_PYTHON: ${{ matrix.python-version }}" in text
    assert 'make ci PYTHON_VERSIONS="${{ matrix.python-version }}"' in text


def test_makefile_wheel_smoke_covers_supported_python_versions() -> None:
    text = (REPO / "Makefile").read_text(encoding="utf-8")
    assert "PYTHON_VERSIONS ?= 3.11 3.12 3.13" in text
    assert "wheel-smoke:" in text
    assert "wheel-smoke-one:" in text
    assert "$(MAKE) --no-print-directory wheel-smoke" in text


def test_workflow_actions_are_pinned_to_full_commit_shas() -> None:
    workflow_paths = [
        REPO / ".github/workflows/ci.yml",
        REPO / ".github/workflows/release.yml",
    ]
    refs = [ref for path in workflow_paths for ref in _workflow_uses_refs(path)]
    assert refs
    assert all(FULL_SHA_REF.search(ref) for ref in refs)


def test_release_checks_dependency_sources_before_build() -> None:
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    release = (REPO / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "check-release-deps:" in makefile
    assert "pdomain-ops must not be path-sourced for release" in makefile
    assert "make check-release-deps" in release
    assert release.index("make check-release-deps") < release.index("uv build")


def test_ci_provisions_path_sourced_pdomain_ops_for_development_ci() -> None:
    text = (REPO / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "PDOMAIN_OPS_REF:" in text
    assert "repository: pdomain/pdomain-ops" in text
    assert "ref: ${{ env.PDOMAIN_OPS_REF }}" in text
    assert 'ln -sfn "$PWD/pdomain-ops" ../pdomain-ops' in text


def test_release_does_not_use_latest_tool_versions() -> None:
    text = (REPO / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "version: latest" not in text
