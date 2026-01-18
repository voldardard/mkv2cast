#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mkv2cast - Smart MKV to Chromecast-compatible converter with hardware acceleration.

This tool converts MKV video files to formats compatible with Chromecast devices
and smart TVs, using VAAPI, QSV, or CPU encoding with intelligent codec detection.

Copyright (C) 2024-2026 voldardard
License: GPL-3.0 (https://www.gnu.org/licenses/gpl-3.0.html)
"""

import argparse
import configparser
import datetime
import fnmatch
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
import threading
from dataclasses import dataclass
from pathlib import Path
from queue import Queue, Empty
from typing import Optional, Tuple, List, Dict

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

# SQLite support (usually available, but check anyway)
try:
    import sqlite3
    SQLITE_AVAILABLE = True
except ImportError:
    SQLITE_AVAILABLE = False

# Try to import rich, fallback to basic mode if not available
try:
    from rich.console import Console, Group
    from rich.table import Table
    from rich.live import Live
    from rich.text import Text
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


# -------------------- VERSION & METADATA --------------------
__version__ = "1.0.0"
__author__ = "voldardard"
__license__ = "GPL-3.0"
__copyright__ = "Copyright (C) 2024-2026 voldardard"
__url__ = "https://github.com/voldardard/mkv2cast"
__description__ = "Smart MKV to Chromecast-compatible converter with hardware acceleration"


# -------------------- GLOBAL PROCESS REGISTRY --------------------
# Track all running ffmpeg processes for proper cleanup on Ctrl+C
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
    
    print(f"\n🛑 Arrêt de {len(procs)} processus en cours...", file=sys.stderr, flush=True)
    
    # First, send SIGTERM to all
    for proc in procs:
        try:
            if proc.poll() is None:
                proc.terminate()
        except Exception:
            pass
    
    # Wait a bit for graceful shutdown
    time.sleep(0.5)
    
    # Kill any remaining processes
    for proc in procs:
        try:
            if proc.poll() is None:
                proc.kill()
        except Exception:
            pass
    
    # Wait for all to finish
    for proc in procs:
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
    
    # Close all file handles
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
    
    print("✓ Tous les processus arrêtés", file=sys.stderr, flush=True)


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


# Global app directories (initialized in main)
APP_DIRS: Dict[str, Path] = {}


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


def _load_ini_config(path: Path) -> dict:
    """Load INI file and convert to nested dict."""
    cp = configparser.ConfigParser()
    cp.read(path)
    result = {}
    for section in cp.sections():
        result[section] = {}
        for key, value in cp.items(section):
            result[section][key] = _parse_ini_value(value)
    return result


def _load_single_config(config_dir: Path) -> dict:
    """Load config from a single directory (TOML or INI file)."""
    toml_path = config_dir / "config.toml"
    ini_path = config_dir / "config.ini"
    
    if TOML_AVAILABLE and toml_path.exists():
        try:
            with toml_path.open("rb") as f:
                return tomllib.load(f)
        except Exception as e:
            print(f"Warning: Failed to load {toml_path}: {e}", file=sys.stderr)
            return {}
    elif ini_path.exists():
        try:
            return _load_ini_config(ini_path)
        except Exception as e:
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
    return '''# mkv2cast configuration file
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
'''


def _get_default_config_ini() -> str:
    """Return default config as INI string."""
    return '''# mkv2cast configuration file
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
'''


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


def apply_config_to_args(file_config: dict, args: argparse.Namespace) -> None:
    """Apply file config values to args (args take precedence if explicitly set)."""
    # Map config file keys to arg names
    mappings = {
        ("output", "suffix"): "suffix",
        ("output", "container"): "container",
        ("scan", "recursive"): "recursive",
        ("scan", "ignore_patterns"): "ignore_pattern",
        ("scan", "ignore_paths"): "ignore_path",
        ("scan", "include_patterns"): "include_pattern",
        ("scan", "include_paths"): "include_path",
        ("encoding", "backend"): "hw",
        ("encoding", "crf"): "crf",
        ("encoding", "preset"): "preset",
        ("encoding", "abr"): "abr",
        ("workers", "encode"): "encode_workers",
        ("workers", "integrity"): "integrity_workers",
        ("integrity", "enabled"): "integrity_check",
        ("integrity", "stable_wait"): "stable_wait",
        ("integrity", "deep_check"): "deep_check",
    }
    
    for (section, key), arg_name in mappings.items():
        if section in file_config and key in file_config[section]:
            file_val = file_config[section][key]
            # Only apply if arg wasn't explicitly set (check for default values)
            current = getattr(args, arg_name, None)
            # For lists that are empty by default
            if arg_name in ("ignore_pattern", "ignore_path", "include_pattern", "include_path"):
                if not current and file_val:
                    if isinstance(file_val, list):
                        setattr(args, arg_name, file_val)
                    elif isinstance(file_val, str) and file_val:
                        setattr(args, arg_name, [file_val])
            else:
                # Don't override CLI args (we can't easily tell, so file config is base)
                # Actually, we set file config first, then CLI will override
                pass


# -------------------- HISTORY DATABASE --------------------
class HistoryDB:
    """History storage with SQLite primary and JSONL text fallback."""
    
    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self._use_sqlite = SQLITE_AVAILABLE
        
        if self._use_sqlite:
            self._db_path = state_dir / "history.db"
            self._init_sqlite()
        else:
            self._log_path = state_dir / "history.log"
    
    def _init_sqlite(self) -> None:
        """Initialize SQLite database."""
        conn = sqlite3.connect(str(self._db_path))
        conn.execute('''
            CREATE TABLE IF NOT EXISTS conversions (
                id INTEGER PRIMARY KEY,
                input_path TEXT NOT NULL,
                output_path TEXT,
                input_size INTEGER,
                output_size INTEGER,
                duration_ms INTEGER,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL,
                backend TEXT,
                error_msg TEXT,
                encode_time_s REAL,
                integrity_time_s REAL
            )
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_started ON conversions(started_at)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_status ON conversions(status)')
        conn.commit()
        conn.close()
    
    def record_start(self, input_path: Path, backend: str, input_size: int = 0) -> int:
        """Record conversion start, return entry ID."""
        started_at = datetime.datetime.now().isoformat()
        
        if self._use_sqlite:
            conn = sqlite3.connect(str(self._db_path))
            cur = conn.execute(
                '''INSERT INTO conversions (input_path, input_size, started_at, status, backend)
                   VALUES (?, ?, ?, ?, ?)''',
                (str(input_path), input_size, started_at, "running", backend)
            )
            entry_id = cur.lastrowid
            conn.commit()
            conn.close()
            return entry_id
        else:
            # For JSONL, we use line number as pseudo-ID
            entry = {
                "id": int(time.time() * 1000),
                "input": str(input_path),
                "input_size": input_size,
                "started": started_at,
                "status": "running",
                "backend": backend
            }
            with self._log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
            return entry["id"]
    
    def record_finish(self, entry_id: int, output_path: Optional[Path], status: str,
                      encode_time: float = 0, integrity_time: float = 0,
                      output_size: int = 0, duration_ms: int = 0,
                      error_msg: str = None) -> None:
        """Update entry with completion info."""
        finished_at = datetime.datetime.now().isoformat()
        
        if self._use_sqlite:
            conn = sqlite3.connect(str(self._db_path))
            conn.execute(
                '''UPDATE conversions SET 
                   output_path=?, output_size=?, duration_ms=?, finished_at=?,
                   status=?, error_msg=?, encode_time_s=?, integrity_time_s=?
                   WHERE id=?''',
                (str(output_path) if output_path else None, output_size, duration_ms,
                 finished_at, status, error_msg, encode_time, integrity_time, entry_id)
            )
            conn.commit()
            conn.close()
        else:
            # For JSONL, append a new line with the update
            entry = {
                "id": entry_id,
                "output": str(output_path) if output_path else None,
                "output_size": output_size,
                "finished": finished_at,
                "status": status,
                "encode_time": encode_time,
                "integrity_time": integrity_time,
                "error_msg": error_msg
            }
            with self._log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
    
    def record_skip(self, input_path: Path, reason: str, backend: str) -> None:
        """Record a skipped file."""
        now = datetime.datetime.now().isoformat()
        
        if self._use_sqlite:
            conn = sqlite3.connect(str(self._db_path))
            conn.execute(
                '''INSERT INTO conversions (input_path, started_at, finished_at, status, backend, error_msg)
                   VALUES (?, ?, ?, ?, ?, ?)''',
                (str(input_path), now, now, "skipped", backend, reason)
            )
            conn.commit()
            conn.close()
        else:
            entry = {
                "input": str(input_path),
                "started": now,
                "finished": now,
                "status": "skipped",
                "backend": backend,
                "reason": reason
            }
            with self._log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
    
    def get_recent(self, limit: int = 20) -> List[dict]:
        """Get recent conversions."""
        if self._use_sqlite:
            conn = sqlite3.connect(str(self._db_path))
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                '''SELECT * FROM conversions ORDER BY started_at DESC LIMIT ?''',
                (limit,)
            )
            rows = [dict(row) for row in cur.fetchall()]
            conn.close()
            return rows
        else:
            # Read JSONL and get last N entries
            if not self._log_path.exists():
                return []
            entries = []
            with self._log_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
            # Merge updates with starts (by id)
            merged = {}
            for e in entries:
                eid = e.get("id")
                if eid in merged:
                    merged[eid].update(e)
                else:
                    merged[eid] = e
            # Sort by started time descending
            result = sorted(merged.values(), key=lambda x: x.get("started", ""), reverse=True)
            return result[:limit]
    
    def get_stats(self) -> dict:
        """Get conversion statistics."""
        if self._use_sqlite:
            conn = sqlite3.connect(str(self._db_path))
            stats = {}
            
            # Total counts by status
            cur = conn.execute('SELECT status, COUNT(*) FROM conversions GROUP BY status')
            stats["by_status"] = {row[0]: row[1] for row in cur.fetchall()}
            
            # Average encode time for successful conversions
            cur = conn.execute(
                'SELECT AVG(encode_time_s), SUM(encode_time_s) FROM conversions WHERE status="done" AND encode_time_s > 0'
            )
            row = cur.fetchone()
            stats["avg_encode_time"] = row[0] or 0
            stats["total_encode_time"] = row[1] or 0
            
            # Total size processed
            cur = conn.execute('SELECT SUM(input_size), SUM(output_size) FROM conversions WHERE status="done"')
            row = cur.fetchone()
            stats["total_input_size"] = row[0] or 0
            stats["total_output_size"] = row[1] or 0
            
            conn.close()
            return stats
        else:
            # Basic stats from JSONL
            recent = self.get_recent(1000)
            stats = {"by_status": {}}
            for e in recent:
                s = e.get("status", "unknown")
                stats["by_status"][s] = stats["by_status"].get(s, 0) + 1
            
            done = [e for e in recent if e.get("status") == "done"]
            if done:
                times = [e.get("encode_time", 0) for e in done if e.get("encode_time")]
                stats["avg_encode_time"] = sum(times) / len(times) if times else 0
                stats["total_encode_time"] = sum(times)
            else:
                stats["avg_encode_time"] = 0
                stats["total_encode_time"] = 0
            
            stats["total_input_size"] = sum(e.get("input_size", 0) for e in done)
            stats["total_output_size"] = sum(e.get("output_size", 0) for e in done)
            return stats
    
    def clean_old(self, days: int) -> int:
        """Remove entries older than N days. Returns count removed."""
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
        
        if self._use_sqlite:
            conn = sqlite3.connect(str(self._db_path))
            cur = conn.execute('DELETE FROM conversions WHERE started_at < ?', (cutoff,))
            count = cur.rowcount
            conn.commit()
            conn.close()
            return count
        else:
            # For JSONL, rewrite file without old entries
            if not self._log_path.exists():
                return 0
            entries = []
            removed = 0
            with self._log_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            e = json.loads(line)
                            if e.get("started", "") >= cutoff:
                                entries.append(line)
                            else:
                                removed += 1
                        except json.JSONDecodeError:
                            pass
            with self._log_path.open("w", encoding="utf-8") as f:
                for line in entries:
                    f.write(line + "\n")
            return removed


# Global history database (initialized in main)
HISTORY_DB: Optional[HistoryDB] = None


# -------------------- CENTRALIZED LOGGING --------------------
def get_log_path(inp: Path) -> Path:
    """Generate centralized log path for input file."""
    logs_dir = APP_DIRS.get("logs", Path.home() / ".local" / "state" / "mkv2cast" / "logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    date_str = datetime.date.today().isoformat()
    # Sanitize filename (keep only safe chars)
    safe_name = re.sub(r'[^\w\-.]', '_', inp.stem)[:80]
    return logs_dir / f"{date_str}_{safe_name}.log"


def cleanup_old_logs(days: int) -> int:
    """Remove log files older than N days. Returns count removed."""
    logs_dir = APP_DIRS.get("logs")
    if not logs_dir or not logs_dir.exists():
        return 0
    
    cutoff = time.time() - (days * 86400)
    removed = 0
    
    for f in logs_dir.glob("*.log"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        except Exception:
            pass
    
    return removed


# -------------------- CENTRALIZED TMP FILES --------------------
def get_tmp_path(inp: Path, worker_id: int, tag: str = "") -> Path:
    """Generate centralized tmp path for encoding."""
    tmp_dir = APP_DIRS.get("tmp", Path.home() / ".cache" / "mkv2cast" / "tmp")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    
    stem = inp.stem
    ext = CFG.container
    suffix = CFG.suffix
    pid = os.getpid()
    
    return tmp_dir / f"{stem}{tag}{suffix}.tmp.{pid}.{worker_id}.{ext}"


def cleanup_orphaned_tmp(max_age_hours: int = 24) -> int:
    """Remove tmp files older than max_age_hours. Returns count removed."""
    tmp_dir = APP_DIRS.get("tmp")
    if not tmp_dir or not tmp_dir.exists():
        return 0
    
    cutoff = time.time() - (max_age_hours * 3600)
    removed = 0
    
    for f in tmp_dir.glob("*.tmp.*.mkv"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        except Exception:
            pass
    
    for f in tmp_dir.glob("*.tmp.*.mp4"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        except Exception:
            pass
    
    return removed


# -------------------- MULTI-USER CLEANUP (ROOT) --------------------
def is_running_as_root() -> bool:
    """Check if script is running as root."""
    return os.geteuid() == 0


def get_all_users_mkv2cast_dirs() -> List[Dict[str, Path]]:
    """
    Get mkv2cast directories for all users on the system.
    Only returns users that have mkv2cast data directories.
    """
    users = []
    home_base = Path("/home")
    
    if not home_base.exists():
        return users
    
    try:
        for entry in home_base.iterdir():
            if not entry.is_dir():
                continue
            
            # Check for mkv2cast directories
            cache_dir = entry / ".cache" / "mkv2cast"
            state_dir = entry / ".local" / "state" / "mkv2cast"
            config_dir = entry / ".config" / "mkv2cast"
            
            if cache_dir.exists() or state_dir.exists():
                users.append({
                    "user": entry.name,
                    "home": entry,
                    "cache": cache_dir,
                    "tmp": cache_dir / "tmp",
                    "state": state_dir,
                    "logs": state_dir / "logs",
                    "config": config_dir
                })
    except PermissionError:
        pass
    
    return users


def cleanup_all_users_logs(days: int, verbose: bool = True) -> Dict[str, int]:
    """
    Clean logs for all users (requires root).
    Returns dict of {username: removed_count}.
    """
    results = {}
    users = get_all_users_mkv2cast_dirs()
    
    for user_info in users:
        username = user_info["user"]
        logs_dir = user_info["logs"]
        
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
    results = {}
    users = get_all_users_mkv2cast_dirs()
    
    for user_info in users:
        username = user_info["user"]
        tmp_dir = user_info["tmp"]
        
        if not tmp_dir.exists():
            continue
        
        if max_age_hours > 0:
            cutoff = time.time() - (max_age_hours * 3600)
        else:
            cutoff = time.time()  # Everything is older than now
        
        removed = 0
        
        try:
            for pattern in ["*.tmp.*.mkv", "*.tmp.*.mp4"]:
                for f in tmp_dir.glob(pattern):
                    try:
                        # For max_age_hours=0, remove all; otherwise check age
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


# -------------------- CONFIGURATION --------------------
@dataclass
class Config:
    """All configuration options for mkv2cast."""
    # Output settings
    suffix: str = ".cast"
    container: str = "mkv"
    
    # Scan settings
    recursive: bool = True
    ignore_patterns: List[str] = None  # type: ignore
    ignore_paths: List[str] = None  # type: ignore
    include_patterns: List[str] = None  # type: ignore
    include_paths: List[str] = None  # type: ignore
    
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
    hw: str = "auto"
    
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


# Global config instance (set by parse_args)
CFG = Config()


def parse_args() -> Tuple[Config, Optional[Path]]:
    """Parse command-line arguments and return config + optional file path."""
    parser = argparse.ArgumentParser(
        description="Smart MKV -> Cast compatible converter with VAAPI/QSV hardware acceleration.",
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
  %(prog)s --ignore-path Downloads/temp  # Ignore files in temp folder
  %(prog)s --include-path Movies       # Only process files in Movies folder
  %(prog)s --show-dirs                 # Show config/cache/log directories
  %(prog)s --history                   # Show recent conversion history (20 lines)
  %(prog)s --history 100               # Show last 100 conversions
  %(prog)s --history-stats             # Show conversion statistics
  %(prog)s --clean-tmp                 # Clean orphaned temp files
  %(prog)s --clean-logs 30             # Remove logs older than 30 days
        """
    )
    
    # Version
    parser.add_argument("-V", "--version", action="version",
        version=f"%(prog)s {__version__}\n"
                f"Author: {__author__}\n"
                f"License: {__license__}\n"
                f"URL: {__url__}")
    
    # Positional argument
    parser.add_argument("file", nargs="?", help="Optional .mkv file to process (otherwise scan folder)")
    
    # Output settings
    out_group = parser.add_argument_group("Output settings")
    out_group.add_argument("--suffix", default=".cast", help="Output file suffix (default: .cast)")
    out_group.add_argument("--container", choices=["mkv", "mp4"], default="mkv", help="Output container (default: mkv)")
    
    # Scan settings
    scan_group = parser.add_argument_group("Scan settings")
    scan_group.add_argument("-r", "--recursive", action="store_true", default=True, help="Scan directories recursively (default: true)")
    scan_group.add_argument("--no-recursive", action="store_false", dest="recursive", help="Disable recursive scanning")
    scan_group.add_argument("--ignore-pattern", "-I", action="append", default=[], metavar="PATTERN",
                           help="Ignore files matching pattern (glob, can be used multiple times). Ex: '*sample*', '*.eng.*'")
    scan_group.add_argument("--ignore-path", action="append", default=[], metavar="PATH",
                           help="Ignore specific paths or folders (can be used multiple times). Ex: '/path/to/skip', 'SomeFolder'")
    scan_group.add_argument("--include-pattern", "-i", action="append", default=[], metavar="PATTERN",
                           help="Only process files matching pattern (glob). Ex: '*2024*', '*.French.*'")
    scan_group.add_argument("--include-path", action="append", default=[], metavar="PATH",
                           help="Only process files in matching paths. Ex: 'Movies', '/data/films'")
    
    # Debug/test
    debug_group = parser.add_argument_group("Debug/test")
    debug_group.add_argument("-d", "--debug", action="store_true", help="Enable debug output")
    debug_group.add_argument("-n", "--dryrun", action="store_true", help="Dry run - show commands without executing")
    
    # Codec decisions
    codec_group = parser.add_argument_group("Codec decisions")
    codec_group.add_argument("--skip-when-ok", action="store_true", default=True, help="Skip files already compatible (default: true)")
    codec_group.add_argument("--no-skip-when-ok", action="store_false", dest="skip_when_ok", help="Process all files even if compatible")
    codec_group.add_argument("--force-h264", action="store_true", help="Force H264 transcoding even if already H264")
    codec_group.add_argument("--allow-hevc", action="store_true", help="Allow HEVC passthrough for SDR 8-bit content")
    codec_group.add_argument("--force-aac", action="store_true", help="Force AAC transcoding even if already AAC")
    codec_group.add_argument("--keep-surround", action="store_true", help="Keep surround audio channels (default: downmix to stereo)")
    codec_group.add_argument("--no-silence", action="store_false", dest="add_silence_if_no_audio", help="Don't add silence track if no audio")
    
    # Encoding quality
    quality_group = parser.add_argument_group("Encoding quality")
    quality_group.add_argument("--abr", default="192k", help="Audio bitrate (default: 192k)")
    quality_group.add_argument("--crf", type=int, default=20, help="CRF value for CPU encoding (default: 20)")
    quality_group.add_argument("--preset", default="slow", choices=["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"], help="x264 preset (default: slow)")
    
    # Hardware acceleration
    hw_group = parser.add_argument_group("Hardware acceleration")
    hw_group.add_argument("--hw", choices=["auto", "qsv", "vaapi", "cpu"], default="auto", help="Hardware backend (default: auto)")
    hw_group.add_argument("--vaapi-device", default="/dev/dri/renderD128", help="VAAPI device path")
    hw_group.add_argument("--vaapi-qp", type=int, default=23, help="VAAPI QP value (default: 23)")
    hw_group.add_argument("--qsv-quality", type=int, default=23, help="QSV quality value (default: 23)")
    
    # Integrity checks
    integrity_group = parser.add_argument_group("Integrity checks")
    integrity_group.add_argument("--integrity-check", action="store_true", default=True, help="Enable integrity check (default: true)")
    integrity_group.add_argument("--no-integrity-check", action="store_false", dest="integrity_check", help="Disable integrity check")
    integrity_group.add_argument("--stable-wait", type=int, default=3, help="Seconds to wait for file stability (default: 3)")
    integrity_group.add_argument("--deep-check", action="store_true", help="Enable deep decode check (slow)")
    
    # UI settings
    ui_group = parser.add_argument_group("UI settings")
    ui_group.add_argument("--no-progress", action="store_false", dest="progress", help="Disable progress bar")
    ui_group.add_argument("--bar-width", type=int, default=26, help="Progress bar width (legacy mode)")
    ui_group.add_argument("--ui-refresh-ms", type=int, default=120, help="UI refresh interval in ms")
    ui_group.add_argument("--stats-period", type=float, default=0.2, help="FFmpeg stats period")
    
    # Pipeline mode
    pipeline_group = parser.add_argument_group("Pipeline mode")
    pipeline_group.add_argument("--pipeline", action="store_true", default=True, help="Enable parallel pipeline (default: true)")
    pipeline_group.add_argument("--no-pipeline", action="store_false", dest="pipeline", help="Disable parallel pipeline (sequential mode)")
    
    # Parallelism
    parallel_group = parser.add_argument_group("Parallelism")
    parallel_group.add_argument("--encode-workers", type=int, default=0, metavar="N",
        help="Number of parallel encodes (0=auto, default: auto)")
    parallel_group.add_argument("--integrity-workers", type=int, default=0, metavar="N",
        help="Number of parallel integrity checks (0=auto, default: auto)")
    
    # Utility commands
    util_group = parser.add_argument_group("Utility commands")
    util_group.add_argument("--show-dirs", action="store_true",
        help="Show XDG directory paths and exit")
    util_group.add_argument("--history", nargs="?", const=20, type=int, metavar="N",
        help="Show recent conversion history (default: 20 lines, max: 1000)")
    util_group.add_argument("--history-stats", action="store_true",
        help="Show conversion statistics and exit")
    util_group.add_argument("--clean-tmp", action="store_true",
        help="Clean orphaned temp files from cache and exit")
    util_group.add_argument("--clean-logs", type=int, metavar="DAYS",
        help="Remove logs older than N days and exit")
    util_group.add_argument("--clean-history", type=int, metavar="DAYS",
        help="Remove history entries older than N days and exit")
    util_group.add_argument("--check-requirements", action="store_true",
        help="Check system requirements and Python dependencies, then exit")
    
    args = parser.parse_args()
    
    # Build config
    cfg = Config(
        suffix=args.suffix,
        container=args.container,
        recursive=args.recursive,
        ignore_patterns=args.ignore_pattern or [],
        ignore_paths=args.ignore_path or [],
        include_patterns=args.include_pattern or [],
        include_paths=args.include_path or [],
        debug=args.debug,
        dryrun=args.dryrun,
        skip_when_ok=args.skip_when_ok,
        force_h264=args.force_h264,
        allow_hevc=args.allow_hevc,
        force_aac=args.force_aac,
        keep_surround=args.keep_surround,
        add_silence_if_no_audio=args.add_silence_if_no_audio,
        abr=args.abr,
        crf=args.crf,
        preset=args.preset,
        hw=args.hw,
        vaapi_device=args.vaapi_device,
        vaapi_qp=args.vaapi_qp,
        qsv_quality=args.qsv_quality,
        integrity_check=args.integrity_check,
        stable_wait=args.stable_wait,
        deep_check=args.deep_check,
        progress=args.progress,
        bar_width=args.bar_width,
        ui_refresh_ms=args.ui_refresh_ms,
        stats_period=args.stats_period,
        pipeline=args.pipeline,
        encode_workers=args.encode_workers,
        integrity_workers=args.integrity_workers,
    )
    
    single = Path(args.file).expanduser() if args.file else None
    return cfg, single


