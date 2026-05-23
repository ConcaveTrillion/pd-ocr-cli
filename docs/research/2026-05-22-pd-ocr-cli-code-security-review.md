# pd-ocr-cli Deep Code Review and Security Scan

Date: 2026-05-22
Repo: `ConcaveTrillion/pd-ocr-cli`
Workspace path: `/workspaces/ocr-container/pd-ocr-cli`

## Scope

Reviewed the CLI pipeline, model-loading path, filesystem writes, installers,
release/CI workflows, dependency posture, test coverage, and user-facing
documentation. The review used four read-only subagents for security, runtime
behavior, packaging/CI, and tests/docs, plus local static/security tooling.

## Verification

- `make setup AI=1` passed after the initial environment was bootstrapped
  through the repo target.
- `make lint AI=1` passed.
- `make typecheck AI=1` passed.
- `make test AI=1` passed.
- `uv run ruff check --select S .` passed.
- `uvx pip-audit --progress-spinner off --desc off` found no known vulnerable
  Python dependencies in the installed environment.
- `uvx pip-audit -r /tmp/idna-req.txt --progress-spinner off --desc off`
  found `idna==3.13` vulnerable to `CVE-2026-45409`, fixed in `idna>=3.15`.
  A full exported-requirements audit could not complete because pip could not
  resolve the self-hosted `pd-book-tools==0.12.0` entry without the private
  index configuration.
- `uvx detect-secrets scan --all-files --exclude-files
  '(^|/)(\.venv|\.pytest_cache|\.ruff_cache|htmlcov|dist|\.git)/'` found no
  tracked secrets.
- `uvx bandit -q -r pd_ocr_cli scripts install.sh install.ps1` reported one
  medium and four low findings.
- `uvx zizmor --format plain .github/workflows` reported workflow hardening
  findings across high, medium, and low severities.

Note: before `make setup`, `.venv` contained broken symlinks into a missing
shared uv cache, causing `basedpyright` and `pytest` entry points to fail. This
did not reproduce after `make setup AI=1` and is not counted as a repo finding.

## Findings

## Filed Issues

- Finding 1: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/15
- Finding 2: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/16
- Finding 3: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/17
- Finding 4: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/18
- Finding 5: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/19
- Finding 6: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/20
- Finding 7: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/21
- Finding 8: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/22
- Finding 9: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/23
- Finding 10: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/24
- Finding 11: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/25
- Finding 12: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/26
- Finding 13: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/27
- Finding 14: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/28
- Finding 15: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/29
- Finding 16: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/30
- Finding 17: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/31
- Finding 18: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/32
- Finding 19: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/33
- Finding 20: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/34
- Finding 21: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/35
- Finding 22: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/36
- Finding 23: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/37
- Finding 24: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/38
- Finding 25: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/39
- Finding 26: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/40
- Finding 27: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/41
- Finding 28: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/42
- Finding 29: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/43
- Finding 30: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/44
- Finding 31: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/45
- Finding 32: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/46
- Finding 33: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/47
- Finding 34: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/48
- Finding 35: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/49
- Finding 36: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/50
- Finding 37: https://github.com/ConcaveTrillion/pd-ocr-cli/issues/51

### 1. High: Default mutable `.pt` model download is loaded through `torch.load`

`--model-version` defaults to `None` / latest in `pd_ocr_cli/ocr_to_txt.py:325`,
the CLI resolves models in `pd_ocr_cli/_hf_models.py:80`, and `pd-book-tools`
downloads with `revision=None` before loading checkpoints through `torch.load`.
Current installed dependency evidence: `.venv/.../pd_book_tools/hf/models.py:63`,
`.venv/.../pd_book_tools/ocr/doctr_support.py:244`, and `:275`.

Impact: a compromised or malicious default Hugging Face model file can execute
code during checkpoint loading on first run.

Remediation: pin default OCR model revisions to immutable commit SHAs, require
explicit opt-in for mutable/non-default repos or revisions, and migrate
checkpoints to a safe loading format such as `safetensors` or
`torch.load(..., weights_only=True)` where compatible.

