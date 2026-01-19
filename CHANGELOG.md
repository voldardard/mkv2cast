# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

---

## [1.1.2] - 2026-01-19

### Added
- **AUR Package**: Published on Arch User Repository (`yay -S mkv2cast`)
- **AUR Workflow**: Automated publishing to AUR on releases (`.github/workflows/aur.yml`)
- **Debian Workflow**: Automated `.deb` package builds on releases (`.github/workflows/deb.yml`)
- Makefile targets: `make deb` and `make aur-srcinfo` for local package building
- CI/Docs status badges in Sphinx documentation

### Changed
- Documentation URL changed from readthedocs to GitHub Pages
- Install script version updated to match package version

### Fixed
- Documentation badges now show real-time CI and build status

---

## [1.1.1] - 2026-01-19

### Added
- GitHub Actions CI/CD pipeline with automated testing and PyPI publishing
- GitHub Pages documentation deployment
- Makefile with `make release` and `make deploy` commands for simplified releases
- Status badges in README (CI, tests, docs, PyPI version, downloads)
- Code formatting with `ruff format`

### Changed
- Improved Makefile help with categorized commands
- Better release workflow with pre-flight checks

### Fixed
- Ruff formatting applied to all source files
- Documentation workflow resilience when Pages not configured

---

## [1.1.0] - 2026-01-19

### Added
- **Python Package**: Full refactoring into proper Python package (`pip install mkv2cast`)
- **Internationalization (i18n)**: Support for 5 languages (EN, FR, ES, DE, IT)
- **Multi-threaded pipeline**: Parallel integrity checking and encoding workers
- **Rich UI**: Beautiful terminal interface with live progress display
- **Unit tests**: Comprehensive test suite with 136+ tests
- **Documentation**: Sphinx-based documentation with RTD theme
- **Packaging**: Support for PyPI, Arch Linux (PKGBUILD), and Debian
- `--history N` now accepts optional number of lines (default: 20, max: 1000)
- System-wide cleanup: `--clean-tmp` and `--clean-logs` now clean all users when run as root
- System-wide systemd timer and service files for automated multi-user cleanup
- Better terminal width detection for history display

### Changed
- Documentation updated with Arch Linux pacman installation instructions (`python-rich`, `python-tomli`)
- History output now properly truncates filenames based on terminal width
- Improved error handling in `--history` display (silent by default, verbose with MKV2CAST_DEBUG)

### Fixed
- History display no longer shows excess whitespace from incorrect terminal width detection

---

## [1.0.0] - 2026-01-18

### Added

#### Core Features
- Smart MKV to Chromecast-compatible conversion
- Automatic codec detection (H.264, HEVC, AV1, AAC, etc.)
- Hardware acceleration support (Intel VAAPI and QSV)
- Parallel processing pipeline with configurable workers
- Integrity checking of source files before processing
- French audio track preference with fallback

#### User Interface
- Rich progress display with multiple parallel tasks
- ETA and speed indicators
- Color-coded status (done, skipped, failed, in progress)
- Legacy fallback mode when `rich` is not installed

#### Configuration
- TOML configuration file support (with INI fallback)
- XDG Base Directory compliance
- Per-conversion logging
- SQLite history database (with JSONL fallback)

#### Filtering
- Glob pattern-based file filtering (`--ignore-pattern`, `--include-pattern`)
- Path-based filtering (`--ignore-path`, `--include-path`)
- Recursive and non-recursive scanning modes

#### Encoding Options
- Multiple hardware backends: auto, vaapi, qsv, cpu
- Configurable quality settings (CRF, preset, QP)
- Audio bitrate and channel configuration
- Container choice (MKV or MP4)
- HEVC passthrough option for compatible devices

#### Utility Commands
- `--version` display with author and license
- `--check-requirements` for dependency verification
- `--show-dirs` to display XDG directories
- `--history` and `--history-stats` for conversion tracking
- `--clean-tmp`, `--clean-logs`, `--clean-history` for maintenance

#### Installation
- Automated installer (`install.sh`)
- Uninstaller with optional data purge (`uninstall.sh`)
- Man page documentation
- Bash and Zsh completion scripts
- Systemd timer for automatic cleanup

### Technical Details
- Python 3.8+ compatibility
- Thread-safe process management
- Graceful Ctrl+C handling with cleanup
- Atomic file moves to prevent partial outputs

---

## Version History Summary

| Version | Date | Highlights |
|---------|------|------------|
| 1.0.0 | 2026-01-18 | Initial release with full feature set |

---

## Upgrade Notes

### Upgrading to 1.0.0

This is the initial release. For fresh installations, simply run `./install.sh`.

---

## Links

- [GitHub Repository](https://github.com/voldardard/mkv2cast)
- [Issue Tracker](https://github.com/voldardard/mkv2cast/issues)
- [GPL-3.0 License](https://www.gnu.org/licenses/gpl-3.0.html)

[Unreleased]: https://github.com/voldardard/mkv2cast/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/voldardard/mkv2cast/releases/tag/v1.0.0
