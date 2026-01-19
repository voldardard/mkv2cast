"""Tests for UI modules."""

from pathlib import Path

import pytest


class TestLegacyUI:
    """Tests for legacy UI."""

    def test_fmt_hms(self):
        """Test fmt_hms time formatting."""
        from mkv2cast.ui.legacy_ui import fmt_hms

        assert fmt_hms(0) == "00:00:00"
        assert fmt_hms(59) == "00:00:59"
        assert fmt_hms(60) == "00:01:00"
        assert fmt_hms(3661) == "01:01:01"
        assert fmt_hms(-5) == "00:00:00"  # Negative should be 0

    def test_shorten(self):
        """Test shorten string truncation."""
        from mkv2cast.ui.legacy_ui import shorten

        assert shorten("short", 10) == "short"
        assert shorten("verylongstring", 10) == "verylon..."  # 7 chars + ...
        assert shorten("abc", 3) == "abc"
        assert shorten("abcdef", 0) == ""

    def test_mkbar(self):
        """Test mkbar progress bar generation."""
        from mkv2cast.ui.legacy_ui import mkbar

        bar_0 = mkbar(0, 10)
        assert bar_0 == "-" * 10

        bar_100 = mkbar(100, 10)
        assert bar_100 == "#" * 10

        bar_50 = mkbar(50, 10)
        assert bar_50 == "#" * 5 + "-" * 5

    def test_term_width(self):
        """Test term_width returns reasonable value."""
        from mkv2cast.ui.legacy_ui import term_width

        width = term_width()
        assert isinstance(width, int)
        assert width > 0

    def test_legacy_ui_init(self):
        """Test LegacyProgressUI initialization."""
        from mkv2cast.ui.legacy_ui import LegacyProgressUI

        ui = LegacyProgressUI(progress=True, bar_width=20)
        assert ui.bar_width == 20
        assert ui.ok == 0
        assert ui.skipped == 0
        assert ui.failed == 0

    def test_legacy_ui_stats(self):
        """Test LegacyProgressUI stats tracking."""
        from mkv2cast.ui.legacy_ui import LegacyProgressUI

        ui = LegacyProgressUI(progress=False)
        ui.inc_ok()
        ui.inc_ok()
        ui.inc_skipped()
        ui.inc_failed()

        ok, skipped, failed, processed = ui.get_stats()
        assert ok == 2
        assert skipped == 1
        assert failed == 1
        assert processed == 4

    def test_ui_state(self):
        """Test UIState dataclass."""
        from mkv2cast.ui.legacy_ui import UIState

        state = UIState(stage="ENCODE", pct=50, cur=1, total=3, base="video.mkv", eta="00:05:00", speed="2.5x")

        assert state.stage == "ENCODE"
        assert state.pct == 50


