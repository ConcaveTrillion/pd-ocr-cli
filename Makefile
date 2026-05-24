AI ?=
LOG := .ci-ai.log

ifdef AI
_goals := $(or $(MAKECMDGOALS),ci)
.PHONY: $(_goals)
$(_goals):
	@rm -f $(LOG)
	@$(MAKE) --no-print-directory AI= $@ > $(LOG) 2>&1 \
		&& echo "✅ $@ passed (log: $(LOG))" \
		|| (echo "❌ $@ failed:"; uv run scripts/ai-filter-log.py $(LOG); echo "(full log: $(LOG))"; exit 1)

else

.PHONY: setup refresh-version install uninstall reset remove-venv upgrade-deps lint format format-check pre-commit-check typecheck test test-slow coverage coverage-slow build clean ci ci-slow upgrade-pd-book-tools update-pd-deps release-patch release-minor release-major _do-release help \
        local-setup local-dev local-check local-upgrade-deps local-install local-uninstall local-run \
        dev-local install-local uninstall-local check-local-editable upgrade-deps-local run-local

# Coverage thresholds. The fast suite floor is duplicated in pyproject.toml's
# [tool.coverage.report] fail_under so any direct `coverage report` run also
# enforces it. The slow floor only applies to ci-slow / coverage-slow.
COV_FAIL_UNDER ?= 100
COV_FAIL_UNDER_SLOW ?= 100

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Set up development environment (sync deps + pre-commit hooks + refresh version)
	@echo "📦 Installing dependencies..."
	uv sync --group dev
	@echo "🪝 Setting up pre-commit hooks..."
	@[ -f .git/hooks/pre-commit ] || uv run pre-commit install
	@$(MAKE) --no-print-directory refresh-version
	@echo "✅ Setup complete!"

refresh-version: ## Force hatch-vcs to re-derive `pd-ocr --version` from current git state (~1s)
	@echo "🔄 Reinstalling pd-ocr-cli so hatch-vcs picks up the current HEAD / tags..."
	@UV_LINK_MODE=copy uv pip install -e . --reinstall-package pd-ocr-cli
	@echo "✅ Version now reports as:"
	@uv run pd-ocr --version

install: ## Install pd-ocr as a uv tool from the local source (auto-detects CUDA)
	@./scripts/install-uv-tool.sh

uninstall: ## Remove the installed pd-ocr uv tool
	@echo "🗑️  Uninstalling pd-ocr..."
	uv tool uninstall pd-ocr-cli || true
	@echo "✅ pd-ocr uninstalled."

remove-venv: ## Remove the virtual environment
	@echo "🗑️  Removing existing virtual environment..."
	rm -rf .venv
	@echo "✅ Virtual environment removed!"

reset: ## Rebuild virtual environment (keeps UV cache)
	@$(MAKE) --no-print-directory clean
	@$(MAKE) --no-print-directory remove-venv
	@$(MAKE) --no-print-directory setup
	@echo "✅ Environment Reset!"

# ---------------------------------------------------------------------------
# Local-dev detection for upgrade-deps guard
# ---------------------------------------------------------------------------
# Two-tier probe: uv pip show (editable) → marker file.
# Intentionally POSIX sh compatible (no bash-isms).
define _is_local_dev
	( uv pip show pd-book-tools 2>/dev/null | grep -q "^Editable project location:" ) \
	|| [ -f .venv/.pd-local-mode ]
endef

upgrade-deps: ## Upgrade dependencies and sync (refuses in local-dev mode; use local-upgrade-deps instead)
	@if $(call _is_local_dev); then \
		echo ""; \
		echo "❌ local-dev install detected (editable siblings present)."; \
		echo "    Running 'uv sync' here would revert the venv to the canonical baseline."; \
		echo "   Use 'make local-upgrade-deps' to upgrade and restore editable siblings."; \
		echo ""; \
		exit 1; \
	fi
	@echo "Upgrading dependency lockfile..."
	uv lock --upgrade
	@echo "Syncing upgraded dependencies..."
	uv sync --group dev
	@echo "Dependencies upgraded and environment synced!"

update-pd-deps: ## Bump sibling pd-* deps to registry latest; leaves diff staged
	@./scripts/update-pd-deps.sh

upgrade-pd-book-tools: ## Deprecated: use 'make update-pd-deps' instead
	@echo "⚠️  upgrade-pd-book-tools is deprecated; use 'make update-pd-deps' instead."
	@$(MAKE) --no-print-directory update-pd-deps

lint: ## Run ruff linting and import sorting
	@echo "🔍 Running linting checks..."
	uv run ruff check --select I --fix
	uv run ruff check --fix

format: ## Format code with ruff
	@echo "✨ Formatting code..."
	uv run ruff format
	@$(MAKE) --no-print-directory lint

format-check: ## Read-only ruff format+lint check (no auto-fix; matches CI exactly)
	@echo "🔍 Checking format and lint (read-only)..."
	uv run ruff format --check .
	uv run ruff check .

pre-commit-check: ## Run pre-commit on all files
	@echo "🪝 Running pre-commit on all files..."
	uv run pre-commit run --all-files

typecheck: ## Run basedpyright at recommended mode (workspace canonical)
	uv run basedpyright pd_ocr_cli --level error

test: ## Run the pytest suite (skips @pytest.mark.slow integration tests)
	@echo "🧪 Running tests..."
	uv run pytest tests/ -v -n auto

test-slow: ## Run the full pytest suite including slow integration tests (downloads pinned model on first run)
	@echo "🧪 Running tests (including slow)..."
	uv run pytest tests/ -v --run-slow