# -------------------- UTIL --------------------
def dbg(msg: str) -> None:
    if CFG.debug:
        print(f"DEBUG: {msg}", flush=True)


def fmt_hms(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    s = int(round(seconds))
    h = s // 3600
    m = (s % 3600) // 60
    r = s % 60
    return f"{h:02d}:{m:02d}:{r:02d}"


def fmt_ms(ms: int) -> str:
    return fmt_hms(ms / 1000.0)


def term_width() -> int:
    try:
        return shutil.get_terminal_size((120, 20)).columns
    except Exception:
        return 120


def mkbar(pct: int) -> str:
    pct = max(0, min(100, pct))
    filled = int(pct * CFG.bar_width / 100)
    empty = CFG.bar_width - filled
    return "#" * filled + "-" * empty


def shorten(s: str, maxlen: int) -> str:
    if maxlen <= 0:
        return ""
    if len(s) <= maxlen:
        return s
    if maxlen <= 3:
        return s[:maxlen]
    return s[: maxlen - 3] + "..."


def run_quiet(cmd: List[str], timeout: float = 10.0) -> bool:
    try:
        p = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout)
        return p.returncode == 0
    except Exception:
        return False


def ffprobe_json(path: Path) -> dict:
    cmd = [
        "ffprobe", "-v", "error",
        "-print_format", "json",
        "-show_streams", "-show_format",
        str(path)
    ]
    out = subprocess.check_output(cmd)
    return json.loads(out)


