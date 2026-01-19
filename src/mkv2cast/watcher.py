"""
Watch mode for mkv2cast.

Monitors directories for new MKV files and automatically converts them.
Uses watchdog library if available, falls back to polling otherwise.
"""

import os
import time
from pathlib import Path
from threading import Event, Thread
from typing import TYPE_CHECKING, Any, Callable, Optional, Set

from mkv2cast.config import Config
from mkv2cast.integrity import check_file_stable

# Try to import watchdog for efficient file system monitoring
if TYPE_CHECKING:
    from watchdog.events import FileCreatedEvent, FileMovedEvent, FileSystemEventHandler
    from watchdog.observers import Observer

try:
    from watchdog.events import FileCreatedEvent, FileMovedEvent, FileSystemEventHandler
    from watchdog.observers import Observer

    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    # Type stubs for mypy
    Observer = None  # type: ignore
    FileSystemEventHandler = None  # type: ignore
    FileCreatedEvent = None  # type: ignore
    FileMovedEvent = None  # type: ignore


class MKVFileHandler:
    """Handler for new MKV files."""

    def __init__(
        self,
        convert_callback: Callable[[Path], None],
        cfg: Config,
        stable_wait: int = 5,
    ):
        """
        Initialize the handler.

        Args:
            convert_callback: Function to call when a new MKV file is detected.
            cfg: Configuration instance.
            stable_wait: Seconds to wait for file to stabilize.
        """
        self.convert_callback = convert_callback
        self.cfg = cfg
        self.stable_wait = stable_wait
        self.processing: Set[Path] = set()
        self._lock = __import__("threading").Lock()

    def handle_file(self, filepath: Path) -> None:
        """Handle a new or moved file."""
        # Only process MKV files
        if not filepath.suffix.lower() == ".mkv":
            return

        # Skip our output files
        name = filepath.name
        if ".tmp." in name or self.cfg.suffix in name:
            return
        if ".h264." in name or ".aac." in name or ".remux." in name:
            return

        # Check if already processing
        with self._lock:
            if filepath in self.processing:
                return
            self.processing.add(filepath)

        try:
            # Wait for file to be stable (not being written)
            if not check_file_stable(filepath, wait_seconds=self.stable_wait):
                return

            # Convert the file
            self.convert_callback(filepath)

        finally:
            with self._lock:
                self.processing.discard(filepath)


if WATCHDOG_AVAILABLE:

    class WatchdogHandler(FileSystemEventHandler):
        """Watchdog event handler for MKV files."""

        def __init__(self, mkv_handler: MKVFileHandler):
            super().__init__()
            self.mkv_handler = mkv_handler

        def on_created(self, event: "FileCreatedEvent") -> None:  # type: ignore[override]
            if not event.is_directory:
                # Run in thread to not block the observer
                src_path = str(event.src_path) if isinstance(event.src_path, bytes) else event.src_path
                Thread(
                    target=self.mkv_handler.handle_file,
                    args=(Path(src_path),),
                    daemon=True,
                ).start()

        def on_moved(self, event: "FileMovedEvent") -> None:  # type: ignore[override]
            if not event.is_directory:
                # Handle files moved into watched directory
                dest_path = str(event.dest_path) if isinstance(event.dest_path, bytes) else event.dest_path
                Thread(
                    target=self.mkv_handler.handle_file,
                    args=(Path(dest_path),),
                    daemon=True,
                ).start()


