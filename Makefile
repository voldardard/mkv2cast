# mkv2cast Makefile

.PHONY: all build install clean test lint translations help version release deploy format check deb aur-srcinfo

# Auto-detect venv if it exists
ifeq ($(wildcard .venv/bin/python),)
  PYTHON ?= python3
  PIP ?= pip3
else
  PYTHON ?= .venv/bin/python
  PIP ?= .venv/bin/pip
endif
LOCALES_DIR = src/mkv2cast/locales
LANGUAGES = en fr es it de
CURRENT_VERSION := $(shell grep -Po '__version__ = "\K[^"]+' src/mkv2cast/__init__.py 2>/dev/null || echo "unknown")

all: translations build

help:
	@echo "mkv2cast build commands:"
	@echo ""
	@echo "  Development:"
	@echo "    make install      - Install package in dev mode"
	@echo "    make test         - Run unit tests"
	@echo "    make lint         - Run linter (ruff check)"
	@echo "    make format       - Format code with ruff"
	@echo "    make check        - Run all checks (lint + test)"
	@echo ""
	@echo "  Build:"
	@echo "    make translations - Compile .po files to .mo files"
	@echo "    make build        - Build Python package"
	@echo "    make clean        - Remove build artifacts"
	@echo "    make all          - translations + build"
	@echo ""
	@echo "  Release:"
	@echo "    make version      - Show current version"
	@echo "    make release V=x.y.z - Bump version, run checks, and build"
	@echo "    make deploy V=x.y.z [FORCE=1] - Full release: bump, check, build, commit, tag, push"
	@echo "                                    Use FORCE=1 to overwrite existing tag"
	@echo ""
	@echo "  Packaging:"
	@echo "    make deb          - Build Debian package (requires devscripts)"
	@echo "    make aur-srcinfo  - Generate .SRCINFO for AUR"
	@echo ""
	@echo "  Current version: $(CURRENT_VERSION)"

version:
	@echo "$(CURRENT_VERSION)"

# Bump version, run checks, and build
release:
ifndef V
	$(error Usage: make release V=1.2.0)
endif
	@echo "══════════════════════════════════════════════════════"
	@echo "  Preparing release v$(V)"
	@echo "══════════════════════════════════════════════════════"
	@echo ""
	@echo "→ Bumping version to $(V)..."
	@./scripts/bump_version.sh $(V)
	@echo ""
	@echo "→ Cleaning build artifacts..."
	@$(MAKE) clean
	@echo ""
	@echo "→ Running checks..."
	@$(MAKE) check
	@echo ""
	@echo "→ Building package..."
	@$(MAKE) all
	@echo ""
	@echo "══════════════════════════════════════════════════════"
	@echo "  ✓ Release v$(V) prepared successfully!"
	@echo ""
	@echo "  Next steps:"
	@echo "    make deploy V=$(V)   # Commit, tag, and push"
	@echo "══════════════════════════════════════════════════════"

# Full deployment: release + git operations
deploy:
ifndef V
	$(error Usage: make deploy V=1.2.0 [FORCE=1])