def probe_duration_ms(path: Path) -> int:
    try:
        cmd = ["ffprobe", "-v", "error", "-of", "json", "-show_entries", "format=duration:stream=codec_type,duration", str(path)]
        j = json.loads(subprocess.check_output(cmd))
        dur = None
        if "format" in j and j["format"].get("duration"):
            dur = float(j["format"]["duration"])
        if (dur is None or dur <= 0) and "streams" in j:
            for s in j["streams"]:
                if s.get("codec_type") == "video" and s.get("duration"):
                    d2 = float(s["duration"])
                    if d2 > 0:
                        dur = d2
                        break
        if dur is None or dur <= 0:
            dbg(f"probe_duration_ms: no duration found for {path.name}")
            return 0
        result = int(dur * 1000)
        dbg(f"probe_duration_ms: {path.name} -> {dur}s = {result}ms")
        return result
    except Exception as e:
        dbg(f"probe_duration_ms: error for {path.name}: {e}")
        return 0


def file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except Exception:
        return 0


# -------------------- AUTO DETECT WORKERS --------------------
def get_total_ram_gb() -> int:
    """Get total RAM in GB by reading /proc/meminfo (Linux)."""
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    # Format: MemTotal:       16000000 kB
                    parts = line.split()
                    if len(parts) >= 2:
                        kb = int(parts[1])
                        return kb // (1024 * 1024)  # Convert to GB
    except Exception:
        pass
    # Fallback: assume 8GB
    return 8


def get_gpu_info() -> Tuple[str, int]:
    """
    Detect GPU type and VRAM.
    Returns: (gpu_type, vram_mb)
    gpu_type: "nvidia", "amd", "intel", "unknown"
    """
    gpu_type = "unknown"
    vram_mb = 0
    
    # Try to detect NVIDIA GPU
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            vram_mb = int(result.stdout.strip().split('\n')[0])
            gpu_type = "nvidia"
            return gpu_type, vram_mb
    except Exception:
        pass
    
    # Try to detect AMD GPU via VRAM info
    try:
        # Check for AMD GPU via lspci
        result = subprocess.run(["lspci"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and "AMD" in result.stdout and "VGA" in result.stdout:
            gpu_type = "amd"
            # Try to get VRAM from /sys
            import glob
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
            # Intel iGPU uses system RAM, estimate ~2GB dedicated
            vram_mb = 2048
            return gpu_type, vram_mb
    except Exception:
        pass
    
    return gpu_type, vram_mb


def auto_detect_workers(backend: str) -> Tuple[int, int]:
    """
    Auto-detect optimal worker counts based on backend and system resources.
    Conservative defaults to avoid overwhelming laptop hardware.
    
    Returns: (encode_workers, integrity_workers)
    """
    ram_gb = get_total_ram_gb()
    cores = os.cpu_count() or 4
    
    if backend in ("vaapi", "qsv"):
        # GPU encoding - detect GPU capabilities
        gpu_type, vram_mb = get_gpu_info()
        dbg(f"auto_detect: GPU backend ({backend}), RAM={ram_gb}GB, GPU={gpu_type}, VRAM={vram_mb}MB, cores={cores}")
        
        # Base encode workers on VRAM (if detected) or RAM as fallback
        if vram_mb >= 8192:  # 8GB+ VRAM (high-end desktop GPU)
            encode = 3
        elif vram_mb >= 4096:  # 4GB+ VRAM (mid-range GPU)
            encode = 2
        elif vram_mb > 0:  # Detected but low VRAM
            encode = 1
        else:
            # Fallback to RAM-based detection (conservative)
            # Intel iGPU or unknown GPU - be conservative
            if gpu_type == "intel" or ram_gb < 16:
                encode = 1
            elif ram_gb >= 32:
                encode = 2
            else:
                encode = 1
        
        # For laptops (low RAM + integrated GPU), stay conservative
        if ram_gb <= 16 and gpu_type in ("intel", "unknown"):
            encode = min(encode, 1)
        
        integrity = encode + 1
        
    else:
        # CPU encoding - depends on cores, very conservative
        # Encoding is CPU-intensive, don't parallelize too much
        dbg(f"auto_detect: CPU backend, RAM={ram_gb}GB, cores={cores}")
        
        if cores >= 16 and ram_gb >= 32:
            encode = 2
        elif cores >= 8 and ram_gb >= 16:
            encode = 1
        else:
            encode = 1
        
        # Integrity check is less intensive
        if cores >= 8:
            integrity = 2
        else:
            integrity = 1
    
    dbg(f"auto_detect: final workers: encode={encode}, integrity={integrity}")
    return encode, integrity


# -------------------- OUTPUT SKIP RULES --------------------
def is_our_output_or_tmp(name: str) -> bool:
    n = name
    if ".tmp." in n:
        return True
    if CFG.suffix in n:
        return True
    if ".h264." in n or ".aac." in n or ".remux." in n:
        return True
    return False


def _matches_pattern(filepath: Path, patterns: List[str]) -> bool:
    """Check if filepath matches any of the patterns (glob on filename)."""
    if not patterns:
        return False
    name = filepath.name.lower()
    for pattern in patterns:
        pattern_lower = pattern.lower()
        if fnmatch.fnmatch(name, pattern_lower):
            return True
        # Also try matching without leading * if pattern has no wildcards
        if "*" not in pattern and "?" not in pattern:
            if fnmatch.fnmatch(name, f"*{pattern_lower}*"):
                return True
    return False


def _matches_path(filepath: Path, paths: List[str]) -> bool:
    """Check if filepath matches any of the paths."""
    if not paths:
        return False
    path_str = str(filepath)
    for check_path in paths:
        # Normalize path for comparison
        check_path_normalized = check_path.rstrip("/\\")
        
        # Check if it's a folder name (no path separator)
        if "/" not in check_path and "\\" not in check_path:
            # Match folder anywhere in path
            if f"/{check_path_normalized}/" in path_str or f"\\{check_path_normalized}\\" in path_str:
                return True
            if path_str.endswith(f"/{check_path_normalized}") or path_str.endswith(f"\\{check_path_normalized}"):
                return True
        else:
            # Full/partial path match
            if check_path_normalized in path_str:
                return True
    return False


def should_process_file(filepath: Path) -> Tuple[bool, Optional[str]]:
    """
    Check if file should be processed based on include and ignore filters.
    Returns (should_process, skip_reason).
    
    Logic:
    - If include filters are set, file must match at least one
    - Then ignore filters are applied
    """
    # First check include filters (if any are set, file must match)
    if CFG.include_patterns or CFG.include_paths:
        matches_include = (
            _matches_pattern(filepath, CFG.include_patterns) or
            _matches_path(filepath, CFG.include_paths)
        )
        if not matches_include:
            return False, "no include match"
    
    # Then check ignore filters
    if _matches_pattern(filepath, CFG.ignore_patterns):
        for pattern in CFG.ignore_patterns:
            if fnmatch.fnmatch(filepath.name.lower(), pattern.lower()):
                return False, f"matches ignore pattern '{pattern}'"
            if "*" not in pattern and fnmatch.fnmatch(filepath.name.lower(), f"*{pattern.lower()}*"):
                return False, f"matches ignore pattern '{pattern}'"
        return False, "matches ignore pattern"
    
    if _matches_path(filepath, CFG.ignore_paths):
        for check_path in CFG.ignore_paths:
            if check_path.rstrip("/\\") in str(filepath):
                return False, f"in ignored path '{check_path}'"
        return False, "in ignored path"
    
    return True, None


# Legacy function for backward compatibility
def should_ignore_file(filepath: Path) -> Optional[str]:
    """
    Check if file should be ignored based on patterns and paths.
    Returns reason string if ignored, None otherwise.
    """
    should_process, reason = should_process_file(filepath)
    return reason if not should_process else None


def output_exists_for_input(inp: Path) -> bool:
    d = inp.parent
    stem = inp.stem
    ext = CFG.container
    patterns = [f"{stem}*{CFG.suffix}.{ext}"]
    for pat in patterns:
        for p in d.glob(pat):
            if p.is_file() and ".tmp." not in p.name:
                return True
    for p in d.glob(f"{stem}*.tmp.*.{ext}"):
        if p.is_file():
            return True
    return False


# -------------------- BACKEND PICK --------------------
def have_encoder(name: str) -> bool:
    return run_quiet(["ffmpeg", "-hide_banner", "-h", f"encoder={name}"], timeout=4.0)


def test_qsv() -> bool:
    if not Path(CFG.vaapi_device).exists():
        return False
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-init_hw_device", f"qsv=hw:{CFG.vaapi_device}", "-filter_hw_device", "hw",
        "-f", "lavfi", "-i", "testsrc2=size=128x128:rate=30", "-t", "0.2",
        "-vf", "format=nv12", "-c:v", "h264_qsv", "-global_quality", "35",
        "-an", "-f", "null", "-"
    ]
    return run_quiet(cmd, timeout=6.0)


def test_vaapi() -> bool:
    if not Path(CFG.vaapi_device).exists():
        return False
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-vaapi_device", CFG.vaapi_device,
        "-f", "lavfi", "-i", "testsrc2=size=128x128:rate=30", "-t", "0.2",
        "-vf", "format=nv12,hwupload", "-c:v", "h264_vaapi", "-qp", "35",
        "-an", "-f", "null", "-"
    ]
    return run_quiet(cmd, timeout=6.0)


def pick_backend() -> str:
    if CFG.hw != "auto":
        return CFG.hw
    if have_encoder("h264_qsv") and test_qsv():
        return "qsv"
    if have_encoder("h264_vaapi") and test_vaapi():
        return "vaapi"
    return "cpu"


def video_args_for(backend: str) -> List[str]:
    if backend == "qsv":
        return ["-vf", "format=nv12", "-c:v", "h264_qsv", "-global_quality", str(CFG.qsv_quality), "-profile:v", "high", "-level", "4.1"]
    if backend == "vaapi":
        return ["-vaapi_device", CFG.vaapi_device, "-vf", "format=nv12,hwupload", "-c:v", "h264_vaapi", "-qp", str(CFG.vaapi_qp), "-profile:v", "high", "-level", "4.1"]
    if backend == "cpu":
        return ["-c:v", "libx264", "-preset", CFG.preset, "-crf", str(CFG.crf), "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1"]
    raise RuntimeError(f"Unknown backend: {backend}")


# -------------------- DECISION LOGIC --------------------
@dataclass
class Decision:
    need_v: bool
    need_a: bool
    aidx: int
    add_silence: bool
    reason_v: str
    vcodec: str
    vpix: str
    vbit: int
    vhdr: bool
    vprof: str
    vlevel: int
    acodec: str
    ach: int
    format_name: str


def parse_bitdepth_from_pix(pix: str) -> int:
    pix = (pix or "").lower()
    m = re.search(r"(10|12)le", pix)
    if m:
        return int(m.group(1))
    if "p010" in pix:
        return 10
    return 8


def is_audio_description(title: str) -> bool:
    t = (title or "").lower()
    return ("audio-description" in t) or ("audiodescription" in t) or ("visual impaired" in t) or (" v.i" in t) or (" ad" in t)


