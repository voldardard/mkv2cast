"""
Pipeline orchestrator for parallel processing in mkv2cast.

Manages multiple integrity check and encode workers processing files in parallel.
"""

import os
import re
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from typing import Callable, List, Optional, Tuple

from mkv2cast.config import Config
from mkv2cast.converter import (
    Decision,
    build_transcode_cmd,
    decide_for,
    probe_duration_ms,
)
from mkv2cast.i18n import _
from mkv2cast.integrity import check_ffprobe_valid, file_size
from mkv2cast.ui.rich_ui import RichProgressUI


@dataclass
class EncodeJob:
    """Job data passed from integrity worker to encode worker."""

    inp: Path
    decision: Decision
    log_path: Path
    final: Path
    tmp: Path
    dur_ms: int
    stage: str
    integrity_time: float


# Track active ffmpeg processes for cleanup on interrupt
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
    """Terminate all active processes."""
    with _processes_lock:
        procs = list(_active_processes)

    for proc in procs:
        try:
            proc.terminate()
        except Exception:
            pass

    # Wait a bit then kill any remaining
    time.sleep(0.5)
    for proc in procs:
        try:
            if proc.poll() is None:
                proc.kill()
        except Exception:
            pass


def integrity_check_with_progress(
    path: Path,
    ui: RichProgressUI,
    worker_id: int,
    filename: str,
    log_path: Optional[Path] = None,
    stop_event: Optional[threading.Event] = None,
    cfg: Optional[Config] = None,
) -> Tuple[bool, float]:
    """
    Perform integrity check with Rich UI progress updates.

    Returns (success, elapsed_seconds).
    """
    if cfg is None:
        from mkv2cast.config import CFG

        cfg = CFG

    start_time = time.time()

    if not cfg.integrity_check:
        return True, 0

    ui.start_integrity(worker_id, filename, path)

    # Stage 1: File size check
    ui.update_integrity(worker_id, "SIZE", 10, filename, inp=path)
    size = file_size(path)
    if size < 1024 * 1024:  # 1MB minimum
        ui.stop_integrity(worker_id, path)
        return False, time.time() - start_time

    # Stage 2: Stability check
    if cfg.stable_wait > 0:
        for i in range(cfg.stable_wait):
            if stop_event and stop_event.is_set():
                ui.stop_integrity(worker_id, path)
                return False, time.time() - start_time

            pct = 10 + int((i + 1) * 40 / cfg.stable_wait)
            ui.update_integrity(worker_id, "STABLE", pct, filename, inp=path)
            time.sleep(1)

        new_size = file_size(path)
        if size != new_size:
            ui.stop_integrity(worker_id, path)
            return False, time.time() - start_time

    # Stage 3: ffprobe check
    ui.update_integrity(worker_id, "FFPROBE", 60, filename, inp=path)
    if not check_ffprobe_valid(path):
        ui.stop_integrity(worker_id, path)
        return False, time.time() - start_time

    # Stage 4: Deep check (optional)
    if cfg.deep_check:
        ui.update_integrity(worker_id, "DECODE", 70, filename, inp=path)
        # Deep decode check - this takes a while
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path), "-map", "0:v:0", "-f", "null", "-"]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=3600)
            if result.returncode != 0:
                ui.stop_integrity(worker_id, path)
                return False, time.time() - start_time
        except Exception:
            ui.stop_integrity(worker_id, path)
            return False, time.time() - start_time

    ui.update_integrity(worker_id, "DONE", 100, filename, inp=path)
    ui.stop_integrity(worker_id, path)

    elapsed = time.time() - start_time
    return True, elapsed


def run_ffmpeg_with_progress(
    cmd: List[str],
    ui: RichProgressUI,
    worker_id: int,
    stage: str,
    filename: str,
    dur_ms: int,
    log_path: Optional[Path],
    inp: Path,
    stop_event: Optional[threading.Event] = None,
) -> int:
    """
    Run ffmpeg command while updating Rich UI progress.

    Returns the process return code.
    """
    # Add progress output to command
    progress_cmd = list(cmd)
    # Insert progress stats option after ffmpeg
    if progress_cmd[0] == "ffmpeg" and "-progress" not in progress_cmd:
        progress_cmd.insert(1, "-stats")

    # Start process
    process = subprocess.Popen(
        progress_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
    )
    register_process(process)

    try:
        # Parse stderr for progress
        last_pct = 0
        last_speed = ""

        while True:
            if stop_event and stop_event.is_set():
                process.terminate()
                break

            if process.stderr is None:
                break
            line = process.stderr.readline()
            if not line:
                break

            line_str = line.decode("utf-8", errors="replace")

            # Log to file
            if log_path:
                try:
                    with log_path.open("a", encoding="utf-8", errors="replace") as lf:
                        lf.write(line_str)
                except Exception:
                    pass

            # Parse progress
            pct, speed, out_ms = _parse_ffmpeg_progress(line_str, dur_ms)

            if pct > last_pct or speed != last_speed:
                last_pct = pct
                last_speed = speed
                ui.update_encode(worker_id, stage, pct, filename, speed=speed, inp=inp, out_ms=out_ms, dur_ms=dur_ms)

        process.wait()
        return process.returncode

    finally:
        unregister_process(process)


