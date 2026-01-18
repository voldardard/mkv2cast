# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `--history N` now accepts optional number of lines (default: 20, max: 1000)
- System-wide cleanup: `--clean-tmp` and `--clean-logs` now clean all users when run as root
- System-wide systemd timer and service files for automated multi-user cleanup
- `.gitignore` file for contributors
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
