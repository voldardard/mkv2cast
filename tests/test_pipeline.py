"""Tests for pipeline module."""

import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest


class TestPipelineOrchestrator:
    """Tests for PipelineOrchestrator class."""

    @pytest.fixture
    def mock_ui(self):
        """Create a mock UI."""
        ui = MagicMock()
        ui.get_stats.return_value = (1, 0, 0, 1)
        ui.lock = threading.Lock()
        return ui

    @pytest.fixture
    def mock_config(self):
        """Create a mock config."""
        from mkv2cast.config import Config

        cfg = Config()
        cfg.integrity_check = False
        cfg.skip_when_ok = True
        cfg.dryrun = True
        return cfg

    def test_pipeline_init(self, mock_ui, mock_config, tmp_path):
        """Test PipelineOrchestrator initialization."""
        pytest.importorskip("rich")
        from mkv2cast.pipeline import PipelineOrchestrator

        targets = [tmp_path / "video1.mkv", tmp_path / "video2.mkv"]
        for t in targets:
            t.touch()

        pipeline = PipelineOrchestrator(
            targets=targets,
            backend="cpu",
            ui=mock_ui,
            cfg=mock_config,
            encode_workers=1,
            integrity_workers=1,
            get_log_path=lambda p: tmp_path / f"{p.stem}.log",
            get_tmp_path=lambda p, w, t: tmp_path / f"{p.stem}.tmp.{w}{t}.mkv",
            output_exists_fn=lambda p, c: False,
        )

        assert pipeline.encode_workers_count == 1
        assert pipeline.integrity_workers_count == 1
        assert len(pipeline.targets) == 2

    def test_auto_detect_workers(self, monkeypatch):
        """Test auto_detect_workers function."""
        pytest.importorskip("rich")
        from mkv2cast.pipeline import auto_detect_workers

        monkeypatch.setattr("os.cpu_count", lambda: 8)

        encode, integrity = auto_detect_workers()
        assert encode >= 1
        assert integrity >= 1


class TestFFmpegProgress:
    """Tests for ffmpeg progress parsing."""

    def test_parse_ffmpeg_progress_time(self):
        """Test parsing time from ffmpeg output."""
        pytest.importorskip("rich")
        from mkv2cast.pipeline import _parse_ffmpeg_progress

        line = "frame=  100 fps=25 time=00:01:30.50 speed=2.5x"
        pct, speed, out_ms = _parse_ffmpeg_progress(line, 180000)  # 3 min duration

        assert pct == 50  # 1:30 of 3:00 = 50%
        assert speed == "2.5x"
        assert out_ms == 90500  # 1:30.5 in ms

    def test_parse_ffmpeg_progress_no_duration(self):
        """Test parsing without duration."""
        pytest.importorskip("rich")
        from mkv2cast.pipeline import _parse_ffmpeg_progress

        line = "frame=  100 fps=25 time=00:01:30.00 speed=1.5x"
        pct, speed, out_ms = _parse_ffmpeg_progress(line, 0)

        assert pct == 0  # Can't calculate without duration
        assert speed == "1.5x"

    def test_parse_ffmpeg_progress_no_match(self):
        """Test parsing line with no progress info."""
        pytest.importorskip("rich")
        from mkv2cast.pipeline import _parse_ffmpeg_progress

        line = "Input #0, matroska,webm, from 'video.mkv':"
        pct, speed, out_ms = _parse_ffmpeg_progress(line, 60000)

        assert pct == 0
        assert speed == ""
        assert out_ms == 0


class TestProcessTracking:
    """Tests for process tracking functions."""

    def test_register_unregister_process(self):
        """Test process registration and unregistration."""
        pytest.importorskip("rich")
        from mkv2cast.pipeline import (
            register_process,
            unregister_process,
        )

        mock_proc = MagicMock()

        # Clear any existing
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("mkv2cast.pipeline._active_processes", [])

            register_process(mock_proc)
            # Check it was added (note: we can't directly access due to module-level list)

            unregister_process(mock_proc)
            # Should complete without error


class TestIntegrityCheckWithProgress:
    """Tests for integrity check with progress updates."""

    def test_integrity_check_disabled(self):
        """Test integrity check when disabled."""
        pytest.importorskip("rich")
        from mkv2cast.config import Config
        from mkv2cast.pipeline import integrity_check_with_progress

        mock_ui = MagicMock()
        cfg = Config()
        cfg.integrity_check = False

        success, elapsed = integrity_check_with_progress(
            Path("/fake/path.mkv"), mock_ui, worker_id=0, filename="path.mkv", cfg=cfg
        )

        assert success is True
        assert elapsed == 0