class DirectoryWatcher:
    """
    Watch a directory for new MKV files.

    Uses watchdog if available, otherwise falls back to polling.
    """

    def __init__(
        self,
        watch_path: Path,
        convert_callback: Callable[[Path], None],
        cfg: Config,
        interval: float = 5.0,
        recursive: bool = True,
    ):
        """
        Initialize the watcher.

        Args:
            watch_path: Directory to watch.
            convert_callback: Function to call for each new MKV file.
            cfg: Configuration instance.
            interval: Polling interval in seconds (for fallback mode).
            recursive: Watch subdirectories.
        """
        self.watch_path = watch_path
        self.convert_callback = convert_callback
        self.cfg = cfg
        self.interval = interval
        self.recursive = recursive
        self.stop_event = Event()
        self._observer: Optional[Any] = None
        self._poll_thread: Optional[Thread] = None

        self.mkv_handler = MKVFileHandler(
            convert_callback=convert_callback,
            cfg=cfg,
            stable_wait=cfg.stable_wait,
        )

    def start(self) -> None:
        """Start watching the directory."""
        if WATCHDOG_AVAILABLE:
            self._start_watchdog()
        else:
            self._start_polling()

    def _start_watchdog(self) -> None:
        """Start watching using watchdog."""
        if not WATCHDOG_AVAILABLE:
            return
        handler = WatchdogHandler(self.mkv_handler)
        observer = Observer()
        observer.schedule(handler, str(self.watch_path), recursive=self.recursive)
        observer.start()
        self._observer = observer

    def _start_polling(self) -> None:
        """Start watching using polling (fallback)."""
        self._known_files: Set[Path] = set()

        # Initial scan
        self._scan_directory()

        # Start polling thread
        poll_thread = Thread(target=self._polling_loop, daemon=True)
        poll_thread.start()
        self._poll_thread = poll_thread

    def _scan_directory(self) -> Set[Path]:
        """Scan directory for MKV files."""
        found = set()
        try:
            if self.recursive:
                for root, _dirs, files in os.walk(self.watch_path):
                    for f in files:
                        if f.lower().endswith(".mkv"):
                            found.add(Path(root) / f)
            else:
                for item in self.watch_path.iterdir():
                    if item.is_file() and item.suffix.lower() == ".mkv":
                        found.add(item)
        except OSError:
            pass
        return found

    def _polling_loop(self) -> None:
        """Polling loop for fallback mode."""
        while not self.stop_event.is_set():
            time.sleep(self.interval)

            current_files = self._scan_directory()
            new_files = current_files - self._known_files

            for filepath in new_files:
                Thread(
                    target=self.mkv_handler.handle_file,
                    args=(filepath,),
                    daemon=True,
                ).start()

            self._known_files = current_files

    def stop(self) -> None:
        """Stop watching."""
        self.stop_event.set()

        if self._observer is not None:
            # Observer has stop() and join() methods
            self._observer.stop()  # type: ignore[attr-defined]
            self._observer.join(timeout=5)  # type: ignore[attr-defined]

        if self._poll_thread is not None:
            self._poll_thread.join(timeout=5)

    def wait(self) -> None:
        """Wait until stopped (blocks)."""
        try:
            while not self.stop_event.is_set():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass


def watch_directory(
    path: Path,
    convert_callback: Callable[[Path], None],
    cfg: Config,
    interval: float = 5.0,
    print_fn: Optional[Callable[[str], None]] = None,
) -> None:
    """
    Watch a directory for new MKV files and convert them.

    This function blocks until interrupted (Ctrl+C).

    Args:
        path: Directory to watch.
        convert_callback: Function to call for each new MKV file.
        cfg: Configuration instance.
        interval: Polling interval in seconds.
        print_fn: Optional function to print status messages.
    """
    if print_fn is None:
        print_fn = print

    if not path.is_dir():
        print_fn(f"Error: {path} is not a directory")
        return

    mode = "watchdog" if WATCHDOG_AVAILABLE else "polling"
    recursive = "recursive" if cfg.recursive else "non-recursive"

    print_fn(f"Watching {path} ({mode}, {recursive})")
    print_fn("Press Ctrl+C to stop")
    print_fn("")

    watcher = DirectoryWatcher(
        watch_path=path,
        convert_callback=convert_callback,
        cfg=cfg,
        interval=interval,
        recursive=cfg.recursive,
    )

    try:
        watcher.start()
        watcher.wait()
    except KeyboardInterrupt:
        print_fn("\nStopping watcher...")
    finally:
        watcher.stop()
        print_fn("Watcher stopped.")