class TestRichUI:
    """Tests for Rich UI (if available)."""

    @pytest.fixture
    def skip_if_no_rich(self):
        """Skip test if rich is not available."""
        pytest.importorskip("rich")

    def test_rich_available(self):
        """Test RICH_AVAILABLE flag."""
        from mkv2cast.ui import RICH_AVAILABLE

        # Just verify it's a boolean
        assert isinstance(RICH_AVAILABLE, bool)

    def test_rich_progress_ui_init(self, skip_if_no_rich):
        """Test RichProgressUI initialization."""
        from mkv2cast.ui.rich_ui import RichProgressUI

        ui = RichProgressUI(total_files=10, encode_workers=2, integrity_workers=3)

        assert ui.total_files == 10
        assert ui.encode_workers == 2
        assert ui.integrity_workers == 3
        assert ui.ok == 0
        assert ui.skipped == 0
        assert ui.failed == 0

    def test_rich_progress_ui_register_job(self, skip_if_no_rich):
        """Test job registration."""
        from mkv2cast.ui.rich_ui import RichProgressUI

        ui = RichProgressUI(total_files=1, encode_workers=1, integrity_workers=1)
        test_path = Path("/test/video.mkv")

        ui.register_job(test_path, backend="vaapi")

        assert str(test_path) in ui.jobs
        assert ui.jobs[str(test_path)].stage == "WAITING"

    def test_rich_progress_ui_mark_done(self, skip_if_no_rich):
        """Test marking job as done."""
        from mkv2cast.ui.rich_ui import RichProgressUI

        ui = RichProgressUI(total_files=1, encode_workers=1, integrity_workers=1)
        test_path = Path("/test/video.mkv")

        ui.register_job(test_path)
        ui.mark_done(test_path, final_path=Path("/test/video.cast.mkv"))

        assert ui.ok == 1
        assert ui.jobs[str(test_path)].stage == "DONE"

    def test_rich_progress_ui_mark_skipped(self, skip_if_no_rich):
        """Test marking job as skipped."""
        from mkv2cast.ui.rich_ui import RichProgressUI

        ui = RichProgressUI(total_files=1, encode_workers=1, integrity_workers=1)
        test_path = Path("/test/video.mkv")

        ui.register_job(test_path)
        ui.mark_skipped(test_path, reason="output exists")

        assert ui.skipped == 1
        assert ui.jobs[str(test_path)].stage == "SKIPPED"
        assert ui.jobs[str(test_path)].result_msg == "output exists"

    def test_rich_progress_ui_mark_failed(self, skip_if_no_rich):
        """Test marking job as failed."""
        from mkv2cast.ui.rich_ui import RichProgressUI

        ui = RichProgressUI(total_files=1, encode_workers=1, integrity_workers=1)
        test_path = Path("/test/video.mkv")

        ui.register_job(test_path)
        ui.mark_failed(test_path, reason="encode error")

        assert ui.failed == 1
        assert ui.jobs[str(test_path)].stage == "FAILED"

    def test_rich_progress_ui_stats(self, skip_if_no_rich):
        """Test stats retrieval."""
        from mkv2cast.ui.rich_ui import RichProgressUI

        ui = RichProgressUI(total_files=3, encode_workers=1, integrity_workers=1)

        # Register and complete jobs
        for i, status in enumerate(["done", "skipped", "failed"]):
            path = Path(f"/test/video{i}.mkv")
            ui.register_job(path)
            if status == "done":
                ui.mark_done(path)
            elif status == "skipped":
                ui.mark_skipped(path, "test")
            else:
                ui.mark_failed(path, "test")

        ok, skipped, failed, processed = ui.get_stats()
        assert ok == 1
        assert skipped == 1
        assert failed == 1
        assert processed == 3


class TestSimpleRichUI:
    """Tests for SimpleRichUI (if available)."""

    def test_simple_rich_ui_init(self):
        """Test SimpleRichUI initialization."""
        pytest.importorskip("rich")
        from mkv2cast.ui.simple_rich import SimpleRichUI

        ui = SimpleRichUI(progress_enabled=True)
        assert ui.ok == 0
        assert ui.skipped == 0
        assert ui.failed == 0

    def test_simple_rich_ui_stats(self):
        """Test SimpleRichUI stats tracking."""
        pytest.importorskip("rich")
        from mkv2cast.ui.simple_rich import SimpleRichUI

        ui = SimpleRichUI(progress_enabled=False)
        ui.inc_ok()
        ui.inc_skipped()
        ui.inc_failed()

        ok, skipped, failed, processed = ui.get_stats()
        assert ok == 1
        assert skipped == 1
        assert failed == 1
        assert processed == 3

    def test_parse_ffmpeg_progress(self):
        """Test ffmpeg progress parsing."""
        pytest.importorskip("rich")
        from mkv2cast.ui.simple_rich import SimpleRichUI

        ui = SimpleRichUI(progress_enabled=False)

        line = "frame=  100 fps=25 q=28.0 time=00:00:30.00 speed=2.0x"
        pct, speed = ui._parse_ffmpeg_progress(line, 60000)  # 1 min duration

        assert pct == 50  # 30s of 60s
        assert speed == "2.0x"