def _parse_ffmpeg_progress(line: str, dur_ms: int) -> Tuple[int, str, int]:
    """Parse ffmpeg progress line. Returns (percentage, speed, current_ms)."""
    pct = 0
    speed = ""
    out_ms = 0

    # Parse time
    m = re.search(r"time=\s*(\d+):(\d+):(\d+)\.(\d+)", line)
    if m:
        h, mi, s, cs = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        out_ms = (h * 3600 + mi * 60 + s) * 1000 + cs * 10
        if dur_ms > 0:
            pct = min(100, int(out_ms * 100 / dur_ms))

    # Parse speed
    m = re.search(r"speed=\s*([0-9.]+)x", line)
    if m:
        speed = f"{float(m.group(1)):.1f}x"

    return pct, speed, out_ms


class PipelineOrchestrator:
    """Orchestrates parallel integrity check and encoding with multiple workers."""

    def __init__(
        self,
        targets: List[Path],
        backend: str,
        ui: RichProgressUI,
        cfg: Config,
        encode_workers: int,
        integrity_workers: int,
        get_log_path: Callable[[Path], Path],
        get_tmp_path: Callable[[Path, int, str], Path],
        output_exists_fn: Callable[[Path, Config], bool],
    ):
        self.targets = targets
        self.backend = backend
        self.ui = ui
        self.cfg = cfg
        self.encode_workers_count = encode_workers
        self.integrity_workers_count = integrity_workers
        self.get_log_path = get_log_path
        self.get_tmp_path = get_tmp_path
        self.output_exists_fn = output_exists_fn

        # Queues
        self.integrity_queue: Queue[Optional[Path]] = Queue()
        self.encode_queue: Queue[Optional[EncodeJob]] = Queue()

        # Control
        self.stop_event = threading.Event()
        self.interrupted = False

        # Track sentinels
        self.integrity_sentinels_remaining = integrity_workers
        self.integrity_sentinels_lock = threading.Lock()

        # Register all jobs and fill integrity queue
        for t in targets:
            self.ui.register_job(t, backend=self.backend)
            self.integrity_queue.put(t)

        # Add sentinels for integrity workers
        for _i in range(integrity_workers):
            self.integrity_queue.put(None)

    def integrity_worker(self, worker_id: int):
        """Worker that performs integrity checks and prepares encode jobs."""
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
                        for _j in range(self.encode_workers_count):
                            self.encode_queue.put(None)
                break

            filename = inp.name

            # Check if output already exists
            if self.output_exists_fn(inp, self.cfg):
                self.ui.mark_skipped(inp, _("output exists"))
                continue

            log_path = self.get_log_path(inp)

            # Run integrity check
            try:
                success, integrity_time = integrity_check_with_progress(
                    inp, self.ui, worker_id, filename, log_path, self.stop_event, self.cfg
                )
                if not success:
                    self.ui.mark_skipped(inp, _("integrity failed"))
                    continue
            except Exception as e:
                self.ui.mark_failed(inp, _("integrity error") + f": {e}")
                continue

            # Analyze file
            try:
                d = decide_for(inp, self.cfg)
            except Exception as e:
                self.ui.mark_failed(inp, _("analysis error") + f": {e}")
                continue

            # Check if already compatible
            if (not d.need_v) and (not d.need_a) and self.cfg.skip_when_ok:
                self.ui.mark_skipped(inp, _("compatible"))
                continue

            # Build output paths
            tag = ""
            if d.need_v:
                tag += ".h264"
            if d.need_a:
                tag += ".aac"
            if not tag:
                tag = ".remux"

            final = inp.parent / f"{inp.stem}{tag}{self.cfg.suffix}.{self.cfg.container}"
            if final.exists():
                self.ui.mark_skipped(inp, _("output exists"))
                continue

            tmp = self.get_tmp_path(inp, worker_id, tag)
            if tmp.exists():
                self.ui.mark_skipped(inp, _("tmp exists"))
                continue

            # Build ffmpeg command
            cmd, stage = build_transcode_cmd(inp, d, self.backend, tmp, log_path, self.cfg)
            dur_ms = probe_duration_ms(inp)

            if self.cfg.dryrun:
                self.ui.log(f"DRYRUN: {' '.join(cmd)}")
                self.ui.mark_skipped(inp, _("dryrun"))
                continue

            # Create encode job
            job = EncodeJob(
                inp=inp,
                decision=d,
                log_path=log_path,
                final=final,
                tmp=tmp,
                dur_ms=dur_ms,
                stage=stage,
                integrity_time=integrity_time,
            )
            self.encode_queue.put(job)

    def encode_worker(self, worker_id: int):
        """Worker that performs encoding."""
        while not self.stop_event.is_set():
            try:
                job = self.encode_queue.get(timeout=0.5)
            except Empty:
                continue

            if job is None:
                break

            filename = job.inp.name
            self.ui.start_encode(worker_id, filename, job.inp, job.final.name)

            # Rebuild command (in case something changed)
            cmd, _stage = build_transcode_cmd(job.inp, job.decision, self.backend, job.tmp, job.log_path, self.cfg)

            try:
                rc = run_ffmpeg_with_progress(
                    cmd, self.ui, worker_id, job.stage, filename, job.dur_ms, job.log_path, job.inp, self.stop_event
                )
            except Exception as e:
                try:
                    job.tmp.unlink(missing_ok=True)
                except Exception:
                    pass
                self.ui.mark_failed(job.inp, _("encode error") + f": {e}")
                continue

            if rc == 0:
                try:
                    shutil.move(str(job.tmp), str(job.final))
                    output_size = job.final.stat().st_size if job.final.exists() else 0
                    self.ui.mark_done(job.inp, final_path=job.final, output_size=output_size)
                except Exception as e:
                    try:
                        job.tmp.unlink(missing_ok=True)
                    except Exception:
                        pass
                    self.ui.mark_failed(job.inp, _("move error") + f": {e}")
            else:
                try:
                    job.tmp.unlink(missing_ok=True)
                except Exception:
                    pass
                if self.stop_event.is_set():
                    self.ui.mark_failed(job.inp, _("interrupted"))
                else:
                    self.ui.mark_failed(job.inp, f"ffmpeg rc={rc}")

    def run(self) -> Tuple[int, int, int, bool]:
        """Run the pipeline. Returns (ok, skipped, failed, interrupted)."""
        # Create worker threads
        integrity_threads = []
        for i in range(self.integrity_workers_count):
            t = threading.Thread(target=self.integrity_worker, args=(i,), name=f"integrity_worker_{i}", daemon=True)
            integrity_threads.append(t)

        encode_threads = []
        for i in range(self.encode_workers_count):
            t = threading.Thread(target=self.encode_worker, args=(i,), name=f"encode_worker_{i}", daemon=True)
            encode_threads.append(t)

        # Signal handler
        def on_sigint(_sig, _frm):
            self.interrupted = True
            self.stop_event.set()
            terminate_all_processes()

        old_handler = signal.signal(signal.SIGINT, on_sigint)

        try:
            # Start UI
            self.ui.start()

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
            self.ui.stop()
            terminate_all_processes()

        # Get final stats
        ok, skipped, failed, _processed = self.ui.get_stats()
        return (ok, skipped, failed, self.interrupted)


def auto_detect_workers() -> Tuple[int, int]:
    """Auto-detect optimal number of workers based on system resources."""
    try:
        cpu_count = os.cpu_count() or 4
    except Exception:
        cpu_count = 4

    # Try to read RAM
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        ram_gb = int(parts[1]) // (1024 * 1024)
                        break
            else:
                ram_gb = 8
    except Exception:
        ram_gb = 8

    # Encode workers: limited by RAM (each encode can use 2-4GB)
    encode_workers = max(1, min(cpu_count // 2, ram_gb // 4))

    # Integrity workers: limited by I/O, typically 2-4 is good
    integrity_workers = min(4, cpu_count // 2, encode_workers * 2)

    return encode_workers, integrity_workers
