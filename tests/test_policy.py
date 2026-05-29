from __future__ import annotations

from dataclasses import dataclass

from pdomain_ocr_cli._policy import build_run_policy


@dataclass
class _Args:
    no_reorg: bool = False
    save_json: bool = False
    save_reorganize_diagnostics: bool = False
    validate_reorg: bool = False
    experimental_drop_layout_words: bool = False
    extract_illustrations: bool = False
    no_illustration_placeholders: bool = False
    layout_debug: bool = False
    layout_debug_dir: str | None = None
    layout_model: str = "pp-doclayout-plus-l"
    no_update_check: bool = False


def _args(**overrides: object) -> _Args:
    args = _Args()
    for name, value in overrides.items():
        setattr(args, name, value)
    return args


def test_policy_skips_layout_for_plain_no_reorg() -> None:
    policy = build_run_policy(_args(no_reorg=True))

    assert policy.do_reorg is False
    assert policy.layout_configured is True
    assert policy.layout_needed is False
    assert policy.layout_debug_announced is False


def test_policy_keeps_layout_for_no_reorg_extract_illustrations() -> None:
    policy = build_run_policy(_args(no_reorg=True, extract_illustrations=True))

    assert policy.do_reorg is False
    assert policy.layout_needed is True


def test_policy_diagnostic_export_requires_reorg_save_json_and_flag() -> None:
    policy = build_run_policy(
        _args(save_json=True, save_reorganize_diagnostics=True, no_reorg=False)
    )
    no_json = build_run_policy(_args(save_reorganize_diagnostics=True, no_reorg=False))
    no_reorg = build_run_policy(
        _args(save_json=True, save_reorganize_diagnostics=True, no_reorg=True)
    )

    assert policy.want_diagnostic_export is True
    assert no_json.want_diagnostic_export is False
    assert no_reorg.want_diagnostic_export is False


def test_policy_centralizes_reorg_dependent_flags() -> None:
    policy = build_run_policy(
        _args(
            no_reorg=False,
            validate_reorg=True,
            experimental_drop_layout_words=True,
            no_illustration_placeholders=True,
            layout_debug=True,
        )
    )

    assert policy.validate_reorg is True
    assert policy.drop_layout_words is True
    assert policy.emit_illustration_placeholders is False
    assert policy.layout_debug_announced is True


def test_policy_emits_current_noop_warnings() -> None:
    policy = build_run_policy(
        _args(
            no_reorg=True,
            save_reorganize_diagnostics=True,
            validate_reorg=True,
            experimental_drop_layout_words=True,
            no_illustration_placeholders=True,
            layout_debug=True,
            layout_debug_dir="debug",
        )
    )
    joined = "\n".join(policy.warnings)

    assert "--save-reorganize-diagnostics has no effect with --no-reorg" in joined
    assert "--validate-reorg has no effect with --no-reorg" in joined
    assert "--layout-debug has no effect with --no-reorg" in joined
    assert "--experimental-drop-layout-words has no effect with --no-reorg" in joined
    assert "--no-illustration-placeholders has no effect with --no-reorg" in joined