def decide_for(path: Path) -> Decision:
    j = ffprobe_json(path)
    fmt = j.get("format", {}) or {}
    format_name = fmt.get("format_name", "") or ""

    streams = j.get("streams", []) or []
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    audios = [s for s in streams if s.get("codec_type") == "audio"]

    def low(x): return (x or "").lower()
    def tag(s, k): return (s.get("tags") or {}).get(k, "")

    vcodec = low((v or {}).get("codec_name", ""))
    vpix = low((v or {}).get("pix_fmt", ""))
    vprof = low((v or {}).get("profile", ""))
    vlevel = int((v or {}).get("level") or 0)
    vbit = parse_bitdepth_from_pix(vpix)

    cprim = low((v or {}).get("color_primaries", ""))
    ctrans = low((v or {}).get("color_transfer", ""))
    vhdr = (cprim in {"bt2020", "bt2020nc", "bt2020c"}) or (ctrans in {"smpte2084", "arib-std-b67"})

    fr_langs = {"fre", "fra", "fr"}
    fr = [a for a in audios if low(tag(a, "language")) in fr_langs and not is_audio_description(tag(a, "title"))]
    if not fr:
        fr = [a for a in audios if low(tag(a, "language")) in fr_langs]
    a = fr[0] if fr else (audios[0] if audios else None)

    aidx = int(a.get("index")) if a else -1
    acodec = low((a or {}).get("codec_name", ""))
    ach = int((a or {}).get("channels") or 0)

    pname = path.name.upper()
    reason_v = ""
    video_ok = False

    if vcodec == "av1" or "AV1" in pname:
        video_ok = False
        reason_v = "AV1 (ou filename AV1) => transcode forcé"
    elif CFG.force_h264:
        video_ok = False
        reason_v = "--force-h264"
    elif vcodec == "h264":
        if (vbit <= 8 and vpix in {"yuv420p", "yuvj420p"} and (not vhdr) and vprof not in {"high 10", "high10", "high 4:2:2", "high 4:4:4"} and (vlevel == 0 or vlevel <= 41)):
            video_ok = True
            reason_v = "H264 8-bit SDR"
        else:
            video_ok = False
            reason_v = f"H264 contraintes non OK (bit={vbit},pix={vpix},hdr={vhdr},prof={vprof},level={vlevel})"
    elif vcodec in {"hevc", "h265"}:
        if CFG.allow_hevc and (vbit <= 8) and (not vhdr):
            video_ok = True
            reason_v = "HEVC SDR 8-bit (--allow-hevc)"
        else:
            video_ok = False
            reason_v = "HEVC => transcode (par défaut)"
    else:
        video_ok = False
        reason_v = f"codec video {vcodec} => transcode"

    need_v = not video_ok

    audio_ok = acodec in {"aac", "mp3"}
    need_a = False
    if aidx < 0:
        need_a = False
    elif CFG.force_aac:
        need_a = True
    elif not audio_ok:
        need_a = True

    add_silence = False
    if aidx < 0 and CFG.add_silence_if_no_audio:
        add_silence = True
        need_a = True

    return Decision(
        need_v=need_v,
        need_a=need_a,
        aidx=aidx,
        add_silence=add_silence,
        reason_v=reason_v,
        vcodec=vcodec, vpix=vpix, vbit=vbit, vhdr=vhdr, vprof=vprof, vlevel=vlevel,
        acodec=acodec, ach=ach,
        format_name=format_name
    )


# -------------------- UI PROGRESS (Legacy fallback) --------------------
@dataclass
class UIState:
    stage: str
    pct: int
    cur: int
    total: int
    base: str
    eta: str
    speed: str
    elapsed: str = ""


class LegacyProgressUI:
    """Fallback progress UI when rich is not available."""
    def __init__(self):
        self.enabled = CFG.progress and sys.stdout.isatty()
        self._last_render: Optional[str] = None

    def render(self, st: UIState):
        if not self.enabled:
            return
        w = term_width()

        bar = mkbar(st.pct)
        elapsed_str = f" {st.elapsed}" if st.elapsed else ""
        left = f"[{bar}] {st.pct:3d}% | {st.stage} | ({st.cur}/{st.total}){elapsed_str} "
        right = f"| {st.eta} {st.speed}".rstrip()

        avail = max(10, w - len(left) - len(right) - 1)
        name = shorten(st.base, avail)

        line = f"{left}{name} {right}"
        pad = ""
        if self._last_render is not None and len(self._last_render) > len(line):
            pad = " " * (len(self._last_render) - len(line))
        if line != self._last_render:
            sys.stdout.write("\r" + line + pad)
            sys.stdout.flush()
            self._last_render = line

    def endline(self):
        if not self.enabled:
            return
        sys.stdout.write("\r" + " " * (len(self._last_render) if self._last_render else 80) + "\r")
        sys.stdout.flush()
        self._last_render = None

    def log(self, msg: str):
        if self.enabled and self._last_render:
            sys.stdout.write("\r" + " " * len(self._last_render) + "\r")
            sys.stdout.flush()
        print(msg, flush=True)
        self._last_render = None


# -------------------- RICH PROGRESS UI (Multi-worker) --------------------
@dataclass
class JobStatus:
    """Tracks the status of a single file."""
    inp: Path
    stage: str = "WAITING"  # WAITING, INTEGRITY, ENCODE, DONE, FAILED, SKIPPED
    pct: int = 0
    speed: str = ""
    dur_ms: int = 0  # Total duration for ETA calc
    out_ms: int = 0  # Current position in ms
    
    # Timing
    start_time: float = 0
    integrity_start: float = 0
    integrity_elapsed: float = 0
    encode_start: float = 0
    encode_elapsed: float = 0
    total_elapsed: float = 0
    
    # Result
    result_msg: str = ""
    output_file: str = ""
    worker_id: int = -1
    
    # History tracking
    history_id: int = 0


class RichProgressUI:
    """Rich-based progress UI showing all files with their status."""
    
    def __init__(self, total_files: int, encode_workers: int, integrity_workers: int):
        self.console = Console()
        self.total_files = total_files
        self.encode_workers = encode_workers
        self.integrity_workers = integrity_workers
        self.lock = threading.Lock()
        
        # Stats
        self.ok = 0
        self.skipped = 0
        self.failed = 0
        self.processed = 0
        
        # All jobs status
        self.jobs: Dict[str, JobStatus] = {}  # keyed by file path string
        
        # Completed jobs log (for display)
        self.completed_log: List[str] = []
        self.max_completed_lines = 10
        
        # Live display
        self.live: Optional[Live] = None
        self._stop_event = threading.Event()
        self._refresh_thread: Optional[threading.Thread] = None
    
    def _make_progress_bar(self, pct: int, width: int = 25) -> Text:
        """Create a colored progress bar."""
        pct = max(0, min(100, pct))
        filled = int(pct * width / 100)
        empty = width - filled
        
        bar = Text()
        bar.append("│", style="dim")
        bar.append("█" * filled, style="green")
        bar.append("░" * empty, style="dim")
        bar.append("│", style="dim")
        return bar
    
    def _parse_speed(self, speed_str: str) -> Optional[float]:
        """Parse speed string like '32.5x' to float."""
        if not speed_str:
            return None
        m = re.match(r"^\s*([0-9]+(?:\.[0-9]+)?)x\s*$", speed_str)
        if m:
            try:
                return float(m.group(1))
            except Exception:
                return None
        return None
    
    def _format_eta(self, job: JobStatus, elapsed: float) -> str:
        """Calculate ETA for a job based on speed or elapsed time."""
        if job.pct <= 0 or elapsed <= 0:
            return "--:--:--"
        
        # If at 100%, show "finishing" instead of ETA
        if job.pct >= 100:
            return "finish..."
        
        # Try speed-based ETA first (more accurate for encode)
        speed_x = self._parse_speed(job.speed)
        if speed_x and speed_x > 0 and job.dur_ms > 0 and job.out_ms > 0:
            remaining_ms = job.dur_ms - job.out_ms
            if remaining_ms > 0:
                eta_s = (remaining_ms / 1000.0) / speed_x
                return fmt_hms(eta_s)
        
        # Time-based ETA
        if job.pct >= 99:
            # Almost done, estimate ~1% more time
            avg_time_per_pct = elapsed / job.pct
            return fmt_hms(avg_time_per_pct)
        
        rate = job.pct / elapsed
        remaining_pct = 100 - job.pct
        eta_s = remaining_pct / rate if rate > 0 else 0
        return fmt_hms(eta_s) if eta_s > 0 else "--:--:--"
    
    def _render(self) -> Group:
        """Render the current state as a rich Group."""
        with self.lock:
            parts = []
            
            # Categorize all jobs
            done_jobs = [j for j in self.jobs.values() if j.stage == "DONE"]
            skip_jobs = [j for j in self.jobs.values() if j.stage == "SKIPPED"]
            fail_jobs = [j for j in self.jobs.values() if j.stage == "FAILED"]
            active_jobs = [j for j in self.jobs.values() if j.stage in ("INTEGRITY", "ENCODE")]
            waiting_encode = [j for j in self.jobs.values() if j.stage == "WAITING_ENCODE"]
            waiting_check = [j for j in self.jobs.values() if j.stage == "WAITING"]
            
            # 1. SKIP files (grey)
            for job in skip_jobs[-8:]:  # Last 8
                filename = shorten(job.inp.name, 50)
                reason = job.result_msg or ""
                line = Text()
                line.append("⊘ SKIP ", style="dim")
                line.append(filename, style="dim")
                if reason:
                    line.append(f" ({reason})", style="dim italic")
                parts.append(line)
            
            # 2. DONE files (green) with timing
            for job in done_jobs[-5:]:  # Last 5
                filename = shorten(job.inp.name, 40)
                line = Text()
                line.append("✓ DONE ", style="bold green")
                line.append(filename, style="green")
                # Timing info
                timing = []
                if job.integrity_elapsed > 0:
                    timing.append(f"int:{fmt_hms(job.integrity_elapsed)}")
                if job.encode_elapsed > 0:
                    timing.append(f"enc:{fmt_hms(job.encode_elapsed)}")
                if job.total_elapsed > 0:
                    timing.append(f"tot:{fmt_hms(job.total_elapsed)}")
                if timing:
                    line.append(f" ({' '.join(timing)})", style="dim")
                parts.append(line)
            
            # 3. FAIL files (red)
            for job in fail_jobs[-3:]:  # Last 3
                filename = shorten(job.inp.name, 50)
                reason = job.result_msg or "error"
                line = Text()
                line.append("✗ FAIL ", style="bold red")
                line.append(filename, style="red")
                line.append(f" ({reason})", style="red dim")
                parts.append(line)
            
            # Separator if we have completed items and active work
            if parts and (active_jobs or waiting_encode):
                parts.append(Text("─" * 60, style="dim"))
            
            # 4. WAITING_ENCODE files (cyan, brief) - passed integrity, waiting for encode slot
            for job in waiting_encode[:3]:  # Show first 3
                filename = shorten(job.inp.name, 50)
                line = Text()
                line.append("⏳ QUEUE ", style="cyan")
                line.append(filename, style="cyan dim")
                if job.integrity_elapsed > 0:
                    line.append(f" (check:{fmt_hms(job.integrity_elapsed)})", style="dim")
                parts.append(line)
            if len(waiting_encode) > 3:
                parts.append(Text(f"   ... +{len(waiting_encode) - 3} en file d'attente", style="cyan dim"))
            
            # 5. ACTIVE jobs (INTEGRITY and ENCODE) with progress bars - YELLOW
            for job in sorted(active_jobs, key=lambda x: (0 if x.stage == "ENCODE" else 1, x.worker_id)):
                filename = shorten(job.inp.name, 40)
                
                if job.stage == "INTEGRITY":
                    elapsed = time.time() - job.integrity_start if job.integrity_start > 0 else 0
                    stage_icon = "🔍"
                    stage_text = "CHECK"
                else:  # ENCODE
                    elapsed = time.time() - job.encode_start if job.encode_start > 0 else 0
                    stage_icon = "⚡"
                    stage_text = "ENCODE"
                
                eta = self._format_eta(job, elapsed)
                speed_str = f" {job.speed}" if job.speed else ""
                
                line = Text()
                line.append(f"{stage_icon} ", style="yellow")
                line.append(f"{stage_text:7}", style="bold yellow")
                line.append(" ")
                line.append_text(self._make_progress_bar(job.pct))
                line.append(f" {job.pct:3d}%", style="bold yellow")
                line.append(f" {fmt_hms(elapsed)}", style="blue")
                line.append(f" ETA:{eta}", style="dim")
                line.append(speed_str, style="magenta")
                line.append(f" {filename}", style="bold yellow")
                
                parts.append(line)
            
            # 6. Waiting for integrity check (just count at bottom)
            if waiting_check:
                parts.append(Text(f"⏳ En attente de vérification: {len(waiting_check)} fichier(s)", style="dim"))
            
            if not parts:
                parts.append(Text("Initialisation...", style="dim"))
            
            return Group(*parts)
    
    def _refresh_loop(self):
        """Background thread that refreshes the display."""
        while not self._stop_event.is_set():
            try:
                if self.live:
                    self.live.update(self._render())
            except Exception:
                pass
            time.sleep(0.1)  # 10 FPS refresh
    
    def start(self):
        """Start the live display."""
        self.live = Live(
            self._render(),
            console=self.console,
            refresh_per_second=10,
            transient=False
        )
        self.live.start()
        
        # Start background refresh thread
        self._refresh_thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self._refresh_thread.start()
    
    def stop(self):
        """Stop the live display."""
        self._stop_event.set()
        if self._refresh_thread:
            self._refresh_thread.join(timeout=1.0)
        if self.live:
            try:
                self.live.update(self._render())  # Final render
                self.live.stop()
            except Exception:
                pass
            finally:
                self.live = None
    
    def register_job(self, inp: Path, backend: str = ""):
        """Register a new job in waiting state."""
        with self.lock:
            key = str(inp)
            if key not in self.jobs:
                job = JobStatus(inp=inp, stage="WAITING", start_time=time.time())
                
                # Record start to history
                if HISTORY_DB:
                    try:
                        input_size = inp.stat().st_size if inp.exists() else 0
                        job.history_id = HISTORY_DB.record_start(inp, backend, input_size)
                    except Exception:
                        pass
                
                self.jobs[key] = job
    
    def start_integrity(self, worker_id: int, _filename: str, inp: Path):
        """Start integrity check for a file."""
        with self.lock:
            key = str(inp)
            if key in self.jobs:
                self.jobs[key].stage = "INTEGRITY"
                self.jobs[key].integrity_start = time.time()
                self.jobs[key].worker_id = worker_id
                self.jobs[key].pct = 0
                self.jobs[key].speed = ""
    
    def update_integrity(self, worker_id: int, _stage: str, pct: int, _filename: str, speed: str = "", inp: Optional[Path] = None):
        """Update integrity progress."""
        with self.lock:
            # Find job by worker_id if inp not provided
            if inp:
                key = str(inp)
            else:
                key = None
                for k, j in self.jobs.items():
                    if j.worker_id == worker_id and j.stage == "INTEGRITY":
                        key = k
                        break
            
            if key and key in self.jobs:
                self.jobs[key].pct = pct
                self.jobs[key].speed = speed
    
    def stop_integrity(self, worker_id: int, inp: Optional[Path] = None):
        """Mark integrity check as complete - transition to WAITING_ENCODE stage."""
        with self.lock:
            if inp:
                key = str(inp)
                if key in self.jobs:
                    job = self.jobs[key]
                    job.integrity_elapsed = time.time() - job.integrity_start
                    job.stage = "WAITING_ENCODE"  # Passed integrity, wait for encode slot
                    job.pct = 0  # Reset progress for encode phase
            else:
                # Find by worker_id
                for j in self.jobs.values():
                    if j.worker_id == worker_id and j.stage == "INTEGRITY":
                        j.integrity_elapsed = time.time() - j.integrity_start
                        j.stage = "WAITING_ENCODE"
                        j.pct = 0
                        break
    
    def start_encode(self, worker_id: int, _filename: str, inp: Path, output_file: str = ""):
        """Start encoding for a file."""
        with self.lock:
            key = str(inp)
            if key in self.jobs:
                self.jobs[key].stage = "ENCODE"
                self.jobs[key].encode_start = time.time()
                self.jobs[key].worker_id = worker_id
                self.jobs[key].pct = 0
                self.jobs[key].speed = ""
                self.jobs[key].output_file = output_file
    
    def update_encode(self, worker_id: int, _stage: str, pct: int, _filename: str, speed: str = "", 
                      inp: Optional[Path] = None, out_ms: int = 0, dur_ms: int = 0):
        """Update encode progress."""
        with self.lock:
            if inp:
                key = str(inp)
            else:
                key = None
                for k, j in self.jobs.items():
                    if j.worker_id == worker_id and j.stage == "ENCODE":
                        key = k
                        break
            
            if key and key in self.jobs:
                self.jobs[key].pct = pct
                self.jobs[key].speed = speed
                if out_ms > 0:
                    self.jobs[key].out_ms = out_ms
                if dur_ms > 0:
                    self.jobs[key].dur_ms = dur_ms
    
    def stop_encode(self, worker_id: int, inp: Optional[Path] = None):
        """Mark encode as complete (not the final status)."""
        with self.lock:
            if inp:
                key = str(inp)
                if key in self.jobs:
                    self.jobs[key].encode_elapsed = time.time() - self.jobs[key].encode_start
            else:
                for j in self.jobs.values():
                    if j.worker_id == worker_id and j.stage == "ENCODE":
                        j.encode_elapsed = time.time() - j.encode_start
                        break
    
    def mark_done(self, inp: Path, _msg: str = "", final_path: Path = None, output_size: int = 0):
        """Mark a job as successfully completed."""
        with self.lock:
            key = str(inp)
            if key in self.jobs:
                job = self.jobs[key]
                job.stage = "DONE"
                job.total_elapsed = time.time() - job.start_time
                if job.encode_start > 0 and job.encode_elapsed == 0:
                    job.encode_elapsed = time.time() - job.encode_start
                self.ok += 1
                self.processed += 1
                
                # Record to history
                if HISTORY_DB and job.history_id:
                    try:
                        HISTORY_DB.record_finish(
                            job.history_id, final_path, "done",
                            encode_time=job.encode_elapsed,
                            integrity_time=job.integrity_elapsed,
                            output_size=output_size
                        )
                    except Exception:
                        pass
    
    def mark_failed(self, inp: Path, reason: str = ""):
        """Mark a job as failed."""
        with self.lock:
            key = str(inp)
            if key in self.jobs:
                job = self.jobs[key]
                job.stage = "FAILED"
                job.result_msg = reason
                job.total_elapsed = time.time() - job.start_time
                if job.encode_start > 0 and job.encode_elapsed == 0:
                    job.encode_elapsed = time.time() - job.encode_start
                if job.integrity_start > 0 and job.integrity_elapsed == 0:
                    job.integrity_elapsed = time.time() - job.integrity_start
                
                self.failed += 1
                self.processed += 1
                
                # Record to history
                if HISTORY_DB and job.history_id:
                    try:
                        status = "interrupted" if "interrupt" in reason.lower() else "failed"
                        HISTORY_DB.record_finish(
                            job.history_id, None, status,
                            encode_time=job.encode_elapsed,
                            integrity_time=job.integrity_elapsed,
                            error_msg=reason
                        )
                    except Exception:
                        pass
    
    def mark_skipped(self, inp: Path, reason: str = ""):
        """Mark a job as skipped."""
        with self.lock:
            key = str(inp)
            if key in self.jobs:
                job = self.jobs[key]
                job.stage = "SKIPPED"
                job.result_msg = reason
                job.total_elapsed = time.time() - job.start_time
                if job.integrity_start > 0 and job.integrity_elapsed == 0:
                    job.integrity_elapsed = time.time() - job.integrity_start
            else:
                # Job wasn't registered (pre-existing output) - create entry now
                job = JobStatus(inp=inp, stage="SKIPPED", result_msg=reason)
                self.jobs[key] = job
            
            self.skipped += 1
            self.processed += 1
            
            # Record to history (skipped files)
            if HISTORY_DB:
                try:
                    HISTORY_DB.record_skip(inp, reason, "")
                except Exception:
                    pass
    
    def log(self, msg: str):
        """Add a message to the log (for backwards compatibility)."""
        with self.lock:
            self.completed_log.append(msg)
    
    def inc_ok(self):
        pass  # Now handled by mark_done
    
    def inc_skipped(self):
        pass  # Now handled by mark_skipped
    
    def inc_failed(self):
        pass  # Now handled by mark_failed
    
    def get_stats(self) -> Tuple[int, int, int, int]:
        with self.lock:
            return (self.ok, self.skipped, self.failed, self.processed)


