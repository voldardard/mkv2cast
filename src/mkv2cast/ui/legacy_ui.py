"""
Legacy text-based progress UI for mkv2cast.

Used when rich is not available or in non-interactive terminals.
"""

import shutil
import sys
from dataclasses import dataclass
from typing import Optional


def term_width() -> int:
    """Get terminal width."""
    try:
        return shutil.get_terminal_size((120, 20)).columns
    except Exception:
        return 120


def mkbar(pct: int, width: int = 26) -> str:
    """Create a simple progress bar string."""
    pct = max(0, min(100, pct))
    filled = int(pct * width / 100)
    empty = width - filled
    return "#" * filled + "-" * empty


def shorten(s: str, maxlen: int) -> str:
    """Shorten a string with ellipsis if too long."""
    if maxlen <= 0:
        return ""
    if len(s) <= maxlen:
        return s
    if maxlen <= 3:
        return s[:maxlen]
    return s[: maxlen - 3] + "..."


def fmt_hms(seconds: float) -> str:
    """Format seconds as HH:MM:SS."""
    if seconds < 0:
        seconds = 0
    s = int(round(seconds))
    h = s // 3600
    m = (s % 3600) // 60
    r = s % 60
    return f"{h:02d}:{m:02d}:{r:02d}"


@dataclass
class UIState:
    """State for legacy UI rendering."""

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

    def __init__(self, progress: bool = True, bar_width: int = 26):
        self.enabled = progress and sys.stdout.isatty()
        self.bar_width = bar_width
        self._last_render: Optional[str] = None

        # Stats tracking
        self.ok = 0
        self.skipped = 0
        self.failed = 0
        self.processed = 0

    def render(self, st: UIState) -> None:
        """Render progress line to terminal."""
        if not self.enabled:
            return

        w = term_width()

        bar = mkbar(st.pct, self.bar_width)
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

    def endline(self) -> None:
        """Clear the current progress line."""
        if not self.enabled:
            return
        sys.stdout.write("\r" + " " * (len(self._last_render) if self._last_render else 80) + "\r")
        sys.stdout.flush()
        self._last_render = None

    def log(self, msg: str) -> None:
        """Print a log message, clearing progress line first."""
        if self.enabled and self._last_render:
            sys.stdout.write("\r" + " " * len(self._last_render) + "\r")
            sys.stdout.flush()
        print(msg, flush=True)
        self._last_render = None

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