### 2. Medium: User-supplied model options cross the same unsafe checkpoint trust boundary

The CLI accepts arbitrary Hugging Face repos/files and local `.pt` model paths
in `pd_ocr_cli/ocr_to_txt.py:317`, `:325`, `:344`, and `:351`, then delegates to
the same loader path.

Impact: users can be tricked into running untrusted `.pt` checkpoints that
execute code locally.

Remediation: document model paths/repos as executable trust inputs, warn on
non-default repos/local `.pt` files, and prefer safe model formats.

### 3. Medium: Predictable sibling temp files allow symlink clobbering in shared output dirs

Atomic text writes use deterministic temps from `pd_ocr_cli/_pipeline.py:57`
and open them with `O_CREAT | O_TRUNC` at `pd_ocr_cli/_pipeline.py:88`.
JSON and crop outputs also use deterministic temp names at
`pd_ocr_cli/ocr_to_txt.py:820` and `:871`.

Impact: in an attacker-writable output directory, a pre-created temp symlink can
truncate or overwrite files writable by the user.

Remediation: create temp files with exclusive creation in the destination
directory, reject symlink temps, and preserve atomic replace semantics.

### 4. High: Rotated OCR pages can get unrotated layout regions and crops

The OCR document is created at `pd_ocr_cli/ocr_to_txt.py:728`, but layout
detection still receives the original path at `:743`, and illustration crops
re-read the original image at `:850`.

Impact: sideways/upside-down scans may OCR correctly through auto-rotation
while layout detection and crops run on the unrotated source, producing
misaligned regions, wrong reading-order hints, wrong figure/caption tagging, or
crops from the wrong coordinates.

Remediation: pass the OCR page's rotated image/frame to layout detection and
crop extraction when available, and add a rotated-image regression test.

### 5. High: Explicit file inputs with the same basename silently overwrite each other under `-o`

For file-only inputs, `compute_mirror_root()` returns `None`
(`pd_ocr_cli/_pipeline.py:159`), `resolve_dest_dir()` writes all files flat under
the output directory (`:200`), and `output_paths_for()` uses only the basename
(`:205`).

Impact: `pd-ocr -o out dir1/page.png dir2/page.png` writes both pages to
`out/page.txt`; the later page silently replaces the earlier output.

Remediation: preflight output-path collisions and fail clearly, or mirror by a
common parent when collisions would occur.

### 6. Medium: `--no-reorg` still resolves, downloads, loads, and runs layout

Layout is enabled based on `args.layout_model != "none"` rather than whether
layout output is needed. Resolution/prefetch happens at
`pd_ocr_cli/ocr_to_txt.py:655`, loading at `:677`, detection at `:741`, while
`do_reorg` is only computed later at `:754`.

Impact: a user asking for raw OCR can still pay layout model download/load
costs and can fail on layout network/model errors even though reorganization is
disabled.

Remediation: compute an effective layout need: reorg will run or illustration
extraction is requested. Skip layout for plain `--no-reorg`.

### 7. Medium: JSON and crop writes bypass the durable atomic-write helper

The pipeline states all disk writes should go through fsync + replace helpers
in `pd_ocr_cli/_pipeline.py:46`, but JSON writes use `doc.to_json_file()` then
`os.replace()` at `pd_ocr_cli/ocr_to_txt.py:820` and `:827`; crop writes use
`cv2.imwrite()` then `os.replace()` at `:871` and `:881`.

Impact: a crash or power loss can lose or corrupt sidecar/crop outputs even
when `.txt` output uses the stronger durability path.

Remediation: serialize JSON and encoded crop bytes through the atomic write
helper, or add a binary/callback atomic writer that fsyncs the temp file and
parent directory.

### 8. Medium: Failed final `.txt` write leaves earlier sidecars/crops behind

