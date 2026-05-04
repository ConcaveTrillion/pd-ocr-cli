.PHONY: setup install uninstall reset remove-venv lint format pre-commit-check test build clean ci upgrade-pd-book-tools release-patch release-minor release-major _do-release help local-setup dev-local install-local uninstall-local check-local-editable run-local python-local

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

setup: ## Set up development environment (sync deps + pre-commit hooks)
	@echo "📦 Installing dependencies..."
	uv sync --group dev
	@echo "🪝 Setting up pre-commit hooks..."
	uv run pre-commit install
	@echo "✅ Setup complete!"

install: ## Install pd-ocr as a uv tool from the local source (auto-detects CUDA)
	@EXTRA_INDEX=""; \
	if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then \
		CUDA_VER=$$(nvidia-smi 2>/dev/null | sed -n 's/.*CUDA Version: \([0-9]*\.[0-9]*\).*/\1/p' | head -1); \
		if [ -n "$$CUDA_VER" ]; then \
			CUDA_TAG="cu$$(echo "$$CUDA_VER" | tr -d '.')"; \
			EXTRA_INDEX="https://download.pytorch.org/whl/$$CUDA_TAG"; \
			echo "🟢 Detected CUDA $$CUDA_VER — installing PyTorch with $$CUDA_TAG support."; \
		else \
			echo "⚠️  nvidia-smi found but could not detect CUDA version — falling back to CPU."; \
		fi; \
	elif [ "$$(uname)" = "Darwin" ] && [ "$$(uname -m)" = "arm64" ]; then \
		echo "🍎 Detected Apple Silicon — MPS acceleration will be used automatically."; \
	else \
		echo "💻 No GPU detected — installing CPU-only PyTorch."; \
	fi; \
	echo "📦 Installing pd-ocr from local source..."; \
	if [ -n "$$EXTRA_INDEX" ]; then \
		uv tool install --reinstall . --extra-index-url "$$EXTRA_INDEX"; \
	else \
		uv tool install --reinstall .; \
	fi; \
	echo "✅ pd-ocr installed. Run: pd-ocr --version"

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
	@echo "🔍 Fetching latest pd-book-tools tag..."
	$(eval LATEST_TAG := $(shell curl -sSf "https://api.github.com/repos/ConcaveTrillion/pd-book-tools/tags" | grep '"name"' | head -1 | sed 's/.*"name": "\(.*\)".*/\1/'))
	@if [ -z "$(LATEST_TAG)" ]; then echo "❌ Could not fetch latest tag." && exit 1; fi
	@echo "📌 Pinning to $(LATEST_TAG)..."
	@sed -i 's|pd-book-tools = { git = "https://github.com/ConcaveTrillion/pd-book-tools.git", tag = ".*" }|pd-book-tools = { git = "https://github.com/ConcaveTrillion/pd-book-tools.git", tag = "$(LATEST_TAG)" }|' pyproject.toml
	@echo "📦 Syncing..."
	uv sync --group dev
	@echo "✅ pd-book-tools upgraded to $(LATEST_TAG)!"

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

test: ## Run the pytest suite
	@echo "🧪 Running tests..."
	uv run pytest tests/ -v

build: ## Build the project
	@echo "🔨 Building project..."
	uv build

ci: ## Run complete CI pipeline (setup, pre-commit, test, build)
	@echo "🚀 Running complete CI pipeline..."
	@$(MAKE) --no-print-directory setup
	@$(MAKE) --no-print-directory pre-commit-check
	@$(MAKE) --no-print-directory test
	@$(MAKE) --no-print-directory build
	@echo "✅ CI pipeline complete!"

clean: ## Clean up cache and build artifacts
	@echo "🧹 Cleaning Python cache files..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@echo "🧹 Cleaning build artifacts..."
	rm -rf dist/ 2>/dev/null || true
	@echo "✅ Cleanup complete!"

release-patch: ## Bump patch version and create a git tag (e.g. v0.3 → v0.3.1)
	@$(MAKE) --no-print-directory _do-release BUMP=patch

release-minor: ## Bump minor version and create a git tag (e.g. v0.3 → v0.4)
	@$(MAKE) --no-print-directory _do-release BUMP=minor

release-major: ## Bump major version and create a git tag (e.g. v0.3 → v1.0)
	@$(MAKE) --no-print-directory _do-release BUMP=major

_do-release:
	@BUMP=$(or $(BUMP),minor); \
	LATEST=$$(git tag --list 'v*' --sort=-version:refname | head -1); \
	if [ -z "$$LATEST" ]; then LATEST="v0.0"; fi; \
	MAJOR=$$(echo "$$LATEST" | sed 's/v\([0-9]*\)\..*/\1/'); \
	MINOR=$$(echo "$$LATEST" | sed 's/v[0-9]*\.\([0-9]*\).*/\1/'); \
	PATCH=$$(echo "$$LATEST" | sed 's/v[0-9]*\.[0-9]*\.\([0-9]*\).*/\1/'); \
	if [ "$$PATCH" = "$$LATEST" ]; then PATCH=0; fi; \
	if [ "$$BUMP" = "major" ]; then MAJOR=$$((MAJOR+1)); MINOR=0; PATCH=0; \
	elif [ "$$BUMP" = "minor" ]; then MINOR=$$((MINOR+1)); PATCH=0; \
	else PATCH=$$((PATCH+1)); fi; \
	VERSION="v$$MAJOR.$$MINOR"; \
	if [ "$$BUMP" = "patch" ]; then VERSION="v$$MAJOR.$$MINOR.$$PATCH"; fi; \
	git tag "$$VERSION"; \
	echo "🏷️  Tagged $$VERSION — push with: git push && git push --tags"

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
	@env -u VIRTUAL_ENV UV_NO_SYNC=1 uv run python -c "import inspect, os, sys, importlib.metadata as md, pd_book_tools; \
module_file = os.path.realpath(inspect.getfile(pd_book_tools)); \
peer = os.path.realpath('$(PEER_BOOK_TOOLS)'); \
is_local = module_file.startswith(peer + os.sep) or module_file == peer; \
print('module_file=', module_file); \
print('expected_peer=', peer); \
print('dist_version=', md.version('pd-book-tools')); \
sys.exit(0 if is_local else 1)" || (echo "❌ pd-book-tools is not local/editable. Run: make dev-local" >&2; exit 1)
	@echo "✅ pd-book-tools resolves to local editable copy."

run-local: check-local-editable ## [local-dev] Run pd-ocr against the local editable workspace; pass ARGS="..."
	@if [ -z "$(ARGS)" ]; then \
		echo "Usage: make run-local ARGS='page.png'" >&2; \
		exit 2; \
	fi
	env -u VIRTUAL_ENV UV_NO_SYNC=1 uv run pd-ocr $(ARGS)

python-local: check-local-editable ## [local-dev] Run python against the local editable workspace; pass ARGS="..."
	env -u VIRTUAL_ENV UV_NO_SYNC=1 uv run python $(ARGS)
