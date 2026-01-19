"""
Command-line interface for mkv2cast.

This is the main entry point for the application.
"""

import argparse
import datetime
import fnmatch
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from mkv2cast import __author__, __license__, __url__, __version__
from mkv2cast.config import (
    TOML_AVAILABLE,
    Config,
    apply_config_to_args,
    get_app_dirs,
    load_config_file,
    save_default_config,
)
from mkv2cast.converter import (
    build_transcode_cmd,
    decide_for,
    have_encoder,
    pick_backend,
    probe_duration_ms,
)
from mkv2cast.history import SQLITE_AVAILABLE, HistoryDB
from mkv2cast.i18n import _, setup_i18n
from mkv2cast.integrity import integrity_check as do_integrity_check
from mkv2cast.notifications import (
    check_notification_support,
    notify_interrupted,
    notify_partial,
    notify_success,
)
from mkv2cast.ui import RICH_AVAILABLE
from mkv2cast.ui.legacy_ui import LegacyProgressUI, fmt_hms

# Conditionally import Rich UI and Pipeline
if RICH_AVAILABLE:
    from mkv2cast.pipeline import PipelineOrchestrator
    from mkv2cast.ui.rich_ui import RichProgressUI
    from mkv2cast.ui.simple_rich import SimpleRichUI

# -------------------- GLOBAL STATE --------------------

# Global app directories (initialized in main)
APP_DIRS: Dict[str, Path] = {}

# Global history database (initialized in main)
HISTORY_DB: Optional[HistoryDB] = None

# Track all running ffmpeg processes for proper cleanup
_active_processes: List[subprocess.Popen] = []
_processes_lock = threading.Lock()


def register_process(proc: subprocess.Popen) -> None:
    """Register a process for tracking."""
    with _processes_lock:
        _active_processes.append(proc)


def unregister_process(proc: subprocess.Popen) -> None:
    """Unregister a process from tracking."""
    with _processes_lock:
        if proc in _active_processes:
            _active_processes.remove(proc)


def terminate_all_processes() -> None:
    """Terminate all active processes and wait for cleanup."""
    with _processes_lock:
        procs = list(_active_processes)

    if not procs:
        return

    print(f"\n🛑 {_('Stopping')} {len(procs)} {_('processes')}...", file=sys.stderr, flush=True)

    for proc in procs:
        try:
            if proc.poll() is None:
                proc.terminate()
        except Exception:
            pass

    time.sleep(0.5)

    for proc in procs:
        try:
            if proc.poll() is None:
                proc.kill()
        except Exception:
            pass

    for proc in procs:
        try:
            proc.wait(timeout=5)
        except Exception:
            pass

    for proc in procs:
        try:
            if proc.stdout:
                proc.stdout.close()
            if proc.stderr:
                proc.stderr.close()
        except Exception:
            pass

    with _processes_lock:
        _active_processes.clear()

    print(f"✓ {_('All processes stopped')}", file=sys.stderr, flush=True)


# -------------------- ARGUMENT PARSING --------------------


