"""
File integrity checking for mkv2cast.

Verifies source files before processing to avoid corrupted outputs.
Includes:
- File size stability check (for files being downloaded/copied)
- Basic ffprobe validation
- Optional deep decode verification
"""

import subprocess
import time
from pathlib import Path
from typing import Callable, Optional, Tuple


def file_size(path: Path) -> int:
    """Get file size in bytes, returns 0 on error."""
    try:
        return path.stat().st_size
    except Exception:
        return 0


def run_quiet(cmd: list, timeout: float = 10.0) -> bool:
    """Run a command quietly, return True if successful."""
    try:
        p = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout)
        return p.returncode == 0
    except Exception:
        return False


def check_file_stable(path: Path, wait_seconds: int = 3) -> bool:
    """
    Check if file size is stable (not being written to).

    Args:
        path: Path to the file.
        wait_seconds: Number of seconds to wait between checks.

    Returns:
        True if file size is stable, False otherwise.
    """
    if wait_seconds <= 0:
        return True

    s1 = file_size(path)
    if s1 < 1024 * 1024:  # Less than 1MB is suspicious
        return False

    time.sleep(wait_seconds)

    s2 = file_size(path)
    return s1 == s2


def check_ffprobe_valid(path: Path, timeout: float = 8.0) -> bool:
    """
    Check if file is valid using ffprobe.

    Args:
        path: Path to the file.
        timeout: Timeout in seconds.

    Returns:
        True if ffprobe reports valid duration.
    """
    return run_quiet(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        timeout=timeout,
    )


def check_deep_decode(
    path: Path,
    log_path: Optional[Path] = None,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    dur_ms: int = 0,
) -> bool:
    """
    Perform deep decode verification by decoding the entire video stream.

    This is slow but catches files that are truncated or have decode errors.

    Args:
        path: Path to the file.
        log_path: Optional path to write logs.
        progress_callback: Optional callback(pct, speed) for progress updates.
        dur_ms: Duration in milliseconds for progress calculation.

    Returns:
        True if decode succeeds, False otherwise.
    """
    if log_path:
        with log_path.open("a", encoding="utf-8", errors="replace") as lf:
            lf.write("DEEP_CHECK: decode video stream\n")

    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path), "-map", "0:v:0", "-f", "null", "-"]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=3600)  # 1 hour timeout
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


def integrity_check(
    path: Path,
    enabled: bool = True,
    stable_wait: int = 3,
    deep_check: bool = False,
    log_path: Optional[Path] = None,
    progress_callback: Optional[Callable[[str, int, str], None]] = None,
) -> Tuple[bool, float]:
    """
    Perform complete integrity check on a file.

    Args:
        path: Path to the file to check.
        enabled: If False, skip all checks and return True.
        stable_wait: Seconds to wait for file size stability.
        deep_check: If True, perform full decode verification.
        log_path: Optional path to write logs.
        progress_callback: Optional callback(stage, pct, message) for UI updates.

    Returns:
        Tuple of (success, elapsed_seconds).
    """
    start_time = time.time()

    if not enabled:
        return True, 0

    # Stage 1: Check file exists and has reasonable size
    if progress_callback:
        progress_callback("CHECK", 0, "Checking file...")

    size = file_size(path)
    if size < 1024 * 1024:  # Less than 1MB
        return False, time.time() - start_time

    # Stage 2: File stability check
    if stable_wait > 0:
        for i in range(stable_wait):
            if progress_callback:
                pct = int(((i + 1) * 50) / stable_wait)
                progress_callback("STABLE", pct, f"Waiting {stable_wait - i - 1}s...")
            time.sleep(1)

        new_size = file_size(path)
        if size != new_size:
            return False, time.time() - start_time

    # Stage 3: ffprobe validation
    if progress_callback:
        progress_callback("FFPROBE", 60, "Validating with ffprobe...")

    if not check_ffprobe_valid(path):
        return False, time.time() - start_time

    # Stage 4: Deep check (optional)
    if deep_check:
        if progress_callback:
            progress_callback("DECODE", 70, "Deep verification...")

        if not check_deep_decode(path, log_path):
            return False, time.time() - start_time

    if progress_callback:
        progress_callback("DONE", 100, "OK")

    elapsed = time.time() - start_time
    return True, elapsed
