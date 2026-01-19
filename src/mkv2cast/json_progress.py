"""
JSON progress output for mkv2cast.

This module provides structured JSON output for integration
with other applications (web UIs, monitoring tools, etc.).
"""

import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class FileProgress:
    """Progress information for a single file."""

    filename: str
    filepath: str
    status: str  # "queued", "checking", "encoding", "done", "skipped", "failed"
    progress_percent: float = 0.0
    current_frame: int = 0
    total_frames: int = 0
    current_time_ms: int = 0
    duration_ms: int = 0
    fps: float = 0.0
    speed: str = ""
    bitrate: str = ""
    size_bytes: int = 0
    eta_seconds: float = 0.0
    error: Optional[str] = None
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    output_path: Optional[str] = None


@dataclass
class OverallProgress:
    """Overall progress for the entire batch."""

    total_files: int = 0
    processed_files: int = 0
    converted_files: int = 0
    skipped_files: int = 0
    failed_files: int = 0
    current_file: Optional[str] = None
    overall_percent: float = 0.0
    eta_seconds: float = 0.0
    started_at: Optional[float] = None
    backend: str = ""
    encode_workers: int = 1
    integrity_workers: int = 1


@dataclass
class JSONProgressState:
    """Complete state for JSON progress output."""

    version: str = "1.0"
    timestamp: float = field(default_factory=time.time)
    event: str = "progress"  # "start", "progress", "file_start", "file_done", "complete"
    overall: OverallProgress = field(default_factory=OverallProgress)
    files: Dict[str, FileProgress] = field(default_factory=dict)
    current_encoding: List[str] = field(default_factory=list)
    current_checking: List[str] = field(default_factory=list)


