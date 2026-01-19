# mkv2cast Makefile

.PHONY: all build install clean test lint translations help version release

PYTHON ?= python3
PIP ?= pip3
LOCALES_DIR = src/mkv2cast/locales
LANGUAGES = en fr es it de

all: translations build

help:
	@echo "mkv2cast build commands:"
	@echo "  make translations  - Compile .po files to .mo files"
	@echo "  make build         - Build Python package"
	@echo "  make install       - Install package in dev mode"
	@echo "  make test          - Run unit tests"
	@echo "  make lint          - Run linter (ruff)"
	@echo "  make clean         - Remove build artifacts"
	@echo "  make all           - translations + build"
	@echo "  make version       - Show current version"
	@echo "  make release V=x.y.z - Change version and build"

version:
	@grep -Po '__version__ = "\K[^"]+' src/mkv2cast/__init__.py

release:
ifndef V
	$(error Usage: make release V=1.2.0)
endif
	@echo "Bumping version to $(V)..."
	@./scripts/bump_version.sh $(V)
	@$(MAKE) clean
	@$(MAKE) all

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
