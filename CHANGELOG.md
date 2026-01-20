# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

---

## [1.2.9] - 2026-01-20

### Fixed
- **Pipeline Rich UI**:
  - Corrigé un cas où l’encodage avançait bien mais la barre `ENCODE` restait bloquée à 0 % sans ETA sur certaines versions d’FFmpeg (variantes de format de sortie).
  - Unification du parsing de progrès FFmpeg entre le pipeline Rich (`_parse_ffmpeg_progress`) et l’API Python (`parse_ffmpeg_progress`) pour éviter les divergences.
  - Meilleur calcul d’ETA et indicateur explicite quand FFmpeg n’émet pas de statistiques de progrès exploitables.

### Tests
- Ajout de tests pour couvrir les formats de sortie FFmpeg avec virgule décimale (`time=00:01:30,50`) afin de garantir la robustesse du parsing.

---

## [1.2.8] - 2026-01-20

### Added
- **APT Repository GPG Signing**: Full GPG signature support for the APT repository
  - Automatic signing of `Release` file with GPG during repository updates
  - Generation of `Release.gpg` (detached signature) and `InRelease` (inline signed)
  - Public key distribution via GitHub Pages for secure repository verification
  - Support for both passphrase-protected and unprotected GPG keys
- **GPG Key Management Scripts**: New scripts for key generation and export
  - `scripts/generate_gpg_key.sh`: Generate GPG key pairs for repository signing
  - `scripts/export_gpg_key.sh`: Export public keys for distribution
  - Automatic key ID detection and fingerprint display
- **GPG Documentation**: Comprehensive signing guide
  - `docs/package-signing.md`: Complete guide for setting up GPG signing
  - `GPG-KEY.md`: Public key information and verification instructions
  - Key rotation and management best practices
- **Secure Installation Instructions**: Updated APT installation with GPG verification
  - Instructions for importing GPG public key using `signed-by` option
  - Fallback to `trusted=yes` mode when GPG key is not available
  - Key fingerprint verification guidance in documentation

### Changed
- **APT Repository Workflow**: Enhanced `.github/workflows/deb.yml` with GPG signing
  - Automatic import of GPG private key from GitHub Secrets
  - Export and publication of public key to APT repository
  - Graceful degradation when GPG secrets are not configured (warning only)
  - Support for both passphrase-protected and unprotected keys
- **Installation Documentation**: Updated with GPG-secured repository instructions
  - `README.md`: APT installation now uses `signed-by` instead of `trusted=yes`
  - `docs/getting-started/installation.rst`: GPG verification instructions
  - HTML repository page: Dynamic instructions based on key availability
- **Security Enhancements**: Improved `.gitignore` for key protection
  - Automatic exclusion of private key files (`gpg-private-key-*.asc`, `*private*.gpg`)
  - Public keys explicitly allowed in repository
  - Protection against accidental private key commits

### Fixed
- Repository signing workflow handles missing GPG secrets gracefully
- Public key preservation across repository updates
- Key export format compatibility with APT requirements

### Documentation
- New `docs/package-signing.md` guide covering:
  - GPG key generation and setup
  - GitHub Secrets configuration
  - Key rotation procedures
  - Troubleshooting common issues
  - Security best practices
- `GPG-KEY.md` with key information, fingerprint, and verification commands
- Updated installation instructions in README and Sphinx docs

---

## [1.2.7] - 2026-01-27

### Fixed
- Conversion history now records results across all CLI modes (legacy, rich, JSON progress, pipeline, watch)
- Interruptions (Ctrl+C) correctly mark running conversions as interrupted to prevent stale "running" stats

---

## [1.2.5] - 2026-01-26

### Added
- Encoding profiles (fast/balanced/quality) for one-flag tuning
- Disk guards & output quotas to prevent unexpected storage exhaustion
- Metadata/chapters/attachments preservation controls
- Pipeline auto-retry with optional CPU fallback
- Myst-parser is now part of dev dependencies so Sphinx builds work out of the box

### Changed
- AUR and Debian packaging aligned for 1.2.5 release (completions, timers, watch units)
- Documentation and README version references updated to 1.2.5

### Fixed
- Sphinx build failure due to missing `myst_parser` extension

---

## [1.2.3] - 2026-01-19

### Added
- **Python API Progress Callbacks**: New `progress_callback` parameter for `convert_file()`
  - Real-time progress updates with FPS, ETA, bitrate, speed metrics
  - Callback receives `(filepath, progress_dict)` with stage and progress info
  - Stages: "checking", "encoding", "done", "skipped", "failed"
- **Batch Processing Function**: New `convert_batch()` for parallel multi-file processing
  - Uses `ThreadPoolExecutor` for concurrent conversions
  - Respects `encode_workers` configuration for parallelism control
  - Thread-safe callback support for progress tracking
- **Script Mode Detection**: Automatic UI disabling when used as library
  - `is_script_mode()` function to detect non-interactive usage
  - `Config.for_library()` factory method for optimal library configuration
  - Respects `NO_COLOR` and `MKV2CAST_SCRIPT_MODE` environment variables
  - Auto-disables progress bars, notifications, and Rich UI