def parse_args(args: Optional[List[str]] = None) -> Tuple[Config, Optional[Path]]:
    """Parse command-line arguments and return config + optional file path."""
    parser = argparse.ArgumentParser(
        description=_("Smart MKV -> Cast compatible converter with VAAPI/QSV hardware acceleration."),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Process all MKV files in current directory
  %(prog)s movie.mkv                # Process single file
  %(prog)s --debug --dryrun         # Debug mode, show commands without running
  %(prog)s --hw cpu --preset fast   # Use CPU encoding with fast preset
  %(prog)s --no-pipeline            # Disable parallel processing
  %(prog)s --encode-workers 3       # Use 3 parallel encodes
  %(prog)s -I '*sample*' -I '*.eng.*'  # Ignore sample files and English tracks
  %(prog)s -i '*French*' -i '*2024*'   # Only process French 2024 files
  %(prog)s --show-dirs                 # Show config/cache/log directories
  %(prog)s --history                   # Show recent conversion history
  %(prog)s --lang fr                   # Force French language
        """,
    )

    # Version
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}\nAuthor: {__author__}\nLicense: {__license__}\nURL: {__url__}",
    )

    # Positional argument
    parser.add_argument("file", nargs="?", help=_("Optional .mkv file to process"))

    # Output settings
    out_group = parser.add_argument_group(_("Output settings"))
    out_group.add_argument("--suffix", default=".cast", help=_("Output file suffix (default: .cast)"))
    out_group.add_argument("--container", choices=["mkv", "mp4"], default="mkv", help=_("Output container"))

    # Scan settings
    scan_group = parser.add_argument_group(_("Scan settings"))
    scan_group.add_argument("-r", "--recursive", action="store_true", default=True)
    scan_group.add_argument("--no-recursive", action="store_false", dest="recursive")
    scan_group.add_argument("--ignore-pattern", "-I", action="append", default=[], metavar="PATTERN")
    scan_group.add_argument("--ignore-path", action="append", default=[], metavar="PATH")
    scan_group.add_argument("--include-pattern", "-i", action="append", default=[], metavar="PATTERN")
    scan_group.add_argument("--include-path", action="append", default=[], metavar="PATH")

    # Watch mode
    watch_group = parser.add_argument_group(_("Watch mode"))
    watch_group.add_argument(
        "--watch",
        "-w",
        action="store_true",
        default=False,
        help=_("Watch directory for new MKV files and convert automatically"),
    )
    watch_group.add_argument(
        "--watch-interval",
        type=float,
        default=5.0,
        help=_("Polling interval in seconds for watch mode (default: 5)"),
    )

    # Debug/test
    debug_group = parser.add_argument_group(_("Debug/test"))
    debug_group.add_argument("-d", "--debug", action="store_true", help=_("Enable debug output"))
    debug_group.add_argument("-n", "--dryrun", action="store_true", help=_("Dry run"))

    # Codec decisions
    codec_group = parser.add_argument_group(_("Codec decisions"))
    codec_group.add_argument("--skip-when-ok", action="store_true", default=True)
    codec_group.add_argument("--no-skip-when-ok", action="store_false", dest="skip_when_ok")
    codec_group.add_argument("--force-h264", action="store_true")
    codec_group.add_argument("--allow-hevc", action="store_true")
    codec_group.add_argument("--force-aac", action="store_true")
    codec_group.add_argument("--keep-surround", action="store_true")
    codec_group.add_argument("--no-silence", action="store_false", dest="add_silence_if_no_audio")

    # Encoding quality
    quality_group = parser.add_argument_group(_("Encoding quality"))
    quality_group.add_argument("--abr", default="192k")
    quality_group.add_argument("--crf", type=int, default=20)
    quality_group.add_argument(
        "--preset",
        default="slow",
        choices=["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"],
    )

    # Hardware acceleration
    hw_group = parser.add_argument_group(_("Hardware acceleration"))
    hw_group.add_argument("--hw", choices=["auto", "nvenc", "qsv", "vaapi", "cpu"], default="auto")
    hw_group.add_argument("--vaapi-device", default="/dev/dri/renderD128")
    hw_group.add_argument("--vaapi-qp", type=int, default=23)
    hw_group.add_argument("--qsv-quality", type=int, default=23)
    hw_group.add_argument("--nvenc-cq", type=int, default=23, help=_("NVENC constant quality (0-51)"))

    # Audio track selection
    audio_group = parser.add_argument_group(_("Audio track selection"))
    audio_group.add_argument(
        "--audio-lang",
        type=str,
        default=None,
        help=_("Comma-separated language codes priority (e.g., fre,fra,fr,eng)"),
    )
    audio_group.add_argument("--audio-track", type=int, default=None, help=_("Explicit audio track index (0-based)"))

    # Subtitle selection
    subtitle_group = parser.add_argument_group(_("Subtitle selection"))
    subtitle_group.add_argument(
        "--subtitle-lang",
        type=str,
        default=None,
        help=_("Comma-separated subtitle language codes (e.g., fre,eng)"),
    )
    subtitle_group.add_argument(
        "--subtitle-track", type=int, default=None, help=_("Explicit subtitle track index (0-based)")
    )
    subtitle_group.add_argument(
        "--prefer-forced-subs",
        action="store_true",
        default=True,
        help=_("Prefer forced subtitles in audio language (default: True)"),
    )
    subtitle_group.add_argument(
        "--no-forced-subs",
        action="store_true",
        default=False,
        help=_("Don't prefer forced subtitles"),
    )
    subtitle_group.add_argument("--no-subtitles", action="store_true", default=False, help=_("Disable all subtitles"))

    # Integrity checks
    integrity_group = parser.add_argument_group(_("Integrity checks"))
    integrity_group.add_argument("--integrity-check", action="store_true", default=True)
    integrity_group.add_argument("--no-integrity-check", action="store_false", dest="integrity_check")
    integrity_group.add_argument("--stable-wait", type=int, default=3)
    integrity_group.add_argument("--deep-check", action="store_true")

    # UI settings
    ui_group = parser.add_argument_group(_("UI settings"))
    ui_group.add_argument("--no-progress", action="store_false", dest="progress")
    ui_group.add_argument("--bar-width", type=int, default=26)
    ui_group.add_argument("--ui-refresh-ms", type=int, default=120)
    ui_group.add_argument("--stats-period", type=float, default=0.2)

    # Pipeline mode
    pipeline_group = parser.add_argument_group(_("Pipeline mode"))
    pipeline_group.add_argument("--pipeline", action="store_true", default=True)
    pipeline_group.add_argument("--no-pipeline", action="store_false", dest="pipeline")

    # Parallelism
    parallel_group = parser.add_argument_group(_("Parallelism"))
    parallel_group.add_argument("--encode-workers", type=int, default=0, metavar="N")
    parallel_group.add_argument("--integrity-workers", type=int, default=0, metavar="N")

    # Notifications (new)
    notify_group = parser.add_argument_group(_("Notifications"))
    notify_group.add_argument(
        "--notify", action="store_true", default=True, help=_("Send desktop notification when done (default: enabled)")
    )
    notify_group.add_argument(
        "--no-notify", action="store_false", dest="notify", help=_("Disable desktop notifications")
    )

    # Internationalization (new)
    i18n_group = parser.add_argument_group(_("Internationalization"))
    i18n_group.add_argument(
        "--lang", choices=["en", "fr", "es", "it", "de"], default=None, help=_("Force language (default: auto-detect)")
    )

    # Utility commands
    util_group = parser.add_argument_group(_("Utility commands"))
    util_group.add_argument("--show-dirs", action="store_true")
    util_group.add_argument("--history", nargs="?", const=20, type=int, metavar="N")
    util_group.add_argument("--history-stats", action="store_true")
    util_group.add_argument("--clean-tmp", action="store_true")
    util_group.add_argument("--clean-logs", type=int, metavar="DAYS")
    util_group.add_argument("--clean-history", type=int, metavar="DAYS")
    util_group.add_argument("--check-requirements", action="store_true")

    parsed_args = parser.parse_args(args)

    # Setup i18n if language specified
    if parsed_args.lang:
        setup_i18n(parsed_args.lang)

    # Build config
    cfg = Config(
        suffix=parsed_args.suffix,
        container=parsed_args.container,
        recursive=parsed_args.recursive,
        ignore_patterns=parsed_args.ignore_pattern or [],
        ignore_paths=parsed_args.ignore_path or [],
        include_patterns=parsed_args.include_pattern or [],
        include_paths=parsed_args.include_path or [],
        debug=parsed_args.debug,
        dryrun=parsed_args.dryrun,
        skip_when_ok=parsed_args.skip_when_ok,
        force_h264=parsed_args.force_h264,
        allow_hevc=parsed_args.allow_hevc,
        force_aac=parsed_args.force_aac,
        keep_surround=parsed_args.keep_surround,
        add_silence_if_no_audio=parsed_args.add_silence_if_no_audio,
        abr=parsed_args.abr,
        crf=parsed_args.crf,
        preset=parsed_args.preset,
        hw=parsed_args.hw,
        vaapi_device=parsed_args.vaapi_device,
        vaapi_qp=parsed_args.vaapi_qp,
        qsv_quality=parsed_args.qsv_quality,
        nvenc_cq=parsed_args.nvenc_cq,
        audio_lang=parsed_args.audio_lang,
        audio_track=parsed_args.audio_track,
        subtitle_lang=parsed_args.subtitle_lang,
        subtitle_track=parsed_args.subtitle_track,
        prefer_forced_subs=not parsed_args.no_forced_subs,
        no_subtitles=parsed_args.no_subtitles,
        integrity_check=parsed_args.integrity_check,
        stable_wait=parsed_args.stable_wait,
        deep_check=parsed_args.deep_check,
        progress=parsed_args.progress,
        bar_width=parsed_args.bar_width,
        ui_refresh_ms=parsed_args.ui_refresh_ms,
        stats_period=parsed_args.stats_period,
        pipeline=parsed_args.pipeline,
        encode_workers=parsed_args.encode_workers,
        integrity_workers=parsed_args.integrity_workers,
        notify=parsed_args.notify,
        lang=parsed_args.lang,
    )

    single = Path(parsed_args.file).expanduser() if parsed_args.file else None
    return cfg, single


# -------------------- FILE FILTERING --------------------


def is_our_output_or_tmp(name: str, cfg: Config) -> bool:
    """Check if filename is our output or temp file."""
    if ".tmp." in name:
        return True
    if cfg.suffix in name:
        return True
    if ".h264." in name or ".aac." in name or ".remux." in name:
        return True
    return False


def _matches_pattern(filepath: Path, patterns: List[str]) -> bool:
    """Check if filepath matches any glob patterns."""
    if not patterns:
        return False
    name = filepath.name.lower()
    for pattern in patterns:
        pattern_lower = pattern.lower()
        if fnmatch.fnmatch(name, pattern_lower):
            return True
        if "*" not in pattern and "?" not in pattern:
            if fnmatch.fnmatch(name, f"*{pattern_lower}*"):
                return True
    return False


def _matches_path(filepath: Path, paths: List[str]) -> bool:
    """Check if filepath matches any paths."""
    if not paths:
        return False
    path_str = str(filepath)
    for check_path in paths:
        check_path_normalized = check_path.rstrip("/\\")
        if "/" not in check_path and "\\" not in check_path:
            if f"/{check_path_normalized}/" in path_str or f"\\{check_path_normalized}\\" in path_str:
                return True
            if path_str.endswith(f"/{check_path_normalized}") or path_str.endswith(f"\\{check_path_normalized}"):
                return True
        else:
            if check_path_normalized in path_str:
                return True
    return False


def should_process_file(filepath: Path, cfg: Config) -> Tuple[bool, Optional[str]]:
    """Check if file should be processed based on filters."""
    if cfg.include_patterns or cfg.include_paths:
        matches_include = _matches_pattern(filepath, cfg.include_patterns) or _matches_path(filepath, cfg.include_paths)
        if not matches_include:
            return False, "no include match"

    if _matches_pattern(filepath, cfg.ignore_patterns):
        return False, "matches ignore pattern"

    if _matches_path(filepath, cfg.ignore_paths):
        return False, "in ignored path"

    return True, None


def output_exists_for_input(inp: Path, cfg: Config) -> bool:
    """Check if output already exists for input file."""
    d = inp.parent
    stem = inp.stem
    ext = cfg.container
    patterns = [f"{stem}*{cfg.suffix}.{ext}"]
    for pat in patterns:
        for p in d.glob(pat):
            if p.is_file() and ".tmp." not in p.name:
                return True
    for p in d.glob(f"{stem}*.tmp.*.{ext}"):
        if p.is_file():
            return True
    return False


def collect_targets(root: Path, single: Optional[Path], cfg: Config) -> Tuple[List[Path], List[Tuple[Path, str]]]:
    """Collect target files for processing."""
    targets: List[Path] = []
    ignored: List[Tuple[Path, str]] = []

    if single is not None:
        p = single.resolve()
        if not p.exists() or not p.is_file():
            raise RuntimeError(f"{_('File not found')}: {p}")
        if p.suffix.lower() != ".mkv":
            raise RuntimeError(_("Only .mkv files supported"))
        if p.name.startswith(".") or is_our_output_or_tmp(p.name, cfg):
            return [], []
        should, reason = should_process_file(p, cfg)
        if not should:
            ignored.append((p, reason or "filtered"))
            return [], ignored
        targets.append(p)
        return targets, ignored

    if cfg.recursive:
        for dirpath, dirnames, filenames in os.walk(root):
            d = Path(dirpath)
            new_dirnames = []
            for dn in dirnames:
                if dn.startswith("."):
                    continue
                dir_path = d / dn
                should, _reason = should_process_file(dir_path, cfg)
                if not should:
                    continue
                new_dirnames.append(dn)
            dirnames[:] = new_dirnames

            for fn in filenames:
                if not fn.lower().endswith(".mkv"):
                    continue
                if fn.startswith("."):
                    continue
                if is_our_output_or_tmp(fn, cfg):
                    continue
                p = d / fn
                should, reason = should_process_file(p, cfg)
                if not should:
                    ignored.append((p, reason or "filtered"))
                    continue
                targets.append(p)
    else:
        for p in root.glob("*.mkv"):
            if not p.is_file():
                continue
            if is_our_output_or_tmp(p.name, cfg):
                continue
            should, reason = should_process_file(p, cfg)
            if not should:
                ignored.append((p, reason or "filtered"))
                continue
            targets.append(p)

    targets.sort()
    return targets, ignored


# -------------------- SYSTEM DETECTION --------------------


def is_running_as_root() -> bool:
    """Check if script is running as root."""
    return os.geteuid() == 0


def get_total_ram_gb() -> int:
    """Get total RAM in GB."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        kb = int(parts[1])
                        return kb // (1024 * 1024)
    except Exception:
        pass
    return 8


def get_gpu_info() -> Tuple[str, int]:
    """
    Detect GPU type and VRAM.
    Returns: (gpu_type, vram_mb)
    gpu_type: "nvidia", "amd", "intel", "unknown"
    """
    import glob

    gpu_type = "unknown"
    vram_mb = 0

    # Try to detect NVIDIA GPU
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            vram_mb = int(result.stdout.strip().split("\n")[0])
            gpu_type = "nvidia"
            return gpu_type, vram_mb
    except Exception:
        pass

    # Try to detect AMD GPU via VRAM info
    try:
        result = subprocess.run(["lspci"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and "AMD" in result.stdout and "VGA" in result.stdout:
            gpu_type = "amd"
            for path in glob.glob("/sys/class/drm/card*/device/mem_info_vram_total"):
                try:
                    with open(path) as f:
                        vram_mb = int(f.read().strip()) // (1024 * 1024)
                        break
                except Exception:
                    pass
            return gpu_type, vram_mb
    except Exception:
        pass

    # Try to detect Intel GPU
    try:
        result = subprocess.run(["lspci"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and "Intel" in result.stdout and "VGA" in result.stdout:
            gpu_type = "intel"
            vram_mb = 2048  # Intel iGPU uses system RAM, estimate ~2GB
            return gpu_type, vram_mb
    except Exception:
        pass

    return gpu_type, vram_mb


def auto_detect_workers(backend: str) -> Tuple[int, int]:
    """
    Auto-detect optimal worker counts based on backend and system resources.
    Returns: (encode_workers, integrity_workers)
    """
    ram_gb = get_total_ram_gb()
    cores = os.cpu_count() or 4

    if backend in ("vaapi", "qsv"):
        gpu_type, vram_mb = get_gpu_info()

        # Base encode workers on VRAM (if detected) or RAM as fallback
        if vram_mb >= 8192:  # 8GB+ VRAM (high-end desktop GPU)
            encode = 3
        elif vram_mb >= 4096:  # 4GB+ VRAM (mid-range GPU)
            encode = 2
        elif ram_gb >= 32:
            encode = 2
        else:
            encode = 1
        integrity = encode + 1
    else:
        if cores >= 16 and ram_gb >= 32:
            encode = 2
        else:
            encode = 1
        integrity = 2 if cores >= 8 else 1

    return encode, integrity


# -------------------- MULTI-USER CLEANUP (ROOT) --------------------


def get_all_users_mkv2cast_dirs() -> List[Dict[str, Any]]:
    """
    Get mkv2cast directories for all users on the system.
    Only returns users that have mkv2cast data directories.
    """
    users: List[Dict[str, Any]] = []
    home_base = Path("/home")

    if not home_base.exists():
        return users

    try:
        for entry in home_base.iterdir():
            if not entry.is_dir():
                continue

            cache_dir = entry / ".cache" / "mkv2cast"
            state_dir = entry / ".local" / "state" / "mkv2cast"
            config_dir = entry / ".config" / "mkv2cast"

            if cache_dir.exists() or state_dir.exists():
                users.append(
                    {
                        "user": entry.name,
                        "home": entry,
                        "cache": cache_dir,
                        "tmp": cache_dir / "tmp",
                        "state": state_dir,
                        "logs": state_dir / "logs",
                        "config": config_dir,
                    }
                )
    except PermissionError:
        pass

    return users


def cleanup_all_users_logs(days: int, verbose: bool = True) -> Dict[str, int]:
    """
    Clean logs for all users (requires root).
    Returns dict of {username: removed_count}.
    """
    results: Dict[str, int] = {}
    users = get_all_users_mkv2cast_dirs()

    for user_info in users:
        username = str(user_info["user"])
        logs_dir: Path = user_info["logs"]

        if not logs_dir.exists():
            continue

        cutoff = time.time() - (days * 86400)
        removed = 0

        try:
            for f in logs_dir.glob("*.log"):
                try:
                    if f.stat().st_mtime < cutoff:
                        f.unlink()
                        removed += 1
                except Exception:
                    pass

            if removed > 0 or verbose:
                results[username] = removed
        except PermissionError:
            if verbose:
                print(f"  Warning: Cannot access logs for user {username}", file=sys.stderr)

    return results


def cleanup_all_users_tmp(max_age_hours: int = 0, verbose: bool = True) -> Dict[str, int]:
    """
    Clean tmp files for all users (requires root).
    max_age_hours=0 means clean all tmp files.
    Returns dict of {username: removed_count}.
    """
    results: Dict[str, int] = {}
    users = get_all_users_mkv2cast_dirs()

    for user_info in users:
        username = str(user_info["user"])
        tmp_dir: Path = user_info["tmp"]

        if not tmp_dir.exists():
            continue

        if max_age_hours > 0:
            cutoff = time.time() - (max_age_hours * 3600)
        else:
            cutoff = time.time()

        removed = 0

        try:
            for pattern in ["*.tmp.*.mkv", "*.tmp.*.mp4"]:
                for f in tmp_dir.glob(pattern):
                    try:
                        if max_age_hours == 0 or f.stat().st_mtime < cutoff:
                            f.unlink()
                            removed += 1
                    except Exception:
                        pass

            if removed > 0 or verbose:
                results[username] = removed
        except PermissionError:
            if verbose:
                print(f"  Warning: Cannot access tmp for user {username}", file=sys.stderr)

    return results


# -------------------- LOGGING --------------------


def get_log_path(inp: Path) -> Path:
    """Generate log path for input file."""
    logs_dir = APP_DIRS.get("logs", Path.home() / ".local" / "state" / "mkv2cast" / "logs")
    logs_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.date.today().isoformat()
    safe_name = re.sub(r"[^\w\-.]", "_", inp.stem)[:80]
    return logs_dir / f"{date_str}_{safe_name}.log"


def get_tmp_path(inp: Path, worker_id: int, tag: str, cfg: Config) -> Path:
    """Generate temp path for encoding."""
    tmp_dir = APP_DIRS.get("tmp", Path.home() / ".cache" / "mkv2cast" / "tmp")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    stem = inp.stem
    ext = cfg.container
    suffix = cfg.suffix
    pid = os.getpid()

    return tmp_dir / f"{stem}{tag}{suffix}.tmp.{pid}.{worker_id}.{ext}"


# -------------------- UTILITY COMMANDS --------------------


def check_requirements() -> int:
    """Check system requirements."""
    print(f"mkv2cast v{__version__} - {_('Requirements Check')}")
    print("=" * 50)
    print()

    all_ok = True

    print(f"{_('System requirements')} ({_('mandatory')}):")
    print("-" * 40)

    # Check ffmpeg
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            version_line = result.stdout.split("\n")[0] if result.stdout else "unknown"
            print(f"  ✓ ffmpeg: {version_line}")
        else:
            print("  ✗ ffmpeg: installed but returned error")
            all_ok = False
    except FileNotFoundError:
        print("  ✗ ffmpeg: NOT FOUND")
        all_ok = False
    except Exception as e:
        print(f"  ✗ ffmpeg: error - {e}")
        all_ok = False

    # Check ffprobe
    try:
        result = subprocess.run(["ffprobe", "-version"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print("  ✓ ffprobe: found")
        else:
            print("  ✗ ffprobe: error")
            all_ok = False
    except FileNotFoundError:
        print("  ✗ ffprobe: NOT FOUND")
        all_ok = False
    except Exception:
        all_ok = False

    # Python version
    py_version = sys.version_info
    if py_version >= (3, 8):
        print(f"  ✓ Python: {py_version.major}.{py_version.minor}.{py_version.micro}")
    else:
        print(f"  ✗ Python: {py_version.major}.{py_version.minor} (need 3.8+)")
        all_ok = False

    print()
    print(f"{_('Optional dependencies')}:")
    print("-" * 40)

    print(f"  {'✓' if RICH_AVAILABLE else '○'} rich: {'installed' if RICH_AVAILABLE else 'NOT INSTALLED'}")
    print(f"  {'✓' if TOML_AVAILABLE else '○'} TOML support: {'available' if TOML_AVAILABLE else 'not available'}")
    print(f"  {'✓' if SQLITE_AVAILABLE else '○'} SQLite: {'available' if SQLITE_AVAILABLE else 'not available'}")

    notif = check_notification_support()
    print(f"  {'✓' if notif['any'] else '○'} Notifications: {'available' if notif['any'] else 'not available'}")

    print()
    print(f"{_('Hardware acceleration')}:")
    print("-" * 40)

    vaapi_device = Path("/dev/dri/renderD128")
    if vaapi_device.exists():
        print(f"  ✓ VAAPI device: {vaapi_device}")
        if have_encoder("h264_vaapi"):
            print("  ✓ h264_vaapi encoder: available")
        else:
            print("  ○ h264_vaapi encoder: not available")
    else:
        print("  ○ VAAPI device: not found")

    if have_encoder("h264_qsv"):
        print("  ✓ h264_qsv encoder: available")
    else:
        print("  ○ h264_qsv encoder: not available")

    print()
    if all_ok:
        print(f"✓ {_('All requirements satisfied')}")
        return 0
    else:
        print(f"✗ {_('Some requirements missing')}")
        return 1


def handle_utility_commands(cfg: Config, args: argparse.Namespace) -> Optional[int]:
    """Handle utility commands that exit immediately."""
    global APP_DIRS, HISTORY_DB

    if args.check_requirements:
        return check_requirements()

    APP_DIRS = get_app_dirs()

    if args.show_dirs:
        print(f"mkv2cast {_('directories')}:")
        print()
        print(f"{_('User directories')} (XDG):")
        print(f"  Config:  {APP_DIRS['config']}")
        print(f"  State:   {APP_DIRS['state']}")
        print(f"  Logs:    {APP_DIRS['logs']}")
        print(f"  Cache:   {APP_DIRS['cache']}")
        print(f"  Tmp:     {APP_DIRS['tmp']}")
        return 0

    if args.clean_tmp:
        if is_running_as_root():
            print(_("Running as root - cleaning tmp for all users..."))
            results = cleanup_all_users_tmp(max_age_hours=0, verbose=True)
            total = sum(results.values())
            for user, count in results.items():
                if count > 0:
                    print(f"  {user}: {count} {_('files removed')}")
            print(f"{_('Total removed')}: {total} {_('temp files')}")
        else:
            tmp_dir = APP_DIRS.get("tmp")
            if tmp_dir and tmp_dir.exists():
                removed = 0
                for pattern in ["*.tmp.*.mkv", "*.tmp.*.mp4"]:
                    for f in tmp_dir.glob(pattern):
                        try:
                            f.unlink()
                            removed += 1
                        except Exception:
                            pass
                print(f"{_('Removed')} {removed} {_('temp files')}")
        return 0

    if args.clean_logs is not None:
        if is_running_as_root():
            print(_("Running as root - cleaning logs for all users..."))
            results = cleanup_all_users_logs(args.clean_logs, verbose=True)
            total = sum(results.values())
            for user, count in results.items():
                if count > 0:
                    print(f"  {user}: {count} {_('files removed')}")
            print(f"{_('Total removed')}: {total} {_('log files older than')} {args.clean_logs} {_('days')}")
        else:
            logs_dir = APP_DIRS.get("logs")
            if logs_dir and logs_dir.exists():
                cutoff = time.time() - (args.clean_logs * 86400)
                removed = 0
                for f in logs_dir.glob("*.log"):
                    try:
                        if f.stat().st_mtime < cutoff:
                            f.unlink()
                            removed += 1
                    except Exception:
                        pass
                print(f"{_('Removed')} {removed} {_('log files older than')} {args.clean_logs} {_('days')}")
        return 0

    HISTORY_DB = HistoryDB(APP_DIRS["state"])

    if args.clean_history is not None:
        removed = HISTORY_DB.clean_old(args.clean_history)
        print(f"{_('Removed')} {removed} {_('history entries')}")
        return 0

    if args.history is not None:
        limit = min(max(1, args.history), 1000)
        recent = HISTORY_DB.get_recent(limit)

        if not recent:
            print(_("No conversion history found."))
            return 0

        term_cols = shutil.get_terminal_size((80, 20)).columns
        print(f"{_('Recent conversions')} ({_('last')} {len(recent)}):")
        print("-" * min(80, term_cols - 1))

        for entry in recent:
            inp = entry.get("input_path") or entry.get("input", "?")
            inp_name = Path(inp).name if inp else "?"
            status = entry.get("status", "?")
            started = entry.get("started_at") or entry.get("started", "?")
            if started and len(started) > 19:
                started = started[:19]

            status_icon = {"done": "✓", "failed": "✗", "skipped": "⊘", "running": "⚙"}.get(status, "?")

            max_name_len = max(20, term_cols - 45)
            if len(inp_name) > max_name_len:
                inp_name = inp_name[: max_name_len - 3] + "..."

            print(f"  {status_icon} [{started}] {status:8} {inp_name}")
        return 0

    if args.history_stats:
        stats = HISTORY_DB.get_stats()
        by_status = stats.get("by_status", {})

        print(f"{_('Conversion statistics')}:")
        print("-" * 40)
        total = sum(by_status.values())
        print(f"  {_('Total conversions')}:  {total}")
        for status, count in sorted(by_status.items()):
            pct = (count / total * 100) if total > 0 else 0
            print(f"    {status:12} {count:5} ({pct:.1f}%)")

        avg_time = stats.get("avg_encode_time", 0)
        total_time = stats.get("total_encode_time", 0)
        print(f"  {_('Average encode time')}: {avg_time:.1f}s")
        print(f"  {_('Total encode time')}:   {total_time:.1f}s ({total_time / 3600:.1f}h)")
        return 0

    return None


# -------------------- MAIN --------------------


def main_legacy(single: Optional[Path], cfg: Config) -> Tuple[int, int, int, int, bool]:
    """Legacy sequential mode. Returns (ok, skipped, failed, interrupted, was_interrupted)."""
    from mkv2cast.config import CFG as global_cfg

    global_cfg.__dict__.update(cfg.__dict__)

    root = Path(".").resolve()
    backend = pick_backend(cfg)
    print(f"{_('Backend selected')}: {backend}", flush=True)

    ui = LegacyProgressUI(cfg.progress, cfg.bar_width)
    targets, ignored_files = collect_targets(root, single, cfg)

    if not targets:
        print(_("No MKV files to process."), flush=True)
        return 0, 0, 0, 0, False

    len(targets)
    ok = 0
    skipped = 0
    failed = 0
    interrupted = False

    for _i, inp in enumerate(targets, start=1):
        if output_exists_for_input(inp, cfg):
            skipped += 1
            continue

        log_path = get_log_path(inp)
        ui.log(f"==> {inp}")

        # Integrity check
        success, _elapsed = do_integrity_check(
            inp, enabled=cfg.integrity_check, stable_wait=cfg.stable_wait, deep_check=cfg.deep_check, log_path=log_path
        )
        if not success:
            skipped += 1
            ui.log(f"   SKIP: {_('integrity check failed')}")
            continue

        try:
            d = decide_for(inp, cfg)
        except Exception as e:
            failed += 1
            ui.log(f"   FAILED: {e}")
            continue

        if (not d.need_v) and (not d.need_a) and cfg.skip_when_ok:
            skipped += 1
            ui.log(f"   OK: {_('compatible')}")
            continue

        tag = ""
        if d.need_v:
            tag += ".h264"
        if d.need_a:
            tag += ".aac"
        if not tag:
            tag = ".remux"

        final = inp.parent / f"{inp.stem}{tag}{cfg.suffix}.{cfg.container}"
        if final.exists():
            skipped += 1
            continue

        tmp = get_tmp_path(inp, 0, tag, cfg)
        ui.log(f"   -> {final}")

        cmd, stage = build_transcode_cmd(inp, d, backend, tmp, log_path, cfg)

        if cfg.dryrun:
            ui.log(f"DRYRUN: {' '.join(cmd)}")
            skipped += 1
            continue

        probe_duration_ms(inp)

        try:
            result = subprocess.run(cmd, capture_output=True, timeout=86400)
            rc = result.returncode
        except KeyboardInterrupt:
            interrupted = True
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            break
        except Exception as e:
            failed += 1
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            ui.log(f"   FAILED: {e}")
            continue

        if rc == 0:
            try:
                shutil.move(str(tmp), str(final))
                ok += 1
                ui.log("   DONE")
            except Exception as e:
                failed += 1
                if tmp.exists():
                    tmp.unlink(missing_ok=True)
                ui.log(f"   FAILED: {e}")
        else:
            failed += 1
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            ui.log(f"   FAILED (rc={rc})")

    return ok, skipped, failed, 1 if interrupted else 0, interrupted


def main_rich(single: Optional[Path], cfg: Config) -> Tuple[int, int, int, int, bool]:
    """Rich UI sequential mode. Returns (ok, skipped, failed, interrupted, was_interrupted)."""
    from mkv2cast.config import CFG as global_cfg

    global_cfg.__dict__.update(cfg.__dict__)

    start_time = time.time()
    ui = SimpleRichUI(cfg.progress)
    root = Path(".").resolve()
    backend = pick_backend(cfg)

    ui.console.print(f"[bold]mkv2cast[/bold] v{__version__}")
    ui.console.print(f"[dim]{_('Backend')}:[/dim] [cyan]{backend}[/cyan]")
    ui.console.print()

    targets, ignored_files = collect_targets(root, single, cfg)

    if not targets:
        ui.console.print(f"[yellow]{_('No MKV files to process.')}[/yellow]")
        return 0, 0, 0, 0, False

    total_files = len(targets)
    ui.console.print(f"[dim]{_('Found')} {total_files} {_('file(s) to process')}[/dim]")

    ok = 0
    skipped = 0
    failed = 0
    interrupted = False

    for idx, inp in enumerate(targets, start=1):
        if output_exists_for_input(inp, cfg):
            skipped += 1
            continue

        log_path = get_log_path(inp)

        # Integrity check
        success, _elapsed = do_integrity_check(
            inp, enabled=cfg.integrity_check, stable_wait=cfg.stable_wait, deep_check=cfg.deep_check, log_path=log_path
        )
        if not success:
            ui.log_file_start(inp, inp)
            ui.log_skip(_("integrity check failed"))
            continue

        try:
            d = decide_for(inp, cfg)
        except Exception as e:
            ui.log_file_start(inp, inp)
            ui.log_error(str(e))
            continue

        if (not d.need_v) and (not d.need_a) and cfg.skip_when_ok:
            ui.log_file_start(inp, inp)
            ui.log_compatible()
            continue

        tag = ""
        if d.need_v:
            tag += ".h264"
        if d.need_a:
            tag += ".aac"
        if not tag:
            tag = ".remux"

        final = inp.parent / f"{inp.stem}{tag}{cfg.suffix}.{cfg.container}"
        if final.exists():
            skipped += 1
            continue

        tmp = get_tmp_path(inp, 0, tag, cfg)
        ui.log_file_start(inp, final)

        cmd, stage = build_transcode_cmd(inp, d, backend, tmp, log_path, cfg)

        if cfg.dryrun:
            ui.console.print(f"  [dim]DRYRUN: {' '.join(cmd)}[/dim]")
            skipped += 1
            continue

        dur_ms = probe_duration_ms(inp)
        start_encode = time.time()

        try:
            rc, stderr = ui.run_ffmpeg_with_progress(cmd, stage, dur_ms, idx, total_files)
        except KeyboardInterrupt:
            interrupted = True
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            break
        except Exception as e:
            ui.log_error(str(e))
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            continue

        encode_time = time.time() - start_encode

        if rc == 0:
            try:
                shutil.move(str(tmp), str(final))
                output_size = final.stat().st_size if final.exists() else 0
                ui.log_success(encode_time, output_size)
            except Exception as e:
                ui.log_error(str(e))
                if tmp.exists():
                    tmp.unlink(missing_ok=True)
        else:
            ui.log_error(f"ffmpeg exit code {rc}")
            if tmp.exists():
                tmp.unlink(missing_ok=True)

    ok, skipped, failed, _processed = ui.get_stats()

    # Print summary
    ui.print_summary(time.time() - start_time)

    return ok, skipped, failed, 1 if interrupted else 0, interrupted


def main_pipeline(single: Optional[Path], cfg: Config) -> Tuple[int, int, int, int, bool]:
    """Pipeline mode with parallel workers. Returns (ok, skipped, failed, interrupted_count, was_interrupted)."""
    from mkv2cast.config import CFG as global_cfg

    global_cfg.__dict__.update(cfg.__dict__)

    root = Path(".").resolve()
    backend = pick_backend(cfg)

    # Collect targets
    targets, ignored_files = collect_targets(root, single, cfg)

    if not targets:
        print(_("No MKV files to process."), flush=True)
        return 0, 0, 0, 0, False

    # Determine worker counts
    if cfg.encode_workers == 0 or cfg.integrity_workers == 0:
        auto_encode, auto_integrity = auto_detect_workers(backend)
        encode_workers = cfg.encode_workers if cfg.encode_workers > 0 else auto_encode
        integrity_workers = cfg.integrity_workers if cfg.integrity_workers > 0 else auto_integrity
    else:
        encode_workers = cfg.encode_workers
        integrity_workers = cfg.integrity_workers

    # Create Rich UI
    ui = RichProgressUI(total_files=len(targets), encode_workers=encode_workers, integrity_workers=integrity_workers)

    # Header
    ui.console.print(f"[bold]mkv2cast[/bold] v{__version__}")
    ui.console.print(f"[dim]{_('Backend')}:[/dim] [cyan]{backend}[/cyan]")
    ui.console.print(f"[dim]{_('Workers')}:[/dim] {encode_workers} {_('encode')}, {integrity_workers} {_('integrity')}")
    ui.console.print(f"[dim]{_('Files')}:[/dim] {len(targets)} {_('to process')}")
    ui.console.print()

    # Create and run pipeline
    pipeline = PipelineOrchestrator(
        targets=targets,
        backend=backend,
        ui=ui,
        cfg=cfg,
        encode_workers=encode_workers,
        integrity_workers=integrity_workers,
        get_log_path=get_log_path,
        get_tmp_path=lambda inp, wid, tag: get_tmp_path(inp, wid, tag, cfg),
        output_exists_fn=output_exists_for_input,
    )

    ok, skipped, failed, interrupted = pipeline.run()

    # Print final summary
    ui.console.print()
    ui.console.print(f"[bold]═══ {_('Summary')} ═══[/bold]")
    ui.console.print(f"  [green]✓ {_('Converted')}:[/green] {ok}")
    ui.console.print(f"  [yellow]⊘ {_('Skipped')}:[/yellow] {skipped}")
    ui.console.print(f"  [red]✗ {_('Failed')}:[/red] {failed}")

    return ok, skipped, failed, 1 if interrupted else 0, interrupted


def run_watch_mode(single: Optional[Path], cfg: Config, interval: float) -> int:
    """Run in watch mode, monitoring directory for new MKV files."""
    from mkv2cast.watcher import watch_directory

    # Determine watch path
    if single and single.is_dir():
        watch_path = single
    elif single and single.is_file():
        watch_path = single.parent
    else:
        watch_path = Path.cwd()

    print(f"mkv2cast v{__version__} - {_('Watch Mode')}")
    print()

    def convert_single(filepath: Path) -> None:
        """Convert a single file when detected."""
        from mkv2cast.converter import convert_file, pick_backend

        backend = pick_backend(cfg)
        print(f"[{_('NEW')}] {filepath.name}")

        success, output_path, message = convert_file(
            input_path=filepath,
            cfg=cfg,
            backend=backend,
        )

        if success:
            if output_path:
                print(f"  [✓] {_('Converted')}: {output_path.name}")
            else:
                print(f"  [⊘] {_('Skipped')}: {message}")
        else:
            print(f"  [✗] {_('Failed')}: {message}")

    try:
        watch_directory(
            path=watch_path,
            convert_callback=convert_single,
            cfg=cfg,
            interval=interval,
        )
    except KeyboardInterrupt:
        print(f"\n{_('Interrupted')}")

    return 0


def main() -> int:
    """Main entry point."""
    global APP_DIRS, HISTORY_DB

    # Initialize i18n
    setup_i18n()

    # Parse arguments
    cfg, single = parse_args()

    # Update global config
    from mkv2cast.config import CFG as global_cfg

    global_cfg.__dict__.update(cfg.__dict__)

    # Initialize directories
    APP_DIRS = get_app_dirs()

    # Create default config if needed
    save_default_config(APP_DIRS["config"])

    # Load config file
    file_config = load_config_file(APP_DIRS["config"])
    if file_config:
        apply_config_to_args(file_config, cfg)

    # Initialize history database
    HISTORY_DB = HistoryDB(APP_DIRS["state"])

    # Handle utility commands
    _parser = argparse.ArgumentParser(add_help=False)
    _parser.add_argument("--show-dirs", action="store_true")
    _parser.add_argument("--history", nargs="?", const=20, type=int)
    _parser.add_argument("--history-stats", action="store_true")
    _parser.add_argument("--clean-tmp", action="store_true")
    _parser.add_argument("--clean-logs", type=int)
    _parser.add_argument("--clean-history", type=int)
    _parser.add_argument("--check-requirements", action="store_true")
    _util_args, _remaining = _parser.parse_known_args()

    result = handle_utility_commands(cfg, _util_args)
    if result is not None:
        return result

    # Handle watch mode
    _watch_parser = argparse.ArgumentParser(add_help=False)
    _watch_parser.add_argument("--watch", "-w", action="store_true")
    _watch_parser.add_argument("--watch-interval", type=float, default=5.0)
    _watch_args, _ = _watch_parser.parse_known_args()

    if _watch_args.watch:
        return run_watch_mode(single, cfg, _watch_args.watch_interval)

    # Run main processing
    start_time = time.time()

    # Choose UI mode:
    # - Pipeline mode with Rich UI if Rich available and --pipeline enabled
    # - Simple Rich mode if Rich available but --no-pipeline
    # - Legacy mode if Rich not available
    use_pipeline = RICH_AVAILABLE and cfg.pipeline and cfg.progress
    use_simple_rich = RICH_AVAILABLE and not cfg.pipeline and cfg.progress

    if use_pipeline:
        ok, skipped, failed, interrupted_count, was_interrupted = main_pipeline(single, cfg)
        total_time = fmt_hms(time.time() - start_time)
        # Summary is printed by main_pipeline
    elif use_simple_rich:
        ok, skipped, failed, interrupted_count, was_interrupted = main_rich(single, cfg)
        total_time = fmt_hms(time.time() - start_time)
        # Summary is printed by main_rich
    else:
        ok, skipped, failed, interrupted_count, was_interrupted = main_legacy(single, cfg)
        total_time = fmt_hms(time.time() - start_time)

        # Print summary (legacy mode)
        print()
        trans_summary = _("Summary")  # type: ignore[operator]
        trans_ok = _("Transcoded OK")  # type: ignore[operator]
        trans_skipped = _("Skipped")  # type: ignore[operator]
        trans_failed = _("Failed")  # type: ignore[operator]
        trans_time = _("Total time")  # type: ignore[operator]
        print(f"=== {trans_summary} ===")
        print(f"{trans_ok}: {ok}")
        print(f"{trans_skipped}: {skipped}")
        print(f"{trans_failed}: {failed}")
        print(f"{trans_time}: {total_time}")

    # Send notification if enabled
    if cfg.notify:
        if was_interrupted:
            notify_interrupted()
        elif failed == 0 and ok > 0:
            if cfg.notify_on_success:
                notify_success(ok, total_time)
        elif failed > 0:
            if cfg.notify_on_failure:
                notify_partial(ok, failed, skipped, total_time)
        elif ok > 0 or skipped > 0:
            if cfg.notify_on_success:
                notify_partial(ok, failed, skipped, total_time)

    if was_interrupted:
        return 130
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