class JSONProgressOutput:
    """Manages JSON progress output to stdout."""

    def __init__(self, stream=sys.stdout):
        self.stream = stream
        self.state = JSONProgressState()
        self._file_durations: Dict[str, int] = {}

    def _emit(self, event: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Emit a JSON progress event."""
        self.state.timestamp = time.time()
        self.state.event = event
        output = asdict(self.state)
        if extra:
            output.update(extra)
        print(json.dumps(output), file=self.stream, flush=True)

    def start(
        self,
        total_files: int,
        backend: str,
        encode_workers: int,
        integrity_workers: int,
    ) -> None:
        """Signal start of processing."""
        self.state.overall = OverallProgress(
            total_files=total_files,
            backend=backend,
            encode_workers=encode_workers,
            integrity_workers=integrity_workers,
            started_at=time.time(),
        )
        self._emit("start")

    def set_file_duration(self, filepath: str, duration_ms: int) -> None:
        """Set the duration for a file (from probe)."""
        self._file_durations[filepath] = duration_ms

    def file_queued(self, filepath: Path, duration_ms: int = 0) -> None:
        """Signal a file has been queued."""
        key = str(filepath)
        self.state.files[key] = FileProgress(
            filename=filepath.name,
            filepath=key,
            status="queued",
            duration_ms=duration_ms or self._file_durations.get(key, 0),
        )
        self._file_durations[key] = duration_ms

    def file_checking(self, filepath: Path) -> None:
        """Signal a file integrity check has started."""
        key = str(filepath)
        if key in self.state.files:
            self.state.files[key].status = "checking"
            self.state.files[key].started_at = time.time()
        self.state.current_checking.append(filepath.name)
        self._emit("file_checking", {"file": filepath.name})

    def file_check_done(self, filepath: Path) -> None:
        """Signal a file integrity check has finished."""
        if filepath.name in self.state.current_checking:
            self.state.current_checking.remove(filepath.name)

    def file_encoding_start(self, filepath: Path, duration_ms: int = 0) -> None:
        """Signal encoding has started for a file."""
        key = str(filepath)
        if key in self.state.files:
            self.state.files[key].status = "encoding"
            self.state.files[key].started_at = time.time()
            if duration_ms:
                self.state.files[key].duration_ms = duration_ms
        else:
            self.state.files[key] = FileProgress(
                filename=filepath.name,
                filepath=key,
                status="encoding",
                duration_ms=duration_ms or self._file_durations.get(key, 0),
                started_at=time.time(),
            )
        self.state.current_encoding.append(filepath.name)
        self.state.overall.current_file = filepath.name
        self._emit("file_start", {"file": filepath.name})

    def file_progress(
        self,
        filepath: Path,
        frame: int = 0,
        fps: float = 0.0,
        time_ms: int = 0,
        bitrate: str = "",
        speed: str = "",
        size_bytes: int = 0,
    ) -> None:
        """Update encoding progress for a file."""
        key = str(filepath)
        if key not in self.state.files:
            return

        fp = self.state.files[key]
        fp.current_frame = frame
        fp.current_time_ms = time_ms
        fp.fps = fps
        fp.bitrate = bitrate
        fp.speed = speed
        fp.size_bytes = size_bytes

        # Calculate progress percentage
        if fp.duration_ms > 0:
            fp.progress_percent = min(100.0, (time_ms / fp.duration_ms) * 100)

            # Calculate ETA
            if time_ms > 0 and fp.started_at:
                elapsed = time.time() - fp.started_at
                remaining_ms = fp.duration_ms - time_ms
                if time_ms > 0:
                    rate = elapsed / time_ms
                    fp.eta_seconds = (remaining_ms * rate) / 1000

        self._update_overall()
        self._emit("progress")

    def file_done(
        self,
        filepath: Path,
        output_path: Optional[Path] = None,
        skipped: bool = False,
        error: Optional[str] = None,
    ) -> None:
        """Signal a file has finished processing."""
        key = str(filepath)
        if key in self.state.files:
            fp = self.state.files[key]
            fp.finished_at = time.time()
            if error:
                fp.status = "failed"
                fp.error = error
                self.state.overall.failed_files += 1
            elif skipped:
                fp.status = "skipped"
                self.state.overall.skipped_files += 1
            else:
                fp.status = "done"
                fp.progress_percent = 100.0
                self.state.overall.converted_files += 1
            if output_path:
                fp.output_path = str(output_path)

        if filepath.name in self.state.current_encoding:
            self.state.current_encoding.remove(filepath.name)

        self.state.overall.processed_files += 1
        self._update_overall()
        self._emit("file_done", {"file": filepath.name, "status": fp.status if key in self.state.files else "unknown"})

    def complete(self) -> None:
        """Signal all processing is complete."""
        self.state.overall.overall_percent = 100.0
        self._emit("complete")

    def _update_overall(self) -> None:
        """Update overall progress statistics."""
        total = self.state.overall.total_files
        if total > 0:
            # Weight: completed files + partial progress of encoding files
            completed_weight = self.state.overall.processed_files
            encoding_weight = sum(
                fp.progress_percent / 100.0 for fp in self.state.files.values() if fp.status == "encoding"
            )
            self.state.overall.overall_percent = ((completed_weight + encoding_weight) / total) * 100

            # Estimate overall ETA based on average processing time
            if self.state.overall.started_at and self.state.overall.processed_files > 0:
                elapsed = time.time() - self.state.overall.started_at
                avg_time = elapsed / (self.state.overall.processed_files + encoding_weight)
                remaining = total - self.state.overall.processed_files - encoding_weight
                self.state.overall.eta_seconds = avg_time * remaining


def parse_ffmpeg_progress_for_json(line: str) -> Dict[str, Any]:
    """Parse FFmpeg progress line for JSON output.

    Returns a dict with parsed values.
    """
    result: Dict[str, Any] = {}

    # frame=12345
    if "frame=" in line:
        try:
            frame_part = line.split("frame=")[1].split()[0]
            result["frame"] = int(frame_part)
        except (IndexError, ValueError):
            pass

    # fps=123.45
    if "fps=" in line:
        try:
            fps_part = line.split("fps=")[1].split()[0]
            result["fps"] = float(fps_part)
        except (IndexError, ValueError):
            pass

    # time=00:01:23.45
    if "time=" in line:
        try:
            time_part = line.split("time=")[1].split()[0]
            if time_part and time_part != "N/A":
                parts = time_part.split(":")
                if len(parts) == 3:
                    h, m, s = parts
                    time_ms = int((int(h) * 3600 + int(m) * 60 + float(s)) * 1000)
                    result["time_ms"] = time_ms
        except (IndexError, ValueError):
            pass

    # bitrate=1234.5kbits/s
    if "bitrate=" in line:
        try:
            bitrate_part = line.split("bitrate=")[1].split()[0]
            result["bitrate"] = bitrate_part
        except (IndexError, ValueError):
            pass

    # speed=1.23x
    if "speed=" in line:
        try:
            speed_part = line.split("speed=")[1].split()[0]
            result["speed"] = speed_part
        except (IndexError, ValueError):
            pass

    # size=12345kB
    if "size=" in line:
        try:
            size_part = line.split("size=")[1].split()[0]
            if size_part.endswith("kB"):
                result["size_bytes"] = int(float(size_part[:-2]) * 1024)
            elif size_part.endswith("mB"):
                result["size_bytes"] = int(float(size_part[:-2]) * 1024 * 1024)
        except (IndexError, ValueError):
            pass

    return result