endif
	@echo "══════════════════════════════════════════════════════"
	@echo "  Deploying release v$(V)"
	@if [ "$(FORCE)" = "1" ]; then \
		echo "  [FORCE MODE: Will overwrite existing tag]"; \
	fi
	@echo "══════════════════════════════════════════════════════"
	@echo ""
	@echo "→ Formatting code..."
	@$(MAKE) format
	@echo ""
	@# Check if working directory is clean (except for version changes)
	@if [ -n "$$(git status --porcelain)" ]; then \
		echo "→ Staging all changes..."; \
		git add -A; \
	fi
	@echo "→ Committing release..."
	@git commit -m "chore: release v$(V)" --allow-empty
	@echo ""
	@# Check if version has patch number (contains -N)
	@if echo "$(V)" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+-[0-9]+$$'; then \
		echo "→ Creating tag v$(V) (patch release)..."; \
		git tag -d v$(V) 2>/dev/null || true; \
		if [ "$(FORCE)" = "1" ]; then \
			echo "  → Deleting remote tag (force mode)..."; \
			git push origin :refs/tags/v$(V) 2>/dev/null || true; \
		fi; \
		git tag v$(V) -m "Release v$(V)"; \
	else \
		echo "→ Creating tags v$(V) and v$(V)-1 (base + patch release)..."; \
		BASE_TAG="v$(V)"; \
		PATCH_TAG="v$(V)-1"; \
		git tag -d $$BASE_TAG 2>/dev/null || true; \
		git tag -d $$PATCH_TAG 2>/dev/null || true; \
		if [ "$(FORCE)" = "1" ]; then \
			echo "  → Deleting remote tags (force mode)..."; \
			git push origin :refs/tags/$$BASE_TAG 2>/dev/null || true; \
			git push origin :refs/tags/$$PATCH_TAG 2>/dev/null || true; \
		fi; \
		git tag $$BASE_TAG -m "Release $$BASE_TAG"; \
		git tag $$PATCH_TAG -m "Release $$PATCH_TAG"; \
	fi
	@echo ""
	@echo "→ Pushing to origin..."
	@if [ "$(FORCE)" = "1" ]; then \
		git push origin HEAD --tags --force; \
	else \
		git push origin HEAD --tags; \
	fi
	@echo ""
	@echo "══════════════════════════════════════════════════════"
	@echo "  ✓ Release v$(V) deployed!"
	@echo ""
	@echo "  GitHub Actions will now:"
	@echo "    • Run CI tests"
	@echo "    • Build and deploy documentation"
	@echo "    • Publish to PyPI"
	@echo "    • Update AUR package"
	@echo "    • Build Debian package (.deb)"
	@echo "    • Update APT repository"
	@echo ""
	@echo "  Monitor: https://github.com/voldardard/mkv2cast/actions"
	@echo "══════════════════════════════════════════════════════"

# Run all checks (format first, then lint, then test)
check: format lint test
	@echo "✓ All checks passed!"

# Format code (auto-fix issues)
format:
	@echo "→ Formatting code..."
	@$(PYTHON) -m ruff format src/ tests/
	@$(PYTHON) -m ruff check --fix src/ tests/ 2>/dev/null || true

translations:
	@echo "Compiling translation files..."
	@for lang in $(LANGUAGES); do \
		if [ -f "$(LOCALES_DIR)/$$lang/LC_MESSAGES/mkv2cast.po" ]; then \
			msgfmt -o "$(LOCALES_DIR)/$$lang/LC_MESSAGES/mkv2cast.mo" \
			       "$(LOCALES_DIR)/$$lang/LC_MESSAGES/mkv2cast.po" && \
			echo "  Compiled $$lang"; \
		fi; \
	done
	@echo "Done."

build: translations
	$(PYTHON) -m build

install: translations
	$(PIP) install -e ".[full,dev]"

test:
	$(PYTHON) -m pytest tests/ -v

lint:
	$(PYTHON) -m ruff check src/ tests/

clean:
	rm -rf build/ dist/ *.egg-info/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.mo" -delete 2>/dev/null || true

# ==================== Package Building ====================

# Build Debian package (requires: devscripts debhelper dh-python)
deb:
	@echo "Building Debian package..."
	@if ! command -v dpkg-buildpackage >/dev/null 2>&1; then \
		echo "Error: dpkg-buildpackage not found. Install devscripts:"; \
		echo "  sudo apt install devscripts debhelper dh-python"; \
		exit 1; \
	fi
	@mkdir -p build-deb
	@cp -r src pyproject.toml README.md LICENSE CHANGELOG.md man completions systemd build-deb/
	@cp -r packaging/debian build-deb/
	@cd build-deb && dpkg-buildpackage -us -uc -b
	@echo "Package built: $$(ls build-deb/../*.deb 2>/dev/null || echo 'check parent directory')"

# Generate .SRCINFO for AUR (requires: makepkg from pacman)
aur-srcinfo:
	@echo "Generating .SRCINFO for AUR..."
	@if ! command -v makepkg >/dev/null 2>&1; then \
		echo "Error: makepkg not found. This target requires Arch Linux."; \
		exit 1; \
	fi
	@cd packaging/arch && makepkg --printsrcinfo > .SRCINFO
	@echo "Generated: packaging/arch/.SRCINFO"