coverage: ## Run fast tests with coverage + HTML report; fails if total drops below COV_FAIL_UNDER (default 100)
	@echo "🧪 Running tests with coverage (threshold: $(COV_FAIL_UNDER)%)..."
	uv run pytest tests/ --cov=pd_ocr_cli --cov-report=term-missing --cov-report=html --cov-report=xml --cov-fail-under=$(COV_FAIL_UNDER)
	@echo "📊 Coverage report: htmlcov/index.html"

coverage-slow: ## Run full suite (incl. slow) with coverage; fails if total drops below COV_FAIL_UNDER_SLOW (default 100)
	@echo "🧪 Running tests with coverage including slow integration (threshold: $(COV_FAIL_UNDER_SLOW)%)..."
	uv run pytest tests/ --run-slow --cov=pd_ocr_cli --cov-report=term-missing --cov-report=html --cov-report=xml --cov-fail-under=$(COV_FAIL_UNDER_SLOW)
	@echo "📊 Coverage report: htmlcov/index.html"

build: ## Build the project
	@echo "🔨 Building project..."
	uv build

ci: ## Run fast CI pipeline (setup → pre-commit → typecheck → coverage → build); enforces COV_FAIL_UNDER (default 100)
	@echo "🚀 Running fast CI pipeline..."
	@$(MAKE) --no-print-directory setup
	@$(MAKE) --no-print-directory pre-commit-check
	@$(MAKE) --no-print-directory typecheck
	@$(MAKE) --no-print-directory coverage
	@$(MAKE) --no-print-directory build
	@echo "✅ CI pipeline complete!"

ci-slow: ## Run full CI pipeline including slow integration tests; enforces COV_FAIL_UNDER_SLOW (default 100)
	@echo "🚀 Running full CI pipeline (including slow integration tests)..."
	@$(MAKE) --no-print-directory setup
	@$(MAKE) --no-print-directory pre-commit-check
	@$(MAKE) --no-print-directory coverage-slow
	@$(MAKE) --no-print-directory build
	@echo "✅ Full CI pipeline complete!"

clean: ## Clean up cache and build artifacts
	@echo "🧹 Cleaning Python cache files..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@echo "🧹 Cleaning coverage artifacts..."
	rm -rf htmlcov/ 2>/dev/null || true
	rm -f coverage.xml .coverage 2>/dev/null || true
	@echo "🧹 Cleaning build artifacts..."
	rm -rf dist/ 2>/dev/null || true
	@echo "✅ Cleanup complete!"

release-patch: ## Release: bump patch, run ci-slow, tag, push (fires GitHub Release workflow; e.g. v0.4.2 → v0.4.3)
	@$(MAKE) --no-print-directory _do-release BUMP=patch

release-minor: ## Release: bump minor, run ci-slow, tag, push (fires GitHub Release workflow; e.g. v0.4.2 → v0.5.0)
	@$(MAKE) --no-print-directory _do-release BUMP=minor

release-major: ## Release: bump major, run ci-slow, tag, push (fires GitHub Release workflow; e.g. v0.4.2 → v1.0.0)
	@$(MAKE) --no-print-directory _do-release BUMP=major

# scripts/do-release.sh handles repo-state guards, runs the ci-slow pre-flight,
# creates the three-component tag, and pushes main + tag (which fires the
# GitHub Release workflow at .github/workflows/release.yml).
# Pass FORCE=1 to skip the repo-state guards (pre-flight still runs).
# Pass SKIP_PUSH=1 to create the tag locally without pushing (dry-run).
_do-release:
	@BUMP=$(or $(BUMP),minor) ./scripts/do-release.sh

# ─── local-dev workflow (spec #362) ─────────────────────────────────────────

local-setup: ## Clone any missing sibling pd-* repos into the workspace
	@./scripts/local-setup.sh

local-dev: ## Switch to local-dev mode (siblings editable + marker)
	@./scripts/local-dev.sh

local-check: ## Print local-dev mode status + per-sibling resolution
	@./scripts/local-check.sh

local-upgrade-deps: ## Upgrade deps then restore editable siblings (local-mode only)
	@./scripts/local-upgrade-deps.sh

local-install: ## Install uv tool with editable siblings (local-mode only)
	@./scripts/local-install.sh

local-uninstall: ## Uninstall the uv tool (siblings + venv untouched)
	@./scripts/local-uninstall.sh

local-run: ## Run the CLI/server against local-dev workspace (local-mode only)
	@./scripts/local-run.sh

# ─── deprecation aliases ─────────────────────────────────────────────────────

dev-local: ## DEPRECATED: use local-dev
	@echo "warning: 'dev-local' is deprecated; use 'local-dev'"
	@$(MAKE) --no-print-directory local-dev

install-local: ## DEPRECATED: use local-install
	@echo "warning: 'install-local' is deprecated; use 'local-install'"
	@$(MAKE) --no-print-directory local-install

uninstall-local: ## DEPRECATED: use local-uninstall
	@echo "warning: 'uninstall-local' is deprecated; use 'local-uninstall'"
	@$(MAKE) --no-print-directory local-uninstall

check-local-editable: ## DEPRECATED: use local-check
	@echo "warning: 'check-local-editable' is deprecated; use 'local-check'"
	@$(MAKE) --no-print-directory local-check

upgrade-deps-local: ## DEPRECATED: use local-upgrade-deps
	@echo "warning: 'upgrade-deps-local' is deprecated; use 'local-upgrade-deps'"
	@$(MAKE) --no-print-directory local-upgrade-deps

run-local: ## DEPRECATED: use local-run
	@echo "warning: 'run-local' is deprecated; use 'local-run'"
	@$(MAKE) --no-print-directory local-run

endif
