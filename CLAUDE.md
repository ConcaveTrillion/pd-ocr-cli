# CLAUDE — pdomain-ocr-cli

CLI tool that turns scanned book pages into clean `.txt` files. Wraps
`pdomain-book-tools` OCR/layout primitives with auto-rotation, layout-aware
reading-order reconstruction, and a user-facing `pd-ocr` command.

## Commands

| target | does |
|---|---|
| `make setup AI=1` | dev venv + pre-commit hooks (pinned `pdomain-book-tools` tag) |
| `make local-setup` | clone any missing sibling pd-* repos into the workspace |
| `make local-dev` | switch to local-dev mode (editable `../pdomain-book-tools` + marker) |
| `make local-check` | print local-dev mode + per-sibling resolution |
| `make local-upgrade-deps` | upgrade deps then restore editable siblings (local-mode only) |
| `make local-install` / `local-uninstall` | `uv tool install` with editable siblings / uninstall |
| `make local-run` | run `pd-ocr` against local-dev workspace (local-mode only) |
| `make update-pd-deps` | bump pd-* sibling deps to registry latest; leaves diff for review |
| `make test AI=1` | fast suite (`uv run pytest -n auto`; skips `@pytest.mark.slow`) |
| `make test-slow AI=1` | full suite incl. real-model integration tests |
| `make lint AI=1` / `make format AI=1` | ruff |
| `make build AI=1` | sdist + wheel into `dist/` |
| `make ci AI=1` | setup → pre-commit → test → build |
| `make upgrade-pdomain-book-tools` | bump pin to latest GitHub tag |
| `make release-{patch,minor,major}` | tag locally; `git push --tags` triggers release workflow |
| `make refresh-version` | re-derive `pd-ocr --version` after tag changes (hatch-vcs) |

`AI=1` captures verbose output to `.ci-ai.log`; stdout shows `✅` on pass or
filtered failure sections on error. Remove `AI=1` only if you need full verbose
output for debugging.

