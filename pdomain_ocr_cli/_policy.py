from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class RunPolicyArgs(Protocol):
    no_reorg: bool
    save_json: bool
    save_reorganize_diagnostics: bool
    validate_reorg: bool
    experimental_drop_layout_words: bool
    extract_illustrations: bool
    no_illustration_placeholders: bool
    layout_debug: bool
    layout_debug_dir: str | None
    layout_model: str
    no_update_check: bool


@dataclass(frozen=True)
class RunPolicy:
    do_reorg: bool
    layout_configured: bool
    layout_needed: bool
    want_diagnostic_export: bool
    validate_reorg: bool
    drop_layout_words: bool
    emit_illustration_placeholders: bool
    layout_debug_announced: bool
    warnings: tuple[str, ...]


def build_run_policy(args: RunPolicyArgs) -> RunPolicy:
    do_reorg = not args.no_reorg
    layout_configured = args.layout_model != "none"
    layout_needed = layout_configured and (do_reorg or args.extract_illustrations)
    warnings: list[str] = []

    if args.no_reorg and args.save_reorganize_diagnostics:
        warnings.append(
            "warning: --save-reorganize-diagnostics has no effect with --no-reorg (diagnostics are produced only when reorganize runs); ignoring."
        )
    if args.no_reorg and args.validate_reorg:
        warnings.append(
            "warning: --validate-reorg has no effect with --no-reorg (validation compares pre/post reorganize word lists); ignoring."
        )
    if not layout_configured and args.layout_debug:
        warnings.append(
            "warning: --layout-debug has no effect with --layout-model none (no layout model runs, so no debug artifact is written); ignoring."
        )
    if args.no_reorg and args.layout_debug:
        warnings.append(
            "warning: --layout-debug has no effect with --no-reorg (the debug report is written from inside reorganize_page, which is skipped); ignoring."
        )
    if args.layout_debug_dir and not args.layout_debug:
        warnings.append(
            "warning: --layout-debug-dir has no effect without --layout-debug (the directory is only used when the debug artifact is enabled); ignoring."
        )
    if args.save_reorganize_diagnostics and not args.save_json:
        warnings.append(
            "warning: --save-reorganize-diagnostics has no effect without --save-json (the diagnostic bundle is written alongside the regular .json output, which requires --save-json); ignoring."
        )
    if args.no_reorg and args.experimental_drop_layout_words:
        warnings.append(
            "warning: --experimental-drop-layout-words has no effect with --no-reorg (the drop is applied inside reorganize_page, which is skipped); ignoring."
        )
    if args.no_reorg and args.no_illustration_placeholders:
        warnings.append(
            "warning: --no-illustration-placeholders has no effect with --no-reorg (placeholder emission happens inside reorganize_page, which is skipped); ignoring."
        )

    return RunPolicy(
        do_reorg=do_reorg,
        layout_configured=layout_configured,
        layout_needed=layout_needed,
        want_diagnostic_export=do_reorg and args.save_json and args.save_reorganize_diagnostics,
        validate_reorg=do_reorg and args.validate_reorg,
        drop_layout_words=do_reorg and args.experimental_drop_layout_words,
        emit_illustration_placeholders=not args.no_illustration_placeholders,
        layout_debug_announced=args.layout_debug and do_reorg and layout_configured,
        warnings=tuple(warnings),
    )
