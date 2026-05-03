.PHONY: setup install reset remove-venv lint format pre-commit-check build clean ci upgrade-pd-book-tools release-patch release-minor release-major _do-release help

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Set up development environment (install deps + pre-commit hooks)
	@echo "📦 Installing dependencies..."
	uv sync --group dev
	@echo "🪝 Setting up pre-commit hooks..."
	uv run pre-commit install
	@echo "✅ Setup complete!"

install: setup ## Alias for setup

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

build: ## Build the project
	@echo "🔨 Building project..."
	uv build

ci: ## Run complete CI pipeline (setup, pre-commit, build)
	@echo "🚀 Running complete CI pipeline..."
	@$(MAKE) --no-print-directory setup
	@$(MAKE) --no-print-directory pre-commit-check
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