### Changed
- Rich UI respects `NO_COLOR` environment variable (https://no-color.org/)
- Improved TTY detection for script/library usage

### Fixed
- GitHub Release workflow: AUR and Debian workflows now trigger correctly
  - Added `create-release` job to CI workflow that creates GitHub Releases
  - This triggers the downstream AUR publish and Debian package builds

### Documentation
- New comprehensive Library Usage Guide (`docs/usage/library-guide.rst`)
- Updated Python API documentation with callbacks and batch processing examples
- README updated with advanced Python API usage sections
- Added async integration and webhook integration examples

---

## [1.2.0] - 2026-01-19

### Added
- **NVIDIA NVENC Support**: Hardware-accelerated encoding on NVIDIA GPUs (GTX 600+ series, RTX)
  - Automatic detection and testing in `--check-requirements`
  - `--hw nvenc` option to force NVENC backend
  - `--nvenc-cq` option for constant quality (0-51, default: 23)
  - Priority: NVENC > AMF > QSV > VAAPI > CPU
- **AMD AMF Support**: Hardware-accelerated encoding on AMD GPUs (GCN 2.0+)
  - Automatic detection and testing in `--check-requirements`
  - `--hw amf` option to force AMF backend
  - `--amf-quality` option for quality control (0-51, default: 23)
  - Quality modes mapped from CPU presets (speed/balanced/quality)
- **Audio Track Selection**: Choose audio track by language or index
  - `--audio-lang` for comma-separated language codes (e.g., "fre,fra,fr,eng")
  - `--audio-track` for explicit track index (0-based)
  - Automatic fallback to French, then first available track
- **Subtitle Selection**: Advanced subtitle track selection
  - `--subtitle-lang` for language-based selection
  - `--subtitle-track` for explicit track index
  - `--prefer-forced-subs` to prioritize forced subtitles in audio language (default: enabled)
  - `--no-subtitles` to disable subtitle embedding
- **Watch Mode**: Monitor directories for new MKV files
  - `--watch [DIR]` to watch a directory (default: current directory)
  - `--watch-interval SECONDS` for polling interval (default: 5.0)
  - Uses `watchdog` library if available, falls back to polling
  - Automatic conversion of new files as they appear
- **Systemd Service for Watch Mode**: Run watch mode as a background service
  - `systemd/mkv2cast-watch.service` for user service
  - `systemd/mkv2cast-watch.timer` for boot-time activation (optional)
  - Configurable via environment variables (`MKV2CAST_WATCH_DIR`, `MKV2CAST_WATCH_INTERVAL`)
- **JSON Progress Output**: Structured JSON for integration with external tools
  - `--json-progress` option outputs JSON events to stdout
  - Events: `start`, `file_checking`, `file_start`, `progress`, `file_done`, `complete`
  - Includes progress percentage, FPS, ETA, bitrate, speed, and more
  - Python API: `JSONProgressOutput` class and `parse_ffmpeg_progress_for_json` function
  - Full documentation in Python API guide

### Changed
- Backend priority updated: NVENC > AMF > QSV > VAAPI > CPU
- `--check-requirements` now shows NVENC and AMF status
- Hardware acceleration documentation expanded with NVENC and AMF sections
- Python API exports now include `JSONProgressOutput` and `parse_ffmpeg_progress_for_json`

### Fixed
- Improved type safety with proper type annotations
- Better error handling in watch mode

---

## [1.1.2] - 2026-01-19

### Added
- **AUR Package**: Published on Arch User Repository (`yay -S mkv2cast`)
- **APT Repository**: Debian/Ubuntu users can now add our APT repo for automatic updates
- **AUR Workflow**: Automated publishing to AUR on releases (`.github/workflows/aur.yml`)
- **Debian Workflow**: Automated `.deb` package builds and APT repo updates (`.github/workflows/deb.yml`)
- Makefile targets: `make deb` and `make aur-srcinfo` for local package building
- CI/Docs status badges in Sphinx documentation

### Changed
- Documentation URL changed from readthedocs to GitHub Pages
- Install script version updated to match package version
- `make deploy` now shows all automated actions (PyPI, AUR, Debian, APT repo)

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

[Unreleased]: https://github.com/voldardard/mkv2cast/compare/v1.2.8...HEAD
[1.2.8]: https://github.com/voldardard/mkv2cast/compare/v1.2.7...v1.2.8
[1.2.7]: https://github.com/voldardard/mkv2cast/compare/v1.2.5...v1.2.7
[1.2.5]: https://github.com/voldardard/mkv2cast/compare/v1.2.3...v1.2.5
[1.2.3]: https://github.com/voldardard/mkv2cast/compare/v1.2.0...v1.2.3
[1.2.0]: https://github.com/voldardard/mkv2cast/compare/v1.1.2...v1.2.0
[1.1.2]: https://github.com/voldardard/mkv2cast/compare/v1.1.1...v1.1.2
[1.1.1]: https://github.com/voldardard/mkv2cast/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/voldardard/mkv2cast/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/voldardard/mkv2cast/releases/tag/v1.0.0