See [workspace `docs/process/local-dev.md`](../docs/process/local-dev.md) for the canonical local-dev pattern (spec #362). Legacy `dev-local`, `install-local`, `uninstall-local`, `check-local-editable`, `run-local`, `upgrade-deps-local` are kept as deprecation aliases.

Full target list: `make help`. Full dev setup: [`DEVELOPMENT.md`](DEVELOPMENT.md).

## Rules

- Always run `make ci AI=1` before committing.
- Make targets first; fall back to `uv run …` only when no target exists.
- Never `python -m pytest`. Always `uv run pytest -n auto` or `make test`. Bare `python`/`python3`/`.venv/bin/python` miss the venv.
- Never silently drop OCR words. Reorg, caption suppression, and all output paths must preserve every word — roles may change, words may not disappear.
- `--no-illustration-placeholders` suppresses the placeholder block, not caption text. Caption words must survive in the output.
- `pdomain-book-tools` is upstream for OCR/layout/image primitives; coordinate with that agent before adding logic that belongs in the library.
- `pdomain-book-tools` is pinned in `pyproject.toml`; upgrade with `make upgrade-pdomain-book-tools`.
- Version is derived from git tags via `hatch-vcs` — no hardcoded version in `pyproject.toml`.

## Sibling repos

- `../pdomain-book-tools/` — upstream dependency. Side-by-side editing: `make local-setup` + `make dev-local`.

## Docs

- [`DEVELOPMENT.md`](DEVELOPMENT.md) — dev setup, Make targets, release steps.
- [`docs/plans/roadmap.md`](docs/plans/roadmap.md) — open priorities.
- [`docs/architecture/layout-aware-ocr.md`](docs/architecture/layout-aware-ocr.md) — layout-aware OCR behavior.
- [`docs/usage/cli-usage.md`](docs/usage/cli-usage.md) — end-user usage reference.

## GH issues

Cross-cut work tasks are tracked as GH issues in
**`ConcaveTrillion/ocr-container-meta`** (not in this repo's own tracker).
Plans under `docs/plans/` in the workspace root are synced there
via `/decompose-spec --sync`. Milestone naming: `spec: <plan-basename> (#N)`.

When shipping a plan task:

- Before starting: `gh issue view <N> --repo ConcaveTrillion/ocr-container-meta`
- After completing: `gh issue close <N> --repo ConcaveTrillion/ocr-container-meta`
- List open tasks:
  `gh issue list --repo ConcaveTrillion/ocr-container-meta --milestone "spec: <name> (#N)" --state open`

## docs/ folder

This repo follows the workspace docs/ template — see [`docs/README.md`](docs/README.md). Active
folders: `architecture/`, `decisions/`, `plans/`, `process/`, `research/`,
`runbooks/`, `specs/`, `templates/`, `usage/`, plus parallel `archive/`
subfolders.

**Superpowers redirect.** When a superpowers skill (e.g. `brainstorming`,
`writing-plans`) instructs you to save to `docs/superpowers/specs/<file>.md`
or `docs/superpowers/plans/<file>.md`, save to `docs/specs/<file>.md` or
`docs/plans/<file>.md` instead. There is no `docs/superpowers/` subdirectory
in this repo.

<!-- workspace-process:start -->

## Before coding

These steps are workspace defaults for any coding task. **User-level settings
override them** — a user's own `~/.claude/CLAUDE.md`, `settings.json`, or a
direct instruction in the conversation takes precedence and may waive or
change any step below.

### Working principles

- **Use skills.** Invoke the relevant superpowers skill before starting —
  process skills first (`brainstorming`, `systematic-debugging`,
  `writing-plans`, `test-driven-development`), then implementation skills.
  If a skill applies, using it is not optional.
- **Delegate by default.** Dispatch subagents for non-trivial work: per-repo
  agents for repo changes, `Explore` for code searches. This keeps large tool
  output out of the parent context.
- **Parallelize.** Run independent tasks as concurrent subagents — multiple
  agent calls in a single message. Set `model: sonnet` on implementers and
  reviewers.

### Steps

1. **Check the working tree.** `git status --short`. Surface or resolve stray
   uncommitted work before starting — don't build on it.
2. **Read repo guidance.** This repo's `CLAUDE.md` and `CONVENTIONS.md` for
   repo-specific rules.
3. **Consult `docs/` for authoritative context** (whichever folders exist):
   `plans/` (the work plan), `specs/` (design specs — follow any `Spec:`
   pointer from the issue), `research/` (prior investigations), `decisions/`
   (ADRs / constraints), `architecture/` (shipped design).
4. **Check live issue status.** `gh issue view <N> --repo <owner/repo>` —
   confirm it isn't already closed; note its milestone.
5. **Check for in-flight work.** Open PRs and existing branches touching the
   same area, to avoid colliding with work-in-progress.
6. **Consult agent memory.** `.claude/agent-memory/<repo>/feedback_*.md` for
   corrections not yet promoted to `CONVENTIONS.md`.
7. **Locate code with `Explore` first.** Use an `Explore` subagent to find
   relevant files before broad `Read`/grep.
8. **Isolate in a worktree.** Never work directly in the interactive checkout
   at `/workspaces/ocr-container/<repo>/`. Use the `using-git-worktrees` skill
   to set up an isolated worktree. When delegating to a full-power
   implementation agent, pass `isolation: "worktree"` on the `Agent` call
   (skip for `-docs` agents and the `driver` agent). When an agent returns a
   worktree path + branch, use the `finishing-a-development-branch` skill to
   decide how to integrate.
9. **TDD.** Write the failing test first where the plan calls for it.
10. **Verify before committing.** Focused verification plus `make ci`.
11. **Commit locally; do not push** without explicit say-so.

<!-- workspace-process:end -->