The final text write intentionally happens last at `pd_ocr_cli/ocr_to_txt.py:888`
after JSON/diagnostic/crop artifacts have already been written. No rollback
removes those artifacts if the final write fails.

Impact: a failed page can leave new sidecars/crops without a `.txt`, violating
the code's all-or-nothing artifact comment and confusing downstream consumers
that inspect sidecars directly.

Remediation: track newly created artifacts and unlink them if a later mandatory
artifact fails, or stage all page artifacts and promote them only after every
artifact succeeds.

### 9. High: Windows installer likely cannot resolve `pd-book-tools`

`install.ps1` installs from the GitHub source ref at `install.ps1:137` and only
adds an extra index for CUDA/PyTorch at `:156`. It never adds
`https://concavetrillion.github.io/pd-index-pip/simple/`, even though
`pyproject.toml:16` depends on `pd-book-tools>=0.12.0` and `pyproject.toml:51`
declares the uv source only for this repo's own uv operations. The POSIX
installer passes the pd index at `install.sh:151`.

Impact: Windows installs can fail to resolve `pd-book-tools` or resolve it from
an unintended source.

Remediation: make `install.ps1` mirror `install.sh`: install the release wheel,
always pass the pd index URL, and test generated `uv tool install` arguments.

### 10. Medium: Installer dependency resolution permits dependency confusion for `pd-book-tools`

The runtime dependency is a generic lower bound in `pyproject.toml:16`. The Unix
installer passes the private index only as `--extra-index-url` at
`install.sh:151`, while the PowerShell installer omits it entirely in the CPU
path.

Impact: a same-named package on a higher-priority/default index could satisfy
`pd-book-tools` during installation.

Remediation: use an index strategy that prevents PyPI fallback for
`pd-book-tools`, or pin by direct URL/hash. Add the pd index consistently to
Windows installs.

### 11. High: Tag-pushed releases publish artifacts without a server-side test gate

The release workflow runs on any `v*` tag push at `.github/workflows/release.yml:17`,
builds at `:50`, and publishes at `:61`. The local preflight in
`scripts/do-release.sh` can be bypassed by a direct tag push.

Impact: a tag push can publish wheel/sdist artifacts that never passed tests,
typecheck, pre-commit, or integration checks on GitHub Actions.

Remediation: run `make ci` or `make ci-slow` in the release workflow before
`uv build`, add a smoke install from the built wheel, and protect release tags.

### 12. Medium: Privileged release workflow uses mutable third-party action refs and tool versions

The release job has write/id-token/attestation permissions at
`.github/workflows/release.yml:31`, while actions are referenced by tags at
`:36`, `:43`, `:57`, and `:62`; setup-uv also installs `version: latest` at
`:45`.

Impact: a compromised/moved action tag or latest tool release can influence
release artifacts.

Remediation: pin actions by full commit SHA and pin `uv` to a specific version.

### 13. High: Release workflow has template-injection risk in shell block

`zizmor` flagged `${{ github.ref_name }}` interpolated directly into a shell
`run:` block at `.github/workflows/release.yml:94`.

Impact: if an attacker can influence a matching tag name, expression expansion
can alter shell script behavior in a privileged release job.

Remediation: pass `github.ref_name` through an environment variable and quote it
inside the script, or avoid shell interpolation entirely.

### 14. Low: Checkout credentials persist in CI/release jobs

`zizmor` flagged `actions/checkout` steps without `persist-credentials: false`
in `.github/workflows/ci.yml:20` and `.github/workflows/release.yml:36`.

Impact: persisted credentials can be exposed to later steps or accidentally
captured in artifacts if the workflow grows.

Remediation: set `persist-credentials: false` for checkout steps unless a later
git push from the checkout is required.

### 15. Low: setup-uv caching can poison release artifacts

`zizmor` flagged `astral-sh/setup-uv` caching in the tag-triggered publishing
workflow at `.github/workflows/release.yml:43`.

Impact: runtime artifacts in a publishing workflow can be influenced by a
poisoned cache.

