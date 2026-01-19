"""
Simple Rich-based progress UI for mkv2cast (sequential mode).

Provides a beautiful progress bar for single-file encoding.

Respects:
- NO_COLOR environment variable
- MKV2CAST_SCRIPT_MODE environment variable
- sys.stdout.isatty() for automatic detection
"""

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from rich.console import Console
from rich.live import Live
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from mkv2cast.i18n import _
from mkv2cast.ui.legacy_ui import fmt_hms


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


class SimpleRichUI:
    """Simple Rich-based UI for sequential file processing."""

    def __init__(self, progress_enabled: bool = True):
        # Respect NO_COLOR and TTY detection
        use_color = _should_use_color()
        self.console = Console(
            force_terminal=use_color if use_color else None,
            no_color=not use_color,
        )
        self.enabled = progress_enabled and use_color

        # Stats
        self.ok = 0
        self.skipped = 0
        self.failed = 0
        self.processed = 0

        # Current progress
        self.progress: Optional[Progress] = None
        self.current_task: Optional[TaskID] = None
        self.live: Optional[Live] = None

    def log(self, msg: str, style: str = "") -> None:
        """Print a log message."""
        if style:
            self.console.print(msg, style=style)
        else:
            self.console.print(msg)

    def log_file_start(self, inp: Path, output: Path) -> None:
        """Log start of file processing."""
        self.console.print()
        self.console.print(f"[bold blue]▶[/bold blue] [cyan]{inp.name}[/cyan]")
        self.console.print(f"  [dim]→ {output.name}[/dim]")

    def log_skip(self, reason: str) -> None:
        """Log a skip."""
        self.console.print(f"  [yellow]⊘ {_('SKIP')}[/yellow]: {reason}")
        self.skipped += 1
        self.processed += 1

    def log_error(self, error: str) -> None:
        """Log an error."""
        self.console.print(f"  [red]✗ {_('FAILED')}[/red]: {error}")
        self.failed += 1
        self.processed += 1

    def log_success(self, elapsed: float, output_size: int = 0) -> None:
        """Log success."""
        size_str = ""
        if output_size > 0:
            size_mb = output_size / (1024 * 1024)
            size_str = f" ({size_mb:.1f} MB)"
        self.console.print(f"  [green]✓ {_('OK')}[/green] {_('in')} {fmt_hms(elapsed)}{size_str}")
        self.ok += 1
        self.processed += 1

    def log_compatible(self) -> None:
        """Log file is already compatible."""
        self.console.print(f"  [green]✓[/green] [dim]{_('Already compatible')}[/dim]")
        self.skipped += 1
        self.processed += 1

    def run_ffmpeg_with_progress(
        self, cmd: List[str], stage: str, dur_ms: int = 0, file_idx: int = 1, total_files: int = 1
    ) -> Tuple[int, str]:
        """
        Run ffmpeg command while showing progress.

        Returns (return_code, error_message).
        """
        if not self.enabled:
            # Fallback to simple execution
            result = subprocess.run(cmd, capture_output=True, timeout=86400)
            stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
            return result.returncode, stderr

        # Create progress bar
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}[/bold blue]"),
            BarColumn(bar_width=40),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("•"),
            TextColumn("[cyan]{task.fields[speed]}[/cyan]"),
            TextColumn("•"),
            TimeElapsedColumn(),
            TextColumn("→"),
            TimeRemainingColumn(),
            console=self.console,
            transient=True,
        )

        task_desc = f"[{file_idx}/{total_files}] {stage}"
        task_id = progress.add_task(task_desc, total=100, speed="0.0x")

        # Start ffmpeg process
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
        )

        # Read stderr for progress updates
        stderr_buffer = []
        last_pct = 0

        with progress:
            while True:
                # Read one line from stderr
                if process.stderr is None:
                    break
                line = process.stderr.readline()
                if not line:
                    break

                line_str = line.decode("utf-8", errors="replace")
                stderr_buffer.append(line_str)

                # Parse ffmpeg progress
                # Example: frame=  123 fps=45 q=28.0 size=    1234kB time=00:00:05.12 bitrate=1234.5kbits/s speed=1.23x
                pct, speed = self._parse_ffmpeg_progress(line_str, dur_ms)

                if pct > last_pct:
                    last_pct = pct
                    progress.update(task_id, completed=pct)

                if speed:
                    progress.update(task_id, speed=speed)

        # Wait for process to complete
        process.wait()

        stderr_text = "".join(stderr_buffer)
        return process.returncode, stderr_text

    def _parse_ffmpeg_progress(self, line: str, dur_ms: int) -> Tuple[int, str]:
        """Parse ffmpeg progress line. Returns (percentage, speed)."""
        pct = 0
        speed = ""

        # Parse time
        m = re.search(r"time=\s*(\d+):(\d+):(\d+)\.(\d+)", line)
        if m and dur_ms > 0:
            h, mi, s, cs = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
            current_ms = (h * 3600 + mi * 60 + s) * 1000 + cs * 10
            pct = min(100, int(current_ms * 100 / dur_ms))

        # Parse speed
        m = re.search(r"speed=\s*([0-9.]+)x", line)
        if m:
            speed = f"{float(m.group(1)):.1f}x"

        return pct, speed

    def print_summary(self, total_time: float) -> None:
        """Print final summary."""
        self.console.print()

        # Create summary table
        table = Table(title=_("Summary"), box=None, show_header=False)
        table.add_column("Metric", style="bold")
        table.add_column("Value", justify="right")

        table.add_row(f"✓ {_('Converted')}", f"[green]{self.ok}[/green]")
        table.add_row(f"⊘ {_('Skipped')}", f"[yellow]{self.skipped}[/yellow]")
        table.add_row(f"✗ {_('Failed')}", f"[red]{self.failed}[/red]")
        table.add_row(f"⏱ {_('Total time')}", fmt_hms(total_time))

        self.console.print(table)

    def inc_ok(self) -> None:
        """Increment success counter."""
        self.ok += 1
        self.processed += 1

    def inc_skipped(self) -> None:
        """Increment skipped counter."""
        self.skipped += 1
        self.processed += 1

    def inc_failed(self) -> None:
        """Increment failed counter."""
        self.failed += 1
        self.processed += 1

    def get_stats(self):
        """Get current stats."""
        return (self.ok, self.skipped, self.failed, self.processed)