# -------------------- ffmpeg progress runner --------------------
_PROGRESS_KV = re.compile(r"^([a-zA-Z0-9_]+)=(.*)$")


def parse_speed_x(s: str) -> Optional[float]:
    m = re.match(r"^\s*([0-9]+(?:\.[0-9]+)?)x\s*$", s)
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def run_ffmpeg_with_progress_legacy(
    cmd: List[str],
    ui: LegacyProgressUI,
    stage: str,
    cur: int,
    total: int,
    base: str,
    dur_ms: int,
    log_path: Path,
    stop_event: Optional[threading.Event] = None,
) -> int:
    full = cmd[:] + ["-progress", "pipe:1", "-nostats", "-stats_period", str(CFG.stats_period)]
    dbg(f"ffmpeg: {shlex.join(full)}")

    start = time.time()
    last_ui = 0.0
    out_ms = 0
    out_ms_max = 0
    speed_str = ""
    speed_x = None

    with log_path.open("a", encoding="utf-8", errors="replace") as logf:
        proc = subprocess.Popen(
            full,
            stdout=subprocess.PIPE,
            stderr=logf,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )
        register_process(proc)

        def on_sigint(_sig, _frm):
            try:
                proc.send_signal(signal.SIGINT)
            except Exception:
                pass

        old = signal.signal(signal.SIGINT, on_sigint)

        try:
            while True:
                if stop_event and stop_event.is_set():
                    proc.terminate()
                    break
                    
                line = proc.stdout.readline() if proc.stdout else ""
                if line == "" and proc.poll() is not None:
                    break
                line = line.strip()
                if line:
                    m = _PROGRESS_KV.match(line)
                    if m:
                        k, v = m.group(1), m.group(2)
                        if k in ("out_time_ms", "out_time_us", "out_time"):
                            # Note: ffmpeg reports out_time_ms in microseconds despite the name!
                            if k == "out_time_ms":
                                try:
                                    out_ms = int(int(v) / 1000)
                                except Exception:
                                    pass
                            elif k == "out_time_us":
                                try:
                                    out_ms = int(int(v) / 1000)
                                except Exception:
                                    pass
                            else:
                                mm = re.match(r"^(\d+):(\d+):(\d+)(?:\.(\d+))?$", v)
                                if mm:
                                    h = int(mm.group(1)); mi = int(mm.group(2)); se = int(mm.group(3))
                                    frac = (mm.group(4) or "0")
                                    ms = int((frac + "000")[:3])
                                    out_ms = ((h * 3600 + mi * 60 + se) * 1000 + ms)

                            if out_ms < out_ms_max:
                                out_ms = out_ms_max
                            else:
                                out_ms_max = out_ms

                        elif k == "speed":
                            speed_str = v.strip()
                            sx = parse_speed_x(speed_str)
                            if sx and sx > 0:
                                speed_x = sx

                now = time.time()
                if (now - last_ui) * 1000.0 < CFG.ui_refresh_ms:
                    continue
                last_ui = now

                pct = 0
                eta = "ETA=--:--:--"
                sp = speed_str if speed_str else ""
                elapsed = fmt_hms(now - start)

                if dur_ms > 0 and out_ms_max > 0:
                    pct = int(min(100, max(0, (out_ms_max * 100) // dur_ms)))
                    left_ms = max(0, dur_ms - out_ms_max)

                    if speed_x and speed_x > 0:
                        eta_s = (left_ms / 1000.0) / speed_x
                        eta = f"ETA={fmt_hms(eta_s)}"
                    else:
                        elapsed_t = max(0.001, now - start)
                        rate = (out_ms_max / 1000.0) / elapsed_t
                        if rate > 0:
                            eta_s = (left_ms / 1000.0) / rate
                            eta = f"ETA={fmt_hms(eta_s)}"
                else:
                    eta = f"t={fmt_ms(out_ms_max)}"
                    pct = 0

                ui.render(UIState(stage=stage, pct=pct, cur=cur, total=total, base=base, eta=eta, speed=sp, elapsed=elapsed))

            rc = proc.wait()
            ui.endline()
            return rc

        finally:
            unregister_process(proc)
            signal.signal(signal.SIGINT, old)
            try:
                if proc.stdout:
                    proc.stdout.close()
            except Exception:
                pass


def run_ffmpeg_with_progress_rich(
    cmd: List[str],
    ui: RichProgressUI,
    worker_id: int,
    stage: str,
    base: str,
    dur_ms: int,
    log_path: Path,
    inp: Path,
    is_encode: bool = True,
    stop_event: Optional[threading.Event] = None,
) -> int:
    """Run ffmpeg with progress, updating the specified worker's progress bar."""
    full = cmd[:] + ["-progress", "pipe:1", "-nostats", "-stats_period", str(CFG.stats_period)]
    dbg(f"ffmpeg[worker={worker_id}]: {shlex.join(full)}")

    last_ui = 0.0
    out_ms = 0
    out_ms_max = 0
    speed_str = ""

    def update_fn(s: str, p: int, f: str, sp: str, cur_out_ms: int = 0, total_dur_ms: int = 0):
        if is_encode:
            ui.update_encode(worker_id, s, p, f, sp, inp=inp, out_ms=cur_out_ms, dur_ms=total_dur_ms)
        else:
            ui.update_integrity(worker_id, s, p, f, sp, inp=inp)

    with log_path.open("a", encoding="utf-8", errors="replace") as logf:
        proc = subprocess.Popen(
            full,
            stdout=subprocess.PIPE,
            stderr=logf,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )
        register_process(proc)

        try:
            while True:
                if stop_event and stop_event.is_set():
                    proc.terminate()
                    break
                    
                line = proc.stdout.readline() if proc.stdout else ""
                if line == "" and proc.poll() is not None:
                    break
                line = line.strip()
                if line:
                    m = _PROGRESS_KV.match(line)
                    if m:
                        k, v = m.group(1), m.group(2)
                        if k in ("out_time_ms", "out_time_us", "out_time"):
                            # Note: ffmpeg reports out_time_ms in microseconds despite the name!
                            if k == "out_time_ms":
                                try:
                                    out_ms = int(int(v) / 1000)
                                except Exception:
                                    pass
                            elif k == "out_time_us":
                                try:
                                    out_ms = int(int(v) / 1000)
                                except Exception:
                                    pass
                            else:
                                mm = re.match(r"^(\d+):(\d+):(\d+)(?:\.(\d+))?$", v)
                                if mm:
                                    h = int(mm.group(1)); mi = int(mm.group(2)); se = int(mm.group(3))
                                    frac = (mm.group(4) or "0")
                                    ms = int((frac + "000")[:3])
                                    out_ms = ((h * 3600 + mi * 60 + se) * 1000 + ms)

                            if out_ms < out_ms_max:
                                out_ms = out_ms_max
                            else:
                                out_ms_max = out_ms

                        elif k == "speed":
                            speed_str = v.strip()

                now = time.time()
                if (now - last_ui) * 1000.0 < CFG.ui_refresh_ms:
                    continue
                last_ui = now

                pct = 0
                if dur_ms > 0 and out_ms_max > 0:
                    pct = int(min(100, max(0, (out_ms_max * 100) // dur_ms)))
                
                # Debug: log progress values
                if CFG.debug:
                    dbg(f"PROGRESS: out_ms={out_ms_max} dur_ms={dur_ms} pct={pct} speed={speed_str}")

                update_fn(stage, pct, base, speed_str, out_ms_max, dur_ms)

            rc = proc.wait()
            return rc

        finally:
            unregister_process(proc)
            try:
                if proc.stdout:
                    proc.stdout.close()
            except Exception:
                pass


# -------------------- INTEGRITY CHECK --------------------
def integrity_check_legacy(inp: Path, ui: LegacyProgressUI, cur: int, total: int, base: str, log_path: Path) -> bool:
    if not CFG.integrity_check:
        dbg("integrity: disabled")
        return True

    dbg(f"integrity: enabled, stable_wait={CFG.stable_wait}s, deep_check={CFG.deep_check}")
    s1 = file_size(inp)
    if s1 < 1024 * 1024:
        return False

    if CFG.progress and sys.stdout.isatty():
        for i in range(CFG.stable_wait):
            pct = int((i * 100) / max(1, CFG.stable_wait))
            elapsed = fmt_hms(i)
            ui.render(UIState(stage="INTEGRITY", pct=pct, cur=cur, total=total, base=base, eta=f"wait={CFG.stable_wait - i}s", speed="", elapsed=elapsed))
            time.sleep(1)
        ui.endline()
    else:
        time.sleep(CFG.stable_wait)

    s2 = file_size(inp)
    if s1 != s2:
        return False
    dbg(f"integrity: size stable ({s1} bytes)")

    if not run_quiet(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(inp)], timeout=8.0):
        return False
    dbg("integrity: ffprobe OK")

    if CFG.deep_check:
        dbg("integrity: deep_check enabled")
        dur_ms = probe_duration_ms(inp)
        if dur_ms <= 0:
            dur_ms = 0
        with log_path.open("a", encoding="utf-8", errors="replace") as lf:
            lf.write("DEEP_CHECK: decode video stream\n")

        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(inp), "-map", "0:v:0", "-f", "null", "-"]
        rc = run_ffmpeg_with_progress_legacy(cmd, ui, "DEEP_CHECK", cur, total, base, dur_ms, log_path)
        if rc != 0:
            return False
        dbg("integrity: decode check OK")

    return True


def integrity_check_rich(
    inp: Path, 
    ui: RichProgressUI,
    worker_id: int,
    base: str, 
    log_path: Path,
    stop_event: Optional[threading.Event] = None
) -> Tuple[bool, float]:
    """Integrity check with Rich progress UI. Returns (success, elapsed_seconds)."""
    start_time = time.time()
    
    if not CFG.integrity_check:
        dbg("integrity: disabled")
        return True, 0

    dbg(f"integrity[worker={worker_id}]: enabled, stable_wait={CFG.stable_wait}s, deep_check={CFG.deep_check}")
    s1 = file_size(inp)
    if s1 < 1024 * 1024:
        return False, time.time() - start_time

    ui.start_integrity(worker_id, base, inp)
    
    # Stable wait with progress
    for i in range(CFG.stable_wait):
        if stop_event and stop_event.is_set():
            ui.stop_integrity(worker_id, inp=inp)
            return False, time.time() - start_time
        pct = int(((i + 1) * 100) / max(1, CFG.stable_wait))
        ui.update_integrity(worker_id, "STABLE_WAIT", pct, base, f"wait={CFG.stable_wait - i - 1}s", inp=inp)
        time.sleep(1)

    s2 = file_size(inp)
    if s1 != s2:
        ui.stop_integrity(worker_id, inp=inp)
        return False, time.time() - start_time
    dbg(f"integrity[worker={worker_id}]: size stable ({s1} bytes)")

    ui.update_integrity(worker_id, "FFPROBE", 50, base, "checking...", inp=inp)
    if not run_quiet(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(inp)], timeout=8.0):
        ui.stop_integrity(worker_id, inp=inp)
        return False, time.time() - start_time
    dbg(f"integrity[worker={worker_id}]: ffprobe OK")
    
    # Update to 100% when ffprobe succeeds (if no deep check)
    if not CFG.deep_check:
        ui.update_integrity(worker_id, "FFPROBE", 100, base, "OK", inp=inp)

    if CFG.deep_check:
        dbg(f"integrity[worker={worker_id}]: deep_check enabled")
        dur_ms = probe_duration_ms(inp)
        if dur_ms <= 0:
            dur_ms = 0
        with log_path.open("a", encoding="utf-8", errors="replace") as lf:
            lf.write("DEEP_CHECK: decode video stream\n")

        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(inp), "-map", "0:v:0", "-f", "null", "-"]
        rc = run_ffmpeg_with_progress_rich(cmd, ui, worker_id, "DEEP_CHECK", base, dur_ms, log_path, inp, is_encode=False, stop_event=stop_event)
        if rc != 0:
            ui.stop_integrity(worker_id, inp=inp)
            return False, time.time() - start_time
        dbg(f"integrity[worker={worker_id}]: decode check OK")

    elapsed = time.time() - start_time
    ui.stop_integrity(worker_id, inp=inp)
    return True, elapsed


# -------------------- BUILD FFMPEG CMD --------------------
def build_transcode_cmd(inp: Path, decision: Decision, backend: str, tmp_out: Path, log_path: Path) -> Tuple[List[str], str]:
    ext = CFG.container
    if ext not in ("mkv", "mp4"):
        raise RuntimeError("container must be mkv or mp4")

    args = ["ffmpeg", "-hide_banner", "-y"]

    if ext == "mkv":
        args += ["-f", "matroska"]
    else:
        args += ["-f", "mp4", "-movflags", "+faststart"]

    if decision.add_silence:
        args += ["-i", str(inp), "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
        args += ["-map", "0:v:0", "-map", "1:a:0", "-map", "0:s?", "-shortest"]
    else:
        args += ["-i", str(inp), "-map", "0:v:0"]
        if decision.aidx >= 0:
            args += ["-map", f"0:{decision.aidx}"]
        args += ["-map", "0:s?"]

    if not decision.need_v:
        args += ["-c:v", "copy"]
    else:
        args += video_args_for(backend)

    if decision.add_silence:
        args += ["-c:a", "aac", "-b:a", CFG.abr, "-ac", "2"]
    else:
        if decision.aidx >= 0:
            if not decision.need_a:
                args += ["-c:a", "copy"]
            else:
                args += ["-c:a", "aac", "-b:a", CFG.abr]
                if not CFG.keep_surround:
                    args += ["-ac", "2"]

    if ext == "mkv":
        args += ["-c:s", "copy"]
    else:
        args += ["-c:s", "mov_text"]

    args += ["-map_metadata", "0", "-map_chapters", "0", "-max_muxing_queue_size", "2048"]
    args += [str(tmp_out)]

    stage = "TRANSCODE"
    if (not decision.need_v) and decision.need_a:
        stage = "AUDIO"
    elif (not decision.need_v) and (not decision.need_a):
        stage = "REMUX"

    with log_path.open("a", encoding="utf-8", errors="replace") as lf:
        lf.write("CMD: " + shlex.join(args) + "\n")

    return args, stage


# -------------------- COLLECT TARGETS --------------------
def collect_targets(root: Path, single: Optional[Path]) -> Tuple[List[Path], List[Tuple[Path, str]]]:
    """
    Collect target files for processing.
    Returns: (targets, ignored) where ignored is list of (path, reason)
    """
    targets: List[Path] = []
    ignored: List[Tuple[Path, str]] = []
    
    if single is not None:
        p = single.resolve()
        if not p.exists() or not p.is_file():
            raise RuntimeError(f"file not found: {p}")
        if p.suffix.lower() != ".mkv":
            raise RuntimeError("only .mkv supported")
        if p.name.startswith(".") or is_our_output_or_tmp(p.name):
            return [], []
        ignore_reason = should_ignore_file(p)
        if ignore_reason:
            ignored.append((p, ignore_reason))
            return [], ignored
        targets.append(p)
        return targets, ignored

    if CFG.recursive:
        for dirpath, dirnames, filenames in os.walk(root):
            d = Path(dirpath)
            # Skip log directories and ignored folders
            new_dirnames = []
            for dn in dirnames:
                # Skip hidden directories and mkv2cast related folders
                if dn.startswith("."):
                    continue
                # Check if this directory should be ignored
                dir_path = d / dn
                ignore_reason = should_ignore_file(dir_path)
                if ignore_reason:
                    dbg(f"Ignoring folder: {dir_path} ({ignore_reason})")
                    continue
                new_dirnames.append(dn)
            dirnames[:] = new_dirnames
            
            for fn in filenames:
                if not fn.lower().endswith(".mkv"):
                    continue
                if fn.startswith("."):
                    continue
                if is_our_output_or_tmp(fn):
                    continue
                p = d / fn
                ignore_reason = should_ignore_file(p)
                if ignore_reason:
                    ignored.append((p, ignore_reason))
                    continue
                targets.append(p)
    else:
        for p in root.glob("*.mkv"):
            if not p.is_file():
                continue
            if is_our_output_or_tmp(p.name):
                continue
            ignore_reason = should_ignore_file(p)
            if ignore_reason:
                ignored.append((p, ignore_reason))
                continue
            targets.append(p)

    targets.sort()
    return targets, ignored


# -------------------- PIPELINE WORKERS --------------------
@dataclass
class EncodeJob:
    """Job ready for encoding."""
    inp: Path
    decision: Decision
    log_path: Path
    final: Path
    tmp: Path
    dur_ms: int
    stage: str
    integrity_time: float = 0


class PipelineOrchestrator:
    """Orchestrates parallel integrity check and encoding with multiple workers."""
    
    def __init__(self, targets: List[Path], backend: str, ui: RichProgressUI, 
                 encode_workers: int, integrity_workers: int):
        self.targets = targets
        self.backend = backend
        self.ui = ui
        self.encode_workers_count = encode_workers
        self.integrity_workers_count = integrity_workers
        
        # Queues
        self.integrity_queue: Queue[Optional[Path]] = Queue()
        self.encode_queue: Queue[Optional[EncodeJob]] = Queue()
        
        # Control
        self.stop_event = threading.Event()
        self.interrupted = False
        
        # Track active sentinels
        self.integrity_sentinels_remaining = integrity_workers
        self.integrity_sentinels_lock = threading.Lock()
        
        # Register all jobs and fill integrity queue
        for t in targets:
            self.ui.register_job(t, backend=self.backend)
            self.integrity_queue.put(t)
        
        # Add one sentinel per integrity worker
        for _ in range(integrity_workers):
            self.integrity_queue.put(None)
    
    def integrity_worker(self, worker_id: int):
        """Worker that performs integrity checks and prepares encode jobs."""
        dbg(f"integrity_worker[{worker_id}] started")
        
        while not self.stop_event.is_set():
            try:
                inp = self.integrity_queue.get(timeout=0.5)
            except Empty:
                continue
            
            if inp is None:
                # Sentinel - check if we're the last one
                with self.integrity_sentinels_lock:
                    self.integrity_sentinels_remaining -= 1
                    if self.integrity_sentinels_remaining == 0:
                        # Last integrity worker - send sentinels to encode workers
                        for _ in range(self.encode_workers_count):
                            self.encode_queue.put(None)
                dbg(f"integrity_worker[{worker_id}] finished")
                break
            
            base = inp.name
            
            # Check if output already exists
            if output_exists_for_input(inp):
                self.ui.mark_skipped(inp, "output exists")
                dbg(f"SKIP output existe déjà: {inp}")
                continue
            
            log_path = get_log_path(inp)
            
            with log_path.open("a", encoding="utf-8", errors="replace") as lf:
                lf.write(f"\n==> {inp} [integrity_worker={worker_id}]\n")
            
            try:
                success, integrity_time = integrity_check_rich(inp, self.ui, worker_id, base, log_path, self.stop_event)
                if not success:
                    self.ui.mark_skipped(inp, "integrity failed")
                    continue
            except Exception as e:
                self.ui.mark_failed(inp, f"integrity error: {e}")
                continue
            
            try:
                d = decide_for(inp)
            except Exception as e:
                self.ui.mark_failed(inp, f"ffprobe/decision error: {e}")
                continue
            
            # Check if compatible and should skip
            if (not d.need_v) and (not d.need_a) and CFG.skip_when_ok:
                self.ui.mark_skipped(inp, "compatible")
                continue
            
            stem = inp.stem
            tag = ""
            if d.need_v:
                tag += ".h264"
            if d.need_a:
                tag += ".aac"
            if not tag:
                tag = ".remux"
            
            final = inp.parent / f"{stem}{tag}{CFG.suffix}.{CFG.container}"
            if final.exists():
                self.ui.mark_skipped(inp, "output exists")
                dbg(f"SKIP output existe déjà: {final}")
                continue
            
            tmp = get_tmp_path(inp, worker_id, tag)
            if tmp.exists():
                self.ui.mark_skipped(inp, "tmp exists in cache")
                dbg(f"SKIP tmp existe: {tmp}")
                continue
            
            cmd, stage = build_transcode_cmd(inp, d, self.backend, tmp, log_path)
            dur_ms = probe_duration_ms(inp)
            
            if CFG.dryrun:
                self.ui.log(f"[cyan]DRYRUN[/cyan]: {shlex.join(cmd)}")
                self.ui.mark_skipped(inp, "dryrun")
                continue
            
            job = EncodeJob(
                inp=inp,
                decision=d,
                log_path=log_path,
                final=final,
                tmp=tmp,
                dur_ms=dur_ms,
                stage=stage,
                integrity_time=integrity_time
            )
            self.encode_queue.put(job)
    
    def encode_worker(self, worker_id: int):
        """Worker that performs encoding."""
        dbg(f"encode_worker[{worker_id}] started")
        
        while not self.stop_event.is_set():
            try:
                job = self.encode_queue.get(timeout=0.5)
            except Empty:
                continue
            
            if job is None:
                dbg(f"encode_worker[{worker_id}] finished")
                break
            
            base = job.inp.name
            
            self.ui.start_encode(worker_id, base, job.inp, job.final.name)
            
            cmd, _ = build_transcode_cmd(job.inp, job.decision, self.backend, job.tmp, job.log_path)
            
            try:
                rc = run_ffmpeg_with_progress_rich(
                    cmd, self.ui, worker_id, job.stage, base, job.dur_ms, 
                    job.log_path, job.inp, is_encode=True, stop_event=self.stop_event
                )
            except Exception as e:
                try:
                    job.tmp.unlink(missing_ok=True)
                except Exception:
                    pass
                self.ui.mark_failed(job.inp, f"encode error: {e}")
                continue
            
            if rc == 0:
                try:
                    os.replace(job.tmp, job.final)
                    output_size = job.final.stat().st_size if job.final.exists() else 0
                    self.ui.mark_done(job.inp, final_path=job.final, output_size=output_size)
                except Exception as e:
                    try:
                        job.tmp.unlink(missing_ok=True)
                    except Exception:
                        pass
                    self.ui.mark_failed(job.inp, f"move error: {e}")
            else:
                try:
                    job.tmp.unlink(missing_ok=True)
                except Exception:
                    pass
                # Distinguish between interruption and real failure
                if self.stop_event.is_set():
                    self.ui.mark_failed(job.inp, "interrupted")
                else:
                    self.ui.mark_failed(job.inp, f"rc={rc}")
    
    def run(self) -> Tuple[int, int, int, bool]:
        """Run the pipeline and return (ok, skipped, failed, interrupted)."""
        # Create worker threads
        integrity_threads = []
        for i in range(self.integrity_workers_count):
            t = threading.Thread(target=self.integrity_worker, args=(i,), name=f"integrity_worker_{i}")
            integrity_threads.append(t)
        
        encode_threads = []
        for i in range(self.encode_workers_count):
            t = threading.Thread(target=self.encode_worker, args=(i,), name=f"encode_worker_{i}")
            encode_threads.append(t)
        
        def on_sigint(_sig, _frm):
            self.interrupted = True
            self.stop_event.set()
            # Terminate all running ffmpeg processes immediately
            terminate_all_processes()
        
        old_handler = signal.signal(signal.SIGINT, on_sigint)
        
        try:
            # Start all threads
            for t in integrity_threads:
                t.start()
            for t in encode_threads:
                t.start()
            
            # Wait for all threads
            for t in integrity_threads:
                t.join()
            for t in encode_threads:
                t.join()
            
        finally:
            signal.signal(signal.SIGINT, old_handler)
            # Ensure all processes are cleaned up
            terminate_all_processes()
        
        # Get final stats from UI
        ok, skipped, failed, _ = self.ui.get_stats()
        return (ok, skipped, failed, self.interrupted)


# -------------------- MAIN --------------------
def main_legacy(single: Optional[Path]) -> int:
    """Legacy sequential mode."""
    root = Path(".").resolve()

    backend = pick_backend()
    print(f"Backend sélectionné: {backend}", flush=True)
    dbg(f"config: recursive={CFG.recursive} skip_when_ok={CFG.skip_when_ok} integrity_check={CFG.integrity_check} deep_check={CFG.deep_check} container={CFG.container} suffix={CFG.suffix}")

    ui = LegacyProgressUI()

    targets, ignored_files = collect_targets(root, single)
    
    # Show ignored files
    if ignored_files and CFG.debug:
        for p, reason in ignored_files:
            dbg(f"IGNORED: {p.name} ({reason})")
    
    if not targets:
        print("Aucun .mkv à traiter.", flush=True)
        if ignored_files:
            print(f"({len(ignored_files)} fichier(s) ignoré(s))", flush=True)
        return 0

    total = len(targets)
    start_total = time.time()

    ok = 0
    skipped = 0
    failed = 0
    interrupted = 0

    for i, inp in enumerate(targets, start=1):
        base = inp.name

        if output_exists_for_input(inp):
            skipped += 1
            dbg(f"SKIP output existe déjà: {inp}")
            continue

        log_path = get_log_path(inp)

        per_start = time.time()
        ui.log(f"==> {inp}")
        with log_path.open("a", encoding="utf-8", errors="replace") as lf:
            lf.write("\n==> " + str(inp) + "\n")

        try:
            if not integrity_check_legacy(inp, ui, i, total, base, log_path):
                skipped += 1
                ui.log(f"   SKIP: integrity check failed (voir {log_path})")
                ui.log(f"   time: {fmt_hms(time.time() - per_start)} (skipped)")
                continue
        except KeyboardInterrupt:
            interrupted += 1
            print("\nINTERRUPT: reçu SIGINT", flush=True)
            return 130

        try:
            d = decide_for(inp)
        except Exception as e:
            failed += 1
            ui.log(f"   FAILED: ffprobe/decision error: {e} (voir {log_path})")
            continue

        if CFG.debug:
            ui.log(f"   detect: fmt={d.format_name} v={d.vcodec} pix={d.vpix} bit={d.vbit} hdr={int(d.vhdr)} prof={d.vprof} level={d.vlevel} | a={d.acodec} ch={d.ach} idx={d.aidx}")
            ui.log(f"   decision: NEED_V={int(d.need_v)} NEED_A={int(d.need_a)} | {d.reason_v}")

        if (not d.need_v) and (not d.need_a) and CFG.skip_when_ok:
            skipped += 1
            ui.log("   OK: compatible (skip)")
            ui.log(f"   time: {fmt_hms(time.time() - per_start)} (skipped)")
            continue

        stem = inp.stem
        tag = ""
        if d.need_v:
            tag += ".h264"
        if d.need_a:
            tag += ".aac"
        if not tag:
            tag = ".remux"

        final = inp.parent / f"{stem}{tag}{CFG.suffix}.{CFG.container}"
        if final.exists():
            skipped += 1
            dbg(f"SKIP output existe déjà: {final}")
            continue

        tmp = get_tmp_path(inp, 0, tag)  # worker_id=0 for legacy mode
        if tmp.exists():
            skipped += 1
            dbg(f"SKIP tmp existe: {tmp}")
            continue

        ui.log(f"   -> {final}")

        cmd, stage = build_transcode_cmd(inp, d, backend, tmp, log_path)

        if CFG.dryrun:
            ui.log(f"DRYRUN: {shlex.join(cmd)}")
            skipped += 1
            continue

        dur_ms = probe_duration_ms(inp)
        if dur_ms <= 0:
            dur_ms = 0

        try:
            rc = run_ffmpeg_with_progress_legacy(cmd, ui, stage, i, total, base, dur_ms, log_path)
        except KeyboardInterrupt:
            interrupted += 1
            try:
                if tmp.exists():
                    tmp.unlink(missing_ok=True)
            except Exception:
                pass
            print("\nINTERRUPT: reçu SIGINT", flush=True)
            return 130

        if rc == 0:
            try:
                os.replace(tmp, final)
            except Exception as e:
                failed += 1
                try:
                    tmp.unlink(missing_ok=True)
                except Exception:
                    pass
                ui.log(f"   FAILED: atomic move error: {e} (voir {log_path})")
                continue

            ok += 1
            ui.log(f"   DONE in {fmt_hms(time.time() - per_start)}")
        else:
            failed += 1
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            ui.log(f"   FAILED (rc={rc}) (voir {log_path})")

    total_dur = time.time() - start_total
    print("=== Résumé ===", flush=True)
    print(f"Total fichiers vus: {total}", flush=True)
    print(f"Transcodés OK     : {ok}", flush=True)
    print(f"Skippés           : {skipped}", flush=True)
    print(f"Échecs            : {failed}", flush=True)
    print(f"Interrompus       : {interrupted}", flush=True)
    print(f"Temps total       : {fmt_hms(total_dur)}", flush=True)
    return 0 if failed == 0 else 2


def _reset_terminal():
    """Reset terminal to normal mode after Rich display."""
    # Show cursor and reset attributes
    sys.stdout.write("\033[?25h")  # Show cursor
    sys.stdout.write("\033[0m")    # Reset all attributes
    sys.stdout.flush()
    
    # Try to reset terminal line discipline
    try:
        import termios
        fd = sys.stdin.fileno()
        # Get current settings and ensure ICANON and ECHO are enabled
        try:
            attrs = termios.tcgetattr(fd)
            attrs[3] |= termios.ICANON | termios.ECHO  # Enable canonical mode and echo
            termios.tcsetattr(fd, termios.TCSANOW, attrs)
        except (termios.error, OSError):
            pass
    except (ImportError, ValueError):
        pass


def main_pipeline(single: Optional[Path]) -> int:
    """Pipeline mode with parallel integrity check and encoding."""
    root = Path(".").resolve()

    backend = pick_backend()
    
    # Determine worker counts
    if CFG.encode_workers == 0 or CFG.integrity_workers == 0:
        auto_encode, auto_integrity = auto_detect_workers(backend)
        encode_workers = CFG.encode_workers if CFG.encode_workers > 0 else auto_encode
        integrity_workers = CFG.integrity_workers if CFG.integrity_workers > 0 else auto_integrity
    else:
        encode_workers = CFG.encode_workers
        integrity_workers = CFG.integrity_workers
    
    console = Console()
    mode_str = "[green]Pipeline[/green]"
    console.print(f"[bold]mkv2cast[/bold] - Backend: [cyan]{backend}[/cyan] - Mode: {mode_str}")
    console.print(f"Workers: [cyan]{encode_workers}[/cyan] encode, [cyan]{integrity_workers}[/cyan] integrity")
    console.print("─" * 60)
    
    dbg(f"config: recursive={CFG.recursive} skip_when_ok={CFG.skip_when_ok} integrity_check={CFG.integrity_check} deep_check={CFG.deep_check} container={CFG.container} suffix={CFG.suffix}")
    dbg(f"workers: encode={encode_workers} integrity={integrity_workers}")
    if CFG.ignore_patterns:
        dbg(f"ignore_patterns: {CFG.ignore_patterns}")
    if CFG.ignore_paths:
        dbg(f"ignore_paths: {CFG.ignore_paths}")

    targets, ignored_files = collect_targets(root, single)
    
    # Show ignored files
    for p, reason in ignored_files:
        console.print(f"[dim]⊘ IGNORE {shorten(p.name, 50)} ({reason})[/dim]")
    
    if not targets:
        console.print("[yellow]Aucun .mkv à traiter.[/yellow]")
        if ignored_files:
            console.print(f"[dim]({len(ignored_files)} fichier(s) ignoré(s))[/dim]")
        return 0

    total = len(targets)
    console.print(f"[bold]Fichiers à traiter:[/bold] {total}")
    if ignored_files:
        console.print(f"[dim]({len(ignored_files)} fichier(s) ignoré(s))[/dim]")
    console.print("─" * 60)
    
    start_total = time.time()

    ui = RichProgressUI(total, encode_workers, integrity_workers)
    ui.start()
    
    try:
        orchestrator = PipelineOrchestrator(targets, backend, ui, encode_workers, integrity_workers)
        ok, skipped, failed, interrupted = orchestrator.run()
    finally:
        ui.stop()
        _reset_terminal()  # Ensure terminal is restored
    
    total_dur = time.time() - start_total
    
    console.print()
    console.print("─" * 60)
    console.print("[bold]=== Résumé ===[/bold]")
    
    table = Table(show_header=False, box=None)
    table.add_column("Label", style="bold")
    table.add_column("Value", justify="right")
    
    table.add_row("Total fichiers vus", str(total))
    table.add_row("Transcodés OK", f"[green]{ok}[/green]")
    table.add_row("Skippés", f"[yellow]{skipped}[/yellow]")
    table.add_row("Échecs", f"[red]{failed}[/red]" if failed > 0 else "0")
    table.add_row("Interrompus", "1" if interrupted else "0")
    table.add_row("Temps total", fmt_hms(total_dur))
    
    console.print(table)
    
    _reset_terminal()  # Final reset before exit
    
    if interrupted:
        return 130
    return 0 if failed == 0 else 2


def check_requirements() -> int:
    """Check system requirements and Python dependencies. Returns exit code."""
    print(f"mkv2cast v{__version__} - Requirements Check")
    print("=" * 50)
    print()
    
    all_ok = True
    
    # System requirements (mandatory)
    print("System requirements (mandatory):")
    print("-" * 40)
    
    # Check ffmpeg
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            version_line = result.stdout.split('\n')[0] if result.stdout else "unknown"
            print(f"  ✓ ffmpeg: {version_line}")
        else:
            print("  ✗ ffmpeg: installed but returned error")
            all_ok = False
    except FileNotFoundError:
        print("  ✗ ffmpeg: NOT FOUND - Install with: sudo pacman -S ffmpeg (Arch) or sudo apt install ffmpeg (Debian)")
        all_ok = False
    except Exception as e:
        print(f"  ✗ ffmpeg: error checking - {e}")
        all_ok = False
    
    # Check ffprobe
    try:
        result = subprocess.run(["ffprobe", "-version"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            version_line = result.stdout.split('\n')[0] if result.stdout else "unknown"
            print(f"  ✓ ffprobe: {version_line}")
        else:
            print("  ✗ ffprobe: installed but returned error")
            all_ok = False
    except FileNotFoundError:
        print("  ✗ ffprobe: NOT FOUND - Usually included with ffmpeg")
        all_ok = False
    except Exception as e:
        print(f"  ✗ ffprobe: error checking - {e}")
        all_ok = False
    
    # Check Python version
    py_version = sys.version_info
    if py_version >= (3, 8):
        print(f"  ✓ Python: {py_version.major}.{py_version.minor}.{py_version.micro}")
    else:
        print(f"  ✗ Python: {py_version.major}.{py_version.minor}.{py_version.micro} (need 3.8+)")
        all_ok = False
    
    print()
    
    # Python dependencies (optional enhancements)
    print("Python dependencies (optional enhancements):")
    print("-" * 40)
    
    # Check rich
    if RICH_AVAILABLE:
        try:
            from importlib.metadata import version as pkg_version
            rich_ver = pkg_version("rich")
            print(f"  ✓ rich: {rich_ver} - Enhanced progress UI enabled")
        except Exception:
            print("  ✓ rich: installed - Enhanced progress UI enabled")
    else:
        print("  ○ rich: NOT INSTALLED - Install with: pip install rich")
        print("          (Enables beautiful progress bars and tables)")
    
    # Check TOML support
    if TOML_AVAILABLE:
        if py_version >= (3, 11):
            print("  ✓ tomllib: built-in (Python 3.11+) - TOML config enabled")
        else:
            try:
                from importlib.metadata import version as pkg_version
                tomli_ver = pkg_version("tomli")
                print(f"  ✓ tomli: {tomli_ver} - TOML config enabled")
            except Exception:
                print("  ✓ tomli: installed - TOML config enabled")
    else:
        print("  ○ tomli: NOT INSTALLED - Install with: pip install tomli")
        print("          (Enables TOML config files, falls back to INI)")
    
    # Check SQLite
    if SQLITE_AVAILABLE:
        print(f"  ✓ sqlite3: built-in - History database enabled")
    else:
        print("  ○ sqlite3: NOT AVAILABLE - History uses JSONL fallback")
    
    print()
    
    # Hardware acceleration
    print("Hardware acceleration:")
    print("-" * 40)
    
    # Check VAAPI device
    vaapi_device = Path("/dev/dri/renderD128")
    if vaapi_device.exists():
        print(f"  ✓ VAAPI device: {vaapi_device} exists")
        # Test VAAPI encoder
        if have_encoder("h264_vaapi"):
            print("  ✓ h264_vaapi encoder: available")
        else:
            print("  ○ h264_vaapi encoder: not available")
    else:
        print(f"  ○ VAAPI device: {vaapi_device} not found")
    
    # Check QSV encoder
    if have_encoder("h264_qsv"):
        print("  ✓ h264_qsv encoder: available (Intel Quick Sync)")
    else:
        print("  ○ h264_qsv encoder: not available")
    
    # Test backends
    print()
    print("Backend tests:")
    print("-" * 40)
    
    if test_vaapi():
        print("  ✓ VAAPI encoding: working")
    else:
        print("  ○ VAAPI encoding: test failed or unavailable")
    
    if test_qsv():
        print("  ✓ QSV encoding: working")
    else:
        print("  ○ QSV encoding: test failed or unavailable")
    
    print("  ✓ CPU encoding: always available (libx264)")
    
    print()
    print("=" * 50)
    
    if all_ok:
        print("✓ All mandatory requirements satisfied!")
        return 0
    else:
        print("✗ Some mandatory requirements are missing.")
        return 1


def handle_utility_commands(args: argparse.Namespace) -> Optional[int]:
    """Handle utility commands that exit immediately. Returns exit code or None to continue."""
    global APP_DIRS, HISTORY_DB
    
    # Check requirements (before initializing directories)
    if args.check_requirements:
        return check_requirements()
    
    # Initialize directories first
    APP_DIRS = get_app_dirs()
    
    # Show directories
    if args.show_dirs:
        print("mkv2cast directories:")
        print()
        print("User directories (XDG):")
        print(f"  Config:  {APP_DIRS['config']}")
        print(f"  State:   {APP_DIRS['state']}")
        print(f"  Logs:    {APP_DIRS['logs']}")
        print(f"  Cache:   {APP_DIRS['cache']}")
        print(f"  Tmp:     {APP_DIRS['tmp']}")
        print()
        
        # System config
        system_config_dir = Path("/etc/mkv2cast")
        system_toml = system_config_dir / "config.toml"
        system_ini = system_config_dir / "config.ini"
        
        print("System directories:")
        if system_toml.exists():
            print(f"  Config:  {system_toml} (active)")
        elif system_ini.exists():
            print(f"  Config:  {system_ini} (active)")
        else:
            print(f"  Config:  {system_config_dir} (not configured)")
        print()
        
        # Active config files
        print("Active configuration:")
        config_toml = APP_DIRS['config'] / "config.toml"
        config_ini = APP_DIRS['config'] / "config.ini"
        
        if system_toml.exists() or system_ini.exists():
            sys_file = system_toml if system_toml.exists() else system_ini
            print(f"  System:  {sys_file}")
        
        if config_toml.exists():
            print(f"  User:    {config_toml} (overrides system)")
        elif config_ini.exists():
            print(f"  User:    {config_ini} (overrides system)")
        else:
            print("  User:    (none, will be created on first run)")
        
        print()
        print("Features:")
        print(f"  TOML support:   {'yes' if TOML_AVAILABLE else 'no (using INI fallback)'}")
        print(f"  SQLite support: {'yes' if SQLITE_AVAILABLE else 'no (using JSONL fallback)'}")
        return 0
    
    # Clean tmp
    if args.clean_tmp:
        if is_running_as_root():
            # System-wide cleanup: clean all users
            print("Running as root: cleaning temp files for all users...")
            results = cleanup_all_users_tmp(max_age_hours=0, verbose=True)
            total = sum(results.values())
            for username, count in sorted(results.items()):
                if count > 0:
                    print(f"  {username}: {count} file(s) removed")
            print(f"Total: {total} orphaned temp file(s) removed")
        else:
            # User-space cleanup
            removed = cleanup_orphaned_tmp(max_age_hours=0)  # Remove all
            print(f"Removed {removed} orphaned temp file(s) from {APP_DIRS['tmp']}")
        return 0
    
    # Clean logs
    if args.clean_logs is not None:
        if is_running_as_root():
            # System-wide cleanup: clean all users
            print(f"Running as root: cleaning logs older than {args.clean_logs} days for all users...")
            results = cleanup_all_users_logs(args.clean_logs, verbose=True)
            total = sum(results.values())
            for username, count in sorted(results.items()):
                if count > 0:
                    print(f"  {username}: {count} file(s) removed")
            print(f"Total: {total} log file(s) removed")
        else:
            # User-space cleanup
            removed = cleanup_old_logs(args.clean_logs)
            print(f"Removed {removed} log file(s) older than {args.clean_logs} days from {APP_DIRS['logs']}")
        return 0
    
    # Initialize history DB for history commands
    HISTORY_DB = HistoryDB(APP_DIRS['state'])
    
    # Clean history
    if args.clean_history is not None:
        removed = HISTORY_DB.clean_old(args.clean_history)
        print(f"Removed {removed} history entry/entries older than {args.clean_history} days")
        return 0
    
    # Show history
    if args.history is not None:
        try:
            # Validate and cap the limit
            limit = min(max(1, args.history), 1000)
            recent = HISTORY_DB.get_recent(limit)
        except Exception as e:
            if os.environ.get("MKV2CAST_DEBUG"):
                print(f"Error reading history: {e}", file=sys.stderr)
            print("No conversion history found (error reading database).")
            return 1
        
        if not recent:
            print("No conversion history found.")
            return 0
        
        # Get terminal width for proper formatting
        term_cols = shutil.get_terminal_size((80, 20)).columns
        
        print(f"Recent conversions (last {len(recent)}):")
        print("-" * min(80, term_cols - 1))
        
        for entry in recent:
            try:
                inp = entry.get("input_path") or entry.get("input", "?")
                inp_name = Path(inp).name if inp else "?"
                status = entry.get("status", "?")
                started = entry.get("started_at") or entry.get("started", "?")
                if started and len(started) > 19:
                    started = started[:19]  # Trim microseconds
                
                # Status emoji
                status_icon = {"done": "✓", "failed": "✗", "skipped": "⊘", "running": "⚙"}.get(status, "?")
                
                # Duration if available
                encode_time = entry.get("encode_time_s") or entry.get("encode_time", 0)
                try:
                    time_str = f" ({float(encode_time):.1f}s)" if encode_time else ""
                except (ValueError, TypeError):
                    time_str = ""
                
                # Calculate available width for filename
                # Format: "  X [YYYY-MM-DDTHH:MM:SS] status__ filename (Xs)"
                # Fixed parts: "  X [" + "] " + "  " = ~30 chars + status(8) + time_str
                fixed_len = 4 + 19 + 2 + 8 + len(time_str) + 2
                max_name_len = max(20, term_cols - fixed_len - 1)
                
                # Truncate filename to fit terminal
                if len(inp_name) > max_name_len:
                    inp_name = inp_name[:max_name_len - 3] + "..."
                
                print(f"  {status_icon} [{started}] {status:8} {inp_name}{time_str}")
            except Exception as e:
                # Silently skip malformed entries unless in debug mode
                if os.environ.get("MKV2CAST_DEBUG"):
                    print(f"  ? Error parsing entry: {e}", file=sys.stderr)
        return 0
    
    # Show history stats
    if args.history_stats:
        stats = HISTORY_DB.get_stats()
        by_status = stats.get("by_status", {})
        
        print("Conversion statistics:")
        print("-" * 40)
        total = sum(by_status.values())
        print(f"  Total conversions:  {total}")
        for status, count in sorted(by_status.items()):
            pct = (count / total * 100) if total > 0 else 0
            print(f"    {status:12} {count:5} ({pct:.1f}%)")
        
        avg_time = stats.get("avg_encode_time", 0)
        total_time = stats.get("total_encode_time", 0)
        print(f"  Average encode time: {avg_time:.1f}s")
        print(f"  Total encode time:   {total_time:.1f}s ({total_time/3600:.1f}h)")
        
        input_size = stats.get("total_input_size", 0)
        output_size = stats.get("total_output_size", 0)
        if input_size > 0:
            print(f"  Total input size:    {input_size / 1e9:.2f} GB")
            print(f"  Total output size:   {output_size / 1e9:.2f} GB")
            if output_size > 0:
                ratio = output_size / input_size
                print(f"  Compression ratio:   {ratio:.2f}x")
        return 0
    
    return None  # Continue with normal operation


def main() -> int:
    """Main entry point."""
    global CFG, APP_DIRS, HISTORY_DB
    
    # Parse arguments
    CFG, single = parse_args()
    
    # Initialize directories
    APP_DIRS = get_app_dirs()
    
    # Create default config if it doesn't exist
    config_path = save_default_config(APP_DIRS['config'])
    
    # Load config file and apply (CLI args take precedence - already parsed)
    file_config = load_config_file(APP_DIRS['config'])
    if file_config and CFG.debug:
        dbg(f"Loaded config from {config_path}")
    
    # Initialize history database
    HISTORY_DB = HistoryDB(APP_DIRS['state'])
    
    # Clean up orphaned tmp files on startup
    orphaned = cleanup_orphaned_tmp(max_age_hours=24)
    if orphaned > 0 and CFG.debug:
        dbg(f"Cleaned {orphaned} orphaned tmp file(s)")
    
    # Handle utility commands (they exit immediately)
    # Re-parse args to check for utility commands (since CFG doesn't have these)
    _parser = argparse.ArgumentParser(add_help=False)
    _parser.add_argument("--show-dirs", action="store_true")
    _parser.add_argument("--history", nargs="?", const=20, type=int)
    _parser.add_argument("--history-stats", action="store_true")
    _parser.add_argument("--clean-tmp", action="store_true")
    _parser.add_argument("--clean-logs", type=int)
    _parser.add_argument("--clean-history", type=int)
    _parser.add_argument("--check-requirements", action="store_true")
    _util_args, _ = _parser.parse_known_args()
    
    result = handle_utility_commands(_util_args)
    if result is not None:
        return result
    
    # Normal operation
    if RICH_AVAILABLE and CFG.pipeline and CFG.progress and sys.stdout.isatty():
        return main_pipeline(single)
    else:
        if not RICH_AVAILABLE and CFG.pipeline:
            print("Note: Install 'rich' (pip install rich) for better progress display.", flush=True)
        return main_legacy(single)


if __name__ == "__main__":
    sys.exit(main())