Remediation: disable cache for the release workflow or scope/cache-key it so
untrusted refs cannot influence release builds.

### 16. Medium: Default installer downloads release artifacts without verification

The release workflow creates attestations at `.github/workflows/release.yml:56`,
but `install.sh` downloads the selected wheel at `install.sh:136` and installs
it at `:158` without checksum, signature, or attestation verification. README
recommends piping the installer at `README.md:60`.

Impact: users have no install-time protection if a release asset, account, or
network path is compromised.

Remediation: publish checksums and verify them in installers, or verify GitHub
artifact attestations/Sigstore before `uv tool install`.

### 17. Medium: Runtime dependency ranges are open-ended for released installs

Runtime dependencies use lower bounds only in `pyproject.toml:16` and `:17`.
The installer resolves from live indexes at install time.

Impact: future incompatible `pd-book-tools`, `huggingface_hub`, or transitive
releases can break fresh installs without a code change here.

Remediation: add conservative upper bounds for runtime dependencies and run a
release smoke install from the built wheel using the same indexes as installers.

### 18. Low: README manual install commands use the wrong self-hosted index URL

README manual install examples point to
`https://concavetrillion.github.io/pd-index/simple/` at `README.md:284` and
`:294`, while project config and installer use
`https://concavetrillion.github.io/pd-index-pip/simple/`.

Impact: users following the safer manual install path can fail to resolve
`pd-book-tools` and fall back to the piped installer.

Remediation: correct the README URLs and add a docs/install command smoke check.

### 19. Low: Developer Makefile targets interpolate `ARGS` into shell commands

`Makefile:248` runs `uv run pd-ocr $(ARGS)`, and `Makefile:251` runs
`uv run python $(ARGS)`.

Impact: a developer who copies an untrusted `make run-local ARGS=...` or
`python-local ARGS=...` command can execute shell metacharacters locally.

Remediation: avoid shell-interpolated passthrough for arbitrary args, use a
wrapper script, or clearly document these as trusted developer-only targets.

### 20. Medium: Update check uses `urllib.request.urlopen`

`bandit` flagged `pd_ocr_cli/_update_check.py:81` as B310. The URL is currently
fixed HTTPS, but the code uses a generic URL opener and suppresses all failures.

Impact: future changes could accidentally allow non-HTTPS schemes or make the
update check harder to audit.

Remediation: enforce the expected scheme before opening, keep the URL constant,
or switch to a client path that rejects non-HTTPS schemes by construction.

### 21. Low: Update check swallows all exceptions silently

`bandit` flagged `pd_ocr_cli/_update_check.py:118` as B110.

Impact: update-check regressions, parser changes, or API contract breaks become
silent and can remain undiscovered.

Remediation: keep the best-effort behavior but emit debug-level diagnostics
behind an environment flag or record failures in tests/telemetry-free logs.

### 22. Low: GPU nudge invokes `nvidia-smi` from PATH

`bandit` flagged `pd_ocr_cli/ocr_to_txt.py:242` as B603/B607. The command is
fixed and uses `shell=False`, but the executable is resolved from PATH.

Impact: a malicious earlier PATH entry can run during the optional GPU nudge
probe in a compromised local environment.

Remediation: resolve with `shutil.which()`, execute the resolved absolute path,
and keep `shell=False`.

### 23. High: CI workflow uses mutable actions and `uv latest`

The CI workflow uses `actions/checkout@v4` at `.github/workflows/ci.yml:20`,
`astral-sh/setup-uv@v4` at `:23`, and installs `uv` `latest` at `:25`.
`zizmor` reports both action refs as unpinned.

Impact: a moved or compromised action tag, or a breaking `uv` release, can
change the repository's PR/main quality gate without a code change.

Remediation: pin CI actions by full commit SHA, pin `uv` to a reviewed version,
and update both through explicit maintenance PRs.

### 24. Medium: Untrusted image inputs enter native/DL decoders without resource limits

