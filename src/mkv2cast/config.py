"""
Configuration management for mkv2cast.

Handles:
- XDG Base Directory compliance
- TOML/INI configuration file loading
- Config dataclass with all options
- Configuration merging (system -> user -> CLI)
- Automatic script mode detection
"""

import configparser
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# -------------------- SCRIPT MODE DETECTION --------------------


def is_script_mode() -> bool:
    """
    Detect if running as a library (not CLI).

    Returns True if:
    - stdout is not a TTY (piped or redirected)
    - NO_COLOR environment variable is set
    - MKV2CAST_SCRIPT_MODE environment variable is set
    - Being imported as a library (not running as __main__)

    Returns:
        True if running in script mode, False otherwise.
    """
    # Check if stdout is a TTY
    try:
        if not sys.stdout.isatty():
            return True
    except Exception:
        return True

    # Check environment variables
    if os.getenv("NO_COLOR") or os.getenv("MKV2CAST_SCRIPT_MODE"):
        return True

    # Check if being imported (not __main__)
    try:
        import __main__

        # If __main__ has no __file__, we're likely in an interactive session or import
        if not hasattr(__main__, "__file__"):
            return True
        # Check if the main module is mkv2cast CLI
        main_file = getattr(__main__, "__file__", "") or ""
        if "mkv2cast" not in main_file.lower():
            return True
    except Exception:
        pass

    return False


# Try TOML support (Python 3.11+ or tomli package)
try:
    import tomllib  # Python 3.11+

    TOML_AVAILABLE = True
except ImportError:
    try:
        import tomli as tomllib  # pip install tomli

        TOML_AVAILABLE = True
    except ImportError:
        TOML_AVAILABLE = False


# -------------------- XDG DIRECTORIES --------------------


def get_xdg_config_home() -> Path:
    """Get XDG config home directory."""
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def get_xdg_state_home() -> Path:
    """Get XDG state home directory."""
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))


def get_xdg_cache_home() -> Path:
    """Get XDG cache home directory."""
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))


