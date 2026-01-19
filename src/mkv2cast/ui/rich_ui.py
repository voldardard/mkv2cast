"""
Rich-based progress UI for mkv2cast.

Provides beautiful multi-worker progress display with colors and animations.
Requires the 'rich' package to be installed.

Respects:
- NO_COLOR environment variable
- MKV2CAST_SCRIPT_MODE environment variable
- sys.stdout.isatty() for automatic detection
"""

import os
import re
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from rich.console import Console, Group
from rich.live import Live
from rich.text import Text

from mkv2cast.i18n import _
from mkv2cast.ui.legacy_ui import fmt_hms, shorten


def _should_use_color() -> bool:
    """Check if color output should be used."""
    # Check NO_COLOR environment variable (https://no-color.org/)
    if os.getenv("NO_COLOR"):
        return False
    # Check script mode
    if os.getenv("MKV2CAST_SCRIPT_MODE"):
        return False
    # Check if stdout is a TTY
    try:
        if not sys.stdout.isatty():
            return False
    except Exception:
        return False
    return True


@dataclass
class JobStatus:
    """Tracks the status of a single file."""

    inp: Path
    stage: str = "WAITING"  # WAITING, INTEGRITY, WAITING_ENCODE, ENCODE, DONE, FAILED, SKIPPED
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
        # Respect NO_COLOR and TTY detection
        use_color = _should_use_color()
        self.console = Console(
            force_terminal=use_color if use_color else None,
            no_color=not use_color,
        )
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

        if job.pct >= 100:
            return "finish..."

        # Try speed-based ETA first
        speed_x = self._parse_speed(job.speed)
        if speed_x and speed_x > 0 and job.dur_ms > 0 and job.out_ms > 0:
            remaining_ms = job.dur_ms - job.out_ms
            if remaining_ms > 0:
                eta_s = (remaining_ms / 1000.0) / speed_x
                return fmt_hms(eta_s)

        # Time-based ETA
        if job.pct >= 99:
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
            for job in skip_jobs[-8:]:
                filename = shorten(job.inp.name, 50)
                reason = job.result_msg or ""
                line = Text()
                line.append(f"⊘ {_('SKIP')} ", style="dim")
                line.append(filename, style="dim")
                if reason:
                    line.append(f" ({reason})", style="dim italic")
                parts.append(line)

            # 2. DONE files (green)
            for job in done_jobs[-5:]:
                filename = shorten(job.inp.name, 40)
                line = Text()
                line.append(f"✓ {_('DONE')} ", style="bold green")
                line.append(filename, style="green")
                timing = []
                if job.integrity_elapsed > 0:
                    timing.append(f"{_('int')}:{fmt_hms(job.integrity_elapsed)}")
                if job.encode_elapsed > 0:
                    timing.append(f"{_('enc')}:{fmt_hms(job.encode_elapsed)}")
                if job.total_elapsed > 0:
                    timing.append(f"{_('tot')}:{fmt_hms(job.total_elapsed)}")
                if timing:
                    line.append(f" ({' '.join(timing)})", style="dim")
                parts.append(line)

            # 3. FAIL files (red)
            for job in fail_jobs[-3:]:
                filename = shorten(job.inp.name, 50)
                reason = job.result_msg or _("error")
                line = Text()
                line.append(f"✗ {_('FAIL')} ", style="bold red")
                line.append(filename, style="red")
                line.append(f" ({reason})", style="red dim")
                parts.append(line)

            # Separator
            if parts and (active_jobs or waiting_encode):
                parts.append(Text("─" * 60, style="dim"))

            # 4. WAITING_ENCODE files
            for job in waiting_encode[:3]:
                filename = shorten(job.inp.name, 50)
                line = Text()
                line.append(f"⏳ {_('QUEUE')} ", style="cyan")
                line.append(filename, style="cyan dim")
                if job.integrity_elapsed > 0:
                    line.append(f" ({_('check')}:{fmt_hms(job.integrity_elapsed)})", style="dim")
                parts.append(line)
            if len(waiting_encode) > 3:
                parts.append(Text(f"   ... +{len(waiting_encode) - 3} {_('in queue')}", style="cyan dim"))

            # 5. ACTIVE jobs with progress bars
            for job in sorted(active_jobs, key=lambda x: (0 if x.stage == "ENCODE" else 1, x.worker_id)):
                filename = shorten(job.inp.name, 40)

                if job.stage == "INTEGRITY":
                    elapsed = time.time() - job.integrity_start if job.integrity_start > 0 else 0
                    stage_icon = "🔍"
                    stage_text = _("CHECK")
                else:
                    elapsed = time.time() - job.encode_start if job.encode_start > 0 else 0
                    stage_icon = "⚡"
                    stage_text = _("ENCODE")

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

            # 6. Waiting count
            if waiting_check:
                parts.append(Text(f"⏳ {_('Waiting for check')}: {len(waiting_check)} {_('file(s)')}", style="dim"))

            if not parts:
                parts.append(Text(_("Initializing..."), style="dim"))

            return Group(*parts)

    def _refresh_loop(self):
        """Background thread that refreshes the display."""
        while not self._stop_event.is_set():
            try:
                if self.live:
                    self.live.update(self._render())
            except Exception:
                pass
            time.sleep(0.1)

    def start(self):
        """Start the live display."""
        self.live = Live(self._render(), console=self.console, refresh_per_second=10, transient=False)
        self.live.start()

        self._refresh_thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self._refresh_thread.start()

    def stop(self):
        """Stop the live display."""
        self._stop_event.set()
        if self._refresh_thread:
            self._refresh_thread.join(timeout=1.0)
        if self.live:
            try:
                self.live.update(self._render())
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

    def update_integrity(
        self, worker_id: int, _stage: str, pct: int, _filename: str, speed: str = "", inp: Optional[Path] = None
    ):
        """Update integrity progress."""
        with self.lock:
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
        """Mark integrity check as complete."""
        with self.lock:
            if inp:
                key = str(inp)
                if key in self.jobs:
                    job = self.jobs[key]
                    job.integrity_elapsed = time.time() - job.integrity_start
                    job.stage = "WAITING_ENCODE"
                    job.pct = 0
            else:
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

    def update_encode(
        self,
        worker_id: int,
        _stage: str,
        pct: int,
        _filename: str,
        speed: str = "",
        inp: Optional[Path] = None,
        out_ms: int = 0,
        dur_ms: int = 0,
    ):
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
        """Mark encode as complete."""
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

    def mark_done(self, inp: Path, _msg: str = "", final_path: Optional[Path] = None, output_size: int = 0):
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
                job = JobStatus(inp=inp, stage="SKIPPED", result_msg=reason)
                self.jobs[key] = job

            self.skipped += 1
            self.processed += 1

    def log(self, msg: str):
        """Add a message to the log."""
        with self.lock:
            self.completed_log.append(msg)

    def get_stats(self) -> Tuple[int, int, int, int]:
        """Get current statistics."""
        with self.lock:
            return (self.ok, self.skipped, self.failed, self.processed)