The CLI accepts inputs in `pd_ocr_cli/ocr_to_txt.py:540`, then passes images to
OCR at `:728`, layout detection at `:743`, and OpenCV crop reads at `:850`.
There is no preflight limit on file size, decoded pixel count, or per-page
processing time.

Impact: huge or malformed images can exhaust CPU/GPU memory or exercise native
parser vulnerabilities in OpenCV/Pillow/DocTR dependency stacks.

Remediation: add configurable file-size, pixel-count, and timeout limits, and
document sandboxing guidance for mixed-trust batches.

### 25. Medium: Invalid inputs still trigger model resolution and loading first

Model work happens before input validation: OCR model resolution at
`pd_ocr_cli/ocr_to_txt.py:649`, layout resolution/prefetch at `:655`, and
model loading at `:665`; input collection and the no-valid-images error happen
later at `:698`.

Impact: `pd-ocr missing.png` or `pd-ocr notes.txt` can resolve/download/load
models before reporting that there is no valid work.

Remediation: collect and validate images before model resolution, prefetch,
device detection, and model loading. Add a regression test that model setup is
not called for an empty input set.

### 26. Medium: Startup model and layout failures can leak raw tracebacks

OCR model resolution only translates `FileNotFoundError` in
`pd_ocr_cli/_hf_models.py:79`; predictor loading catches only `ImportError` in
`pd_ocr_cli/ocr_to_txt.py:666`; layout loading catches only `ImportError` and
`ValueError` at `:680`. Layout resolution and prefetch happen at `:655` before
the per-image error handler.

Impact: invalid Hugging Face repos, network/cache failures, corrupt
checkpoints, incompatible checkpoints, or CUDA/OOM failures can surface as raw
tracebacks instead of concise CLI `ERROR:` output.

Remediation: wrap startup resolution/prefetch/load phases in clean error
handling, with full tracebacks only under `PD_OCR_DEBUG=1`. Add mocked tests
for each startup failure surface.

### 27. High: Default OCR-word preservation is not regression-tested

The repo rule in `CLAUDE.md:39` forbids silently dropping OCR words, and
`docs/architecture/layout-aware-ocr.md:95` says the default preserves every OCR
word. Current tests only assert the kwarg is forwarded in
`tests/test_main_mocked.py:979`, while the slow helper forces
`--layout-model none` in `tests/test_pipeline_integration.py:102` and checks a
small token subset at `:152`.

Impact: a regression in the CLI/layout integration could drop
header/footer/footnote/caption words under the default path while the test
suite still passes.

Remediation: add a CLI-level integration regression using a synthetic page or
fixture that asserts the original OCR word multiset survives default
reorganization.

### 28. Medium: Caption survival with `--no-illustration-placeholders` is not output-tested

Docs promise caption text is preserved at `docs/usage/cli-usage.md:139` and
`:277`. The CLI test at `tests/test_main_mocked.py:1063` only checks
`emit_illustration_placeholders=False` is forwarded; it does not assert the
written `.txt` keeps caption words.

Impact: a future `reorganize_page()` or CLI output change could suppress both
placeholder and caption while the current tests pass.

Remediation: add a CLI-level test with body, figure, and caption content. Run
with and without `--no-illustration-placeholders` and assert only the
placeholder block changes.

### 29. Medium: Default layout-enabled path is not covered by slow end-to-end tests

Layout detection is documented as the default user path, and the argparse
default is `pp-doclayout-plus-l`, but `tests/test_pipeline_integration.py:102`
always adds `--layout-model none` in the slow OCR helper.

Impact: default `pd-ocr page.png` can fail in layout resolution, detector
loading, region detection, or layout-to-reorg wiring while the slow suite
continues to pass.

Remediation: add at least one slow default-layout test that runs without
`--layout-model none` and asserts successful output plus expected layout UX.

### 30. Low: Usage docs understate accepted image suffixes