def get_app_dirs() -> Dict[str, Path]:
    """Return all application directories, creating them if needed."""
    dirs = {
        "config": get_xdg_config_home() / "mkv2cast",
        "state": get_xdg_state_home() / "mkv2cast",
        "logs": get_xdg_state_home() / "mkv2cast" / "logs",
        "cache": get_xdg_cache_home() / "mkv2cast",
        "tmp": get_xdg_cache_home() / "mkv2cast" / "tmp",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


# -------------------- CONFIGURATION DATACLASS --------------------


@dataclass
class Config:
    """All configuration options for mkv2cast."""

    # Output settings
    suffix: str = ".cast"
    container: str = "mkv"

    # Scan settings
    recursive: bool = True
    ignore_patterns: List[str] = field(default_factory=list)
    ignore_paths: List[str] = field(default_factory=list)
    include_patterns: List[str] = field(default_factory=list)
    include_paths: List[str] = field(default_factory=list)

    # Debug/test
    debug: bool = False
    dryrun: bool = False

    # Codec decisions
    skip_when_ok: bool = True
    force_h264: bool = False
    allow_hevc: bool = False
    force_aac: bool = False
    keep_surround: bool = False
    add_silence_if_no_audio: bool = True

    # Encoding quality
    abr: str = "192k"
    crf: int = 20
    preset: str = "slow"

    # Hardware acceleration
    vaapi_device: str = "/dev/dri/renderD128"
    vaapi_qp: int = 23
    qsv_quality: int = 23
    nvenc_cq: int = 23  # NVIDIA NVENC constant quality (0-51, lower=better)
    amf_quality: int = 23  # AMD AMF quality (0-51, lower=better)
    hw: str = "auto"  # auto, nvenc, amf, qsv, vaapi, cpu

    # Audio track selection
    audio_lang: Optional[str] = None  # Comma-separated language codes (e.g., "fre,fra,fr,eng")
    audio_track: Optional[int] = None  # Explicit audio track index

    # Subtitle selection
    subtitle_lang: Optional[str] = None  # Comma-separated language codes
    subtitle_track: Optional[int] = None  # Explicit subtitle track index
    prefer_forced_subs: bool = True  # Prefer forced subtitles in audio language
    no_subtitles: bool = False  # Disable all subtitles

    # Integrity checks
    integrity_check: bool = True
    stable_wait: int = 3
    deep_check: bool = False

    # UI settings
    progress: bool = True
    bar_width: int = 26
    ui_refresh_ms: int = 120
    stats_period: float = 0.2

    # Pipeline mode
    pipeline: bool = True

    # Parallelism (0 = auto)
    encode_workers: int = 0
    integrity_workers: int = 0

    # Notifications (new)
    notify: bool = True
    notify_on_success: bool = True
    notify_on_failure: bool = True

    # Internationalization (new)
    lang: Optional[str] = None

    # JSON progress output (new)
    json_progress: bool = False

    def __post_init__(self):
        """Apply automatic script mode detection after initialization."""
        # Don't auto-disable if explicitly running in CLI mode
        # (CLI will set these values explicitly)
        pass

    def apply_script_mode(self) -> None:
        """
        Automatically disable UI features when running in script mode.

        Call this method when using mkv2cast as a library to ensure
        no unwanted output is generated.

        Disables:
        - progress: No progress bars
        - notify: No desktop notifications
        - pipeline: No Rich UI (use simple sequential mode)
        """
        if is_script_mode():
            self.progress = False
            self.notify = False
            self.pipeline = False

    @classmethod
    def for_library(cls, **kwargs) -> "Config":
        """
        Create a Config instance optimized for library usage.

        Automatically disables UI features (progress bars, notifications,
        Rich UI) that are not suitable for programmatic use.

        Args:
            **kwargs: Configuration options to override defaults.

        Returns:
            Config instance with script mode settings applied.

        Example:
            >>> config = Config.for_library(hw="vaapi", crf=20)
            >>> success, output, msg = convert_file(path, cfg=config)
        """
        # Set sensible defaults for library usage
        defaults: Dict[str, Any] = {
            "progress": False,
            "notify": False,
            "pipeline": False,
        }
        # User overrides take precedence
        defaults.update(kwargs)
        return cls(**defaults)


# Global config instance (set by parse_args in cli.py)
CFG = Config()


# -------------------- CONFIG FILE LOADING --------------------


def _parse_ini_value(value: str):
    """Parse INI value: bool, int, float, list (comma-sep), or string."""
    v = value.strip()
    if not v:
        return ""
    if v.lower() in ("true", "yes", "on"):
        return True
    if v.lower() in ("false", "no", "off"):
        return False
    # Try int
    try:
        return int(v)
    except ValueError:
        pass
    # Try float
    try:
        return float(v)
    except ValueError:
        pass
    # Check for comma-separated list
    if "," in v:
        return [x.strip() for x in v.split(",") if x.strip()]
    return v


def _load_ini_config(path: Path) -> Dict[str, Any]:
    """Load INI file and convert to nested dict."""
    cp = configparser.ConfigParser()
    cp.read(path)
    result: Dict[str, Any] = {}
    for section in cp.sections():
        result[section] = {}
        for key, value in cp.items(section):
            result[section][key] = _parse_ini_value(value)
    return result


def _load_single_config(config_dir: Path) -> Dict[str, Any]:
    """Load config from a single directory (TOML or INI file)."""
    toml_path = config_dir / "config.toml"
    ini_path = config_dir / "config.ini"

    if TOML_AVAILABLE and toml_path.exists():
        try:
            with toml_path.open("rb") as f:
                return dict(tomllib.load(f))
        except Exception as e:
            import sys

            print(f"Warning: Failed to load {toml_path}: {e}", file=sys.stderr)
            return {}
    elif ini_path.exists():
        try:
            return _load_ini_config(ini_path)
        except Exception as e:
            import sys

            print(f"Warning: Failed to load {ini_path}: {e}", file=sys.stderr)
            return {}
    return {}


def _deep_merge_dicts(base: dict, override: dict) -> dict:
    """Deep merge two dicts, with override taking precedence."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


def load_config_file(config_dir: Path) -> dict:
    """
    Load config with priority:
    1. User config: ~/.config/mkv2cast/config.toml (highest priority)
    2. System config: /etc/mkv2cast/config.toml (lowest priority, optional)

    User config values override system config values.
    """
    # System-wide config (optional, only if exists)
    system_config_dir = Path("/etc/mkv2cast")
    system_config = {}
    if system_config_dir.exists():
        system_config = _load_single_config(system_config_dir)

    # User config (takes precedence)
    user_config = _load_single_config(config_dir)

    # Merge: system as base, user overrides
    if system_config and user_config:
        return _deep_merge_dicts(system_config, user_config)
    elif user_config:
        return user_config
    elif system_config:
        return system_config
    return {}


def _get_default_config_toml() -> str:
    """Return default config as TOML string."""
    return """# mkv2cast configuration file
# This file is auto-generated on first run

[output]
suffix = ".cast"
container = "mkv"

[scan]
recursive = true
# Patterns to ignore (glob format, comma-separated in INI)
ignore_patterns = []
ignore_paths = []
# Patterns to include (only process matching files)
include_patterns = []
include_paths = []

[encoding]
backend = "auto"  # auto, vaapi, qsv, cpu
crf = 20
preset = "slow"
abr = "192k"

[workers]
# 0 = auto-detect based on system
encode = 0
integrity = 0

[integrity]
enabled = true
stable_wait = 3
deep_check = false

[notifications]
# Desktop notifications when processing completes
enabled = true
on_success = true
on_failure = true

[i18n]
# Language for messages (auto-detected from system if not set)
# Supported: en, fr, es, it, de
# lang = "fr"
"""


def _get_default_config_ini() -> str:
    """Return default config as INI string."""
    return """# mkv2cast configuration file
# This file is auto-generated on first run

[output]
suffix = .cast
container = mkv

[scan]
recursive = true
# Lists as comma-separated values
ignore_patterns =
ignore_paths =
include_patterns =
include_paths =

[encoding]
backend = auto
crf = 20
preset = slow
abr = 192k

[workers]
# 0 = auto-detect based on system
encode = 0
integrity = 0

[integrity]
enabled = true
stable_wait = 3
deep_check = false

[notifications]
# Desktop notifications when processing completes
enabled = true
on_success = true
on_failure = true

[i18n]
# Language for messages (auto-detected from system if not set)
# lang = fr
"""


def save_default_config(config_dir: Path) -> Path:
    """Create default config file (TOML if available, else INI). Returns path."""
    config_dir.mkdir(parents=True, exist_ok=True)

    if TOML_AVAILABLE:
        path = config_dir / "config.toml"
        if not path.exists():
            path.write_text(_get_default_config_toml())
        return path
    else:
        path = config_dir / "config.ini"
        if not path.exists():
            path.write_text(_get_default_config_ini())
        return path


def apply_config_to_args(file_config: dict, cfg: Config, cli_explicit: Optional[set] = None) -> None:
    """
    Apply file config values to Config instance.

    Only applies values from file config if they weren't explicitly set on CLI.
    This ensures CLI arguments have priority over config file values.

    Args:
        file_config: Dict from config file (TOML or INI)
        cfg: Config instance with CLI-parsed values
        cli_explicit: Optional set of attribute names explicitly set on CLI
    """
    # Get default values for comparison
    default_cfg = Config()

    # Map config file keys to Config attribute names
    mappings = {
        ("output", "suffix"): "suffix",
        ("output", "container"): "container",
        ("scan", "recursive"): "recursive",
        ("scan", "ignore_patterns"): "ignore_patterns",
        ("scan", "ignore_paths"): "ignore_paths",
        ("scan", "include_patterns"): "include_patterns",
        ("scan", "include_paths"): "include_paths",
        ("encoding", "backend"): "hw",
        ("encoding", "crf"): "crf",
        ("encoding", "preset"): "preset",
        ("encoding", "abr"): "abr",
        ("workers", "encode"): "encode_workers",
        ("workers", "integrity"): "integrity_workers",
        ("integrity", "enabled"): "integrity_check",
        ("integrity", "stable_wait"): "stable_wait",
        ("integrity", "deep_check"): "deep_check",
        ("notifications", "enabled"): "notify",
        ("notifications", "on_success"): "notify_on_success",
        ("notifications", "on_failure"): "notify_on_failure",
        ("i18n", "lang"): "lang",
    }

    for (section, key), attr_name in mappings.items():
        if section in file_config and key in file_config[section]:
            file_val = file_config[section][key]
            current_val = getattr(cfg, attr_name)
            default_val = getattr(default_cfg, attr_name)

            # Skip if CLI explicitly set this value (different from default)
            # This ensures CLI args have priority over config file
            if current_val != default_val:
                continue

            # For lists that might be empty
            if attr_name in ("ignore_patterns", "ignore_paths", "include_patterns", "include_paths"):
                if not current_val and file_val:
                    if isinstance(file_val, list):
                        setattr(cfg, attr_name, file_val)
                    elif isinstance(file_val, str) and file_val:
                        setattr(cfg, attr_name, [file_val])
            else:
                setattr(cfg, attr_name, file_val)
