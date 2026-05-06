.PHONY: setup refresh-version install uninstall reset remove-venv lint format pre-commit-check test test-slow coverage coverage-slow build clean ci ci-slow upgrade-pd-book-tools release-patch release-minor release-major _do-release help local-setup dev-local install-local uninstall-local check-local-editable run-local python-local

# Coverage thresholds. The fast suite floor is duplicated in pyproject.toml's
# [tool.coverage.report] fail_under so any direct `coverage report` run also
# enforces it. The slow floor only applies to ci-slow / coverage-slow.
COV_FAIL_UNDER ?= 100
COV_FAIL_UNDER_SLOW ?= 100

# ---------------------------------------------------------------------------
# Peer-repo discovery for *-local targets
# ---------------------------------------------------------------------------
# `make *-local` workflows install / run pd-ocr against a sibling pd-book-tools
# checkout instead of the pinned tag in pyproject.toml. PEER_BOOK_TOOLS is the
# absolute path if the sibling exists, or empty otherwise. The require-peer
# guard (used inside each *-local recipe) prints a clear message and exits 1
# when the sibling is missing — no surprise failures from raw uv errors.
# `make local-setup` clones the sibling if missing.
PEER_BOOK_TOOLS_PATH := ../pd-book-tools
PEER_BOOK_TOOLS_REPO := https://github.com/ConcaveTrillion/pd-book-tools.git
PEER_BOOK_TOOLS := $(realpath $(PEER_BOOK_TOOLS_PATH))

define _require_peer_book_tools
	@if [ -z "$(PEER_BOOK_TOOLS)" ]; then \
		echo "❌ Peer repo not found at $(PEER_BOOK_TOOLS_PATH)."; \
		echo "   This *-local target requires pd-book-tools as a sibling checkout."; \
		echo "   Run: make local-setup"; \
		echo "   (or clone manually: git clone $(PEER_BOOK_TOOLS_REPO) $(PEER_BOOK_TOOLS_PATH))"; \
		exit 1; \
	fi
endef

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Set up development environment (sync deps + pre-commit hooks + refresh version)
	@echo "📦 Installing dependencies..."
	uv sync --group dev
	@echo "🪝 Setting up pre-commit hooks..."
	uv run pre-commit install
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

upgrade-pd-book-tools: ## Upgrade pd-book-tools pin to latest GitHub tag
	@./scripts/upgrade-pd-book-tools.sh

lint: ## Run ruff linting and import sorting
	@echo "🔍 Running linting checks..."
	uv run ruff check --select I --fix
	uv run ruff check --fix

format: ## Format code with ruff
	@echo "✨ Formatting code..."
	uv run ruff format
	@$(MAKE) --no-print-directory lint

pre-commit-check: ## Run pre-commit on all files
	@echo "🪝 Running pre-commit on all files..."
	uv run pre-commit run --all-files

test: ## Run the pytest suite (skips @pytest.mark.slow integration tests)
	@echo "🧪 Running tests..."
	uv run pytest tests/ -v

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

ci: ## Run fast CI pipeline (setup → pre-commit → coverage → build); enforces COV_FAIL_UNDER (default 100)
	@echo "🚀 Running fast CI pipeline..."
	@$(MAKE) --no-print-directory setup
	@$(MAKE) --no-print-directory pre-commit-check
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

# ---------------------------------------------------------------------------
# Local editable workflow (requires ../pd-book-tools sibling checkout)
# ---------------------------------------------------------------------------
# Each target self-checks for the peer repo and exits cleanly if absent.
# Env vars (UV_LINK_MODE, UV_NO_SYNC) are scoped per-recipe so they don't
# leak into other targets like `make ci` or `make build`.

local-setup: ## [local-dev] Clone ../pd-book-tools if missing and set up the editable workspace
	@if [ -d "$(PEER_BOOK_TOOLS_PATH)" ]; then \
		echo "✅ Peer repo already at $(PEER_BOOK_TOOLS_PATH) — skipping clone."; \
	else \
		echo "📥 Cloning pd-book-tools from $(PEER_BOOK_TOOLS_REPO)..."; \
		git clone "$(PEER_BOOK_TOOLS_REPO)" "$(PEER_BOOK_TOOLS_PATH)"; \
	fi
	@$(MAKE) --no-print-directory dev-local
	@echo ""
	@echo "💡 Optional: to also set up pd-book-tools' own venv (for running its tests):"
	@echo "      (cd $(PEER_BOOK_TOOLS_PATH) && make setup)"

dev-local: ## [local-dev] Install pd-book-tools from ../pd-book-tools as editable in the venv
	$(call _require_peer_book_tools)
	UV_LINK_MODE=copy uv sync --group dev
	UV_LINK_MODE=copy uv pip install -e "$(PEER_BOOK_TOOLS)"
	@$(MAKE) --no-print-directory check-local-editable
	@echo "✅ Local editable pd-book-tools is active in the venv."

install-local: ## [local-dev] Install pd-ocr as a uv tool with both pd-ocr-cli and ../pd-book-tools editable
	$(call _require_peer_book_tools)
	@echo "📦 Installing pd-ocr as a uv tool from local editable sources..."
	UV_LINK_MODE=copy uv tool install --force --reinstall --no-sources --editable . --with-editable "$(PEER_BOOK_TOOLS)"
	@echo "✅ 'pd-ocr' is on PATH and tracks ./ + $(PEER_BOOK_TOOLS) live."
	@echo "   To revert: make uninstall-local && curl -sSL https://raw.githubusercontent.com/ConcaveTrillion/pd-ocr-cli/main/install.sh | sh"

uninstall-local: ## [local-dev] Uninstall the locally-installed pd-ocr uv tool
	@echo "🗑️  Uninstalling pd-ocr uv tool..."
	uv tool uninstall pd-ocr-cli || true
	@echo "✅ pd-ocr removed."

check-local-editable: ## [local-dev] Verify pd-book-tools resolves to ../pd-book-tools (not the pinned tag)
	$(call _require_peer_book_tools)
	@env -u VIRTUAL_ENV UV_NO_SYNC=1 uv run python scripts/check-editable.py "$(PEER_BOOK_TOOLS)" || (echo "❌ pd-book-tools is not local/editable. Run: make dev-local" >&2; exit 1)
	@echo "✅ pd-book-tools resolves to local editable copy."

run-local: check-local-editable ## [local-dev] Run pd-ocr against the local editable workspace; pass ARGS="..."
	@if [ -z "$(ARGS)" ]; then \
		echo "Usage: make run-local ARGS='page.png'" >&2; \
		exit 2; \
	fi
	env -u VIRTUAL_ENV UV_NO_SYNC=1 uv run pd-ocr $(ARGS)

python-local: check-local-editable ## [local-dev] Run python against the local editable workspace; pass ARGS="..."
	env -u VIRTUAL_ENV UV_NO_SYNC=1 uv run python $(ARGS)