`docs/usage/cli-usage.md:33` lists common formats but omits JPEG 2000, while
`tests/test_collect_images.py:118` accepts every `SUPPORTED_IMAGE_SUFFIXES`
entry and `tests/test_collect_images.py:132` explicitly asserts `.jp2`
support.

Impact: users with JPEG 2000 scans can assume `pd-ocr` will skip files the
code already accepts.

Remediation: update usage docs to match `pd-book-tools` supported suffixes, or
state that format support is delegated to `pd-book-tools` and include JPEG
2000 examples.

### 31. Low: Pre-commit hooks use mutable tag refs

`.pre-commit-config.yaml` pins hooks by mutable version tags at lines `4`,
`8`, `20`, `24`, `36`, and `61`.

Impact: a compromised or moved upstream hook tag can run code in developer
environments and CI pre-commit runs.

Remediation: pin hooks to commit SHAs, or enforce reviewed `pre-commit
autoupdate` PRs before adopting hook changes.

### 32. Medium: `pd-book-tools` lock entries lack artifact hashes

`uv.lock:1838` points to the `pd-book-tools` sdist URL and `uv.lock:1840`
points to the wheel URL; neither entry carries a hash.

Impact: the lockfile does not provide artifact integrity verification for the
key private dependency.

Remediation: publish PEP 503 hash fragments in `pd-index-pip` or otherwise
lock direct URL hashes, then refresh `uv.lock`.

### 33. Medium: CI does not cover all supported Python versions

Package metadata claims `>=3.10,<3.14` at `pyproject.toml:14`, CI only sets
`UV_PYTHON=3.13` at `.github/workflows/ci.yml:17`, and release builds with
Python 3.12 at `.github/workflows/release.yml:48`.

Impact: Python 3.10, 3.11, or 3.12 runtime/install failures can ship unnoticed.

Remediation: add a CI matrix for supported Python versions, at least smoke
tests plus lock/install checks for 3.10, 3.11, 3.12, and 3.13.

### 34. Low: Release docs contradict the release script's push behavior

`DEVELOPMENT.md:134` says `make release-*` only creates a local tag and does
not push, but `scripts/do-release.sh:143` pushes main plus tags unless
`SKIP_PUSH=1`.

Impact: maintainers can accidentally push a release while expecting a
local-only tag, or run redundant push commands after the script already pushed.

Remediation: align the docs with the script's default push behavior and
`SKIP_PUSH=1`, or change the script to require an explicit push flag.

### 35. Medium: PowerShell installer bypasses the documented release-wheel path

README says installers resolve the latest GitHub Release and download the
published wheel at `README.md:248`, but `install.ps1:137` constructs a
`git+https` source install ref, `:139` resolves tags, and `:156` installs that
git ref directly.

Impact: Windows users bypass the documented release-wheel path and can get
different source-build behavior than Linux/macOS users.

Remediation: make `install.ps1` mirror `install.sh`: resolve the latest
release, download the wheel asset, pass the pd index, and verify provenance
when available.

### 36. Medium: Build backend versions are unbounded for releases

`pyproject.toml:2` declares `hatchling` and `hatch-vcs` without version bounds,
and `.github/workflows/release.yml:50` runs `uv build` in the release workflow.

Impact: a future build backend release can change wheel/sdist contents or
break official release builds without a repository change.

Remediation: pin build backend versions to reviewed ranges or exact versions
and update them through explicit maintenance PRs.

### 37. Medium: Lockfile contains vulnerable `idna==3.13`

`uv.lock:773` pins `idna` `3.13`. `uvx pip-audit -r` against a requirements
file containing `idna==3.13` reports `CVE-2026-45409`, fixed in `idna>=3.15`.

Impact: crafted IDNA inputs can cause CPU denial of service. Direct exposure
in `pd-ocr-cli` appears limited, but the vulnerable package is present in the
runtime dependency graph.

Remediation: upgrade `idna` to `>=3.15`, refresh `uv.lock`, and re-run
`pip-audit` against the full runtime dependency set with the private index
configuration available.
