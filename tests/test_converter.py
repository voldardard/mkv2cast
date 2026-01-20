"""
Tests for the converter module.
"""

import shutil
import threading

import pytest


class TestProgressParsing:
    """Tests for FFmpeg progress parsing."""

    def test_parse_ffmpeg_progress_basic(self):
        """Test basic progress parsing."""
        from mkv2cast.converter import parse_ffmpeg_progress

        line = "frame=  100 fps=30.0 q=28.0 size=   1234kB time=00:00:10.00 bitrate=1000kbits/s speed=2.5x"
        result = parse_ffmpeg_progress(line, 60000)  # 60 seconds duration

        assert result["frame"] == 100
        assert result["fps"] == 30.0
        assert result["current_time_ms"] == 10000
        assert result["bitrate"] == "1000kbits/s"
        assert result["speed"] == "2.5x"
        assert abs(result["progress_percent"] - 16.67) < 0.1

    def test_parse_ffmpeg_progress_no_duration(self):
        """Test progress parsing with no duration."""
        from mkv2cast.converter import parse_ffmpeg_progress

        line = "frame=  100 fps=30.0 time=00:00:10.00"
        result = parse_ffmpeg_progress(line, 0)

        assert result["progress_percent"] == 0.0
        assert result["current_time_ms"] == 10000

    def test_parse_ffmpeg_progress_empty_line(self):
        """Test progress parsing with empty line."""
        from mkv2cast.converter import parse_ffmpeg_progress

        result = parse_ffmpeg_progress("", 60000)

        assert result["progress_percent"] == 0.0
        assert result["fps"] == 0.0

    def test_parse_ffmpeg_progress_time_comma_decimal(self):
        """Test parsing time when ffmpeg uses comma as decimal separator."""
        from mkv2cast.converter import parse_ffmpeg_progress

        line = "frame=  100 fps=25 time=00:01:30,50 speed=2.5x"
        result = parse_ffmpeg_progress(line, 180000)  # 3 min duration

        assert result["current_time_ms"] == 90500
        assert result["speed"] == "2.5x"
        assert abs(result["progress_percent"] - 50.0) < 0.5

    def test_calculate_eta(self):
        """Test ETA calculation."""
        import time

        from mkv2cast.converter import calculate_eta

        start = time.time() - 10  # Started 10 seconds ago
        eta = calculate_eta(30000, 60000, "2.0x", start)  # 50% done at 2x speed

        # At 2x speed, 30 seconds remaining should take 15 seconds
        assert 10 < eta < 20


class TestMakeProgressDict:
    """Tests for progress dictionary creation."""

    def test_make_progress_dict_encoding(self):
        """Test creating encoding progress dict."""
        from mkv2cast.converter import _make_progress_dict

        result = _make_progress_dict(
            stage="encoding",
            progress_percent=50.0,
            fps=120.5,
            eta_seconds=30.0,
            bitrate="2500kbits/s",
            speed="2.5x",
            current_time_ms=30000,
            duration_ms=60000,
        )

        assert result["stage"] == "encoding"
        assert result["progress_percent"] == 50.0
        assert result["fps"] == 120.5
        assert result["eta_seconds"] == 30.0
        assert result["error"] is None

    def test_make_progress_dict_failed(self):
        """Test creating failed progress dict."""
        from mkv2cast.converter import _make_progress_dict

        result = _make_progress_dict(stage="failed", error="Test error")

        assert result["stage"] == "failed"
        assert result["error"] == "Test error"


class TestScriptModeDetection:
    """Tests for script mode detection."""

    def test_is_script_mode_with_no_color_env(self, monkeypatch):
        """Test script mode detection with NO_COLOR env."""
        from mkv2cast.config import is_script_mode

        monkeypatch.setenv("NO_COLOR", "1")
        assert is_script_mode() is True

    def test_is_script_mode_with_script_mode_env(self, monkeypatch):
        """Test script mode detection with MKV2CAST_SCRIPT_MODE env."""
        from mkv2cast.config import is_script_mode

        monkeypatch.setenv("MKV2CAST_SCRIPT_MODE", "1")
        assert is_script_mode() is True

    def test_config_for_library(self):
        """Test Config.for_library() factory."""
        from mkv2cast.config import Config

        config = Config.for_library(hw="vaapi", crf=18)

        assert config.hw == "vaapi"
        assert config.crf == 18
        assert config.progress is False
        assert config.notify is False
        assert config.pipeline is False

    def test_config_apply_script_mode(self, monkeypatch):
        """Test Config.apply_script_mode() method."""
        from mkv2cast.config import Config

        monkeypatch.setenv("NO_COLOR", "1")

        config = Config(progress=True, notify=True, pipeline=True)
        config.apply_script_mode()

        assert config.progress is False
        assert config.notify is False
        assert config.pipeline is False


class TestConvertFileCallback:
    """Tests for convert_file with progress callback."""

    @pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not available")
    def test_convert_file_callback_called_for_skip(self, test_h264_mkv, default_config, temp_dir):
        """Test callback is called when file is skipped."""
        from mkv2cast.converter import convert_file

        callback_calls = []

        def callback(filepath, progress):
            callback_calls.append((filepath, progress.copy()))

        config = default_config
        config.skip_when_ok = True

        convert_file(
            test_h264_mkv,
            cfg=config,
            output_dir=temp_dir,
            progress_callback=callback,
        )

        # Should have at least checking and skipped stages
        assert len(callback_calls) >= 2
        stages = [call[1]["stage"] for call in callback_calls]
        assert "checking" in stages
        assert "skipped" in stages

    @pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not available")
    def test_convert_file_callback_receives_filepath(self, test_h264_mkv, default_config, temp_dir):
        """Test callback receives correct filepath."""
        from mkv2cast.converter import convert_file

        received_paths = []

        def callback(filepath, _progress):
            received_paths.append(filepath)

        convert_file(
            test_h264_mkv,
            cfg=default_config,
            output_dir=temp_dir,
            progress_callback=callback,
        )

        assert all(p == test_h264_mkv for p in received_paths)

    def test_convert_file_callback_error_handling(self, default_config, temp_dir):
        """Test callback errors don't stop conversion."""
        from mkv2cast.converter import convert_file

        def buggy_callback(_filepath, _progress):
            raise RuntimeError("Bug!")

        # Create a non-existent file path
        fake_path = temp_dir / "nonexistent.mkv"

        # Should not raise even though callback throws
        success, _output, _msg = convert_file(
            fake_path,
            cfg=default_config,
            progress_callback=buggy_callback,
        )

        # Conversion should fail (file doesn't exist), but not because of callback
        assert success is False


class TestConvertBatch:
    """Tests for convert_batch function."""

    def test_convert_batch_empty_list(self, default_config):
        """Test convert_batch with empty list."""
        from mkv2cast.converter import convert_batch

        results = convert_batch([], cfg=default_config)
        assert results == {}

    def test_convert_batch_nonexistent_files(self, default_config):
        """Test convert_batch with non-existent files."""
        from pathlib import Path

        from mkv2cast.converter import convert_batch

        files = [Path("/nonexistent/file1.mkv"), Path("/nonexistent/file2.mkv")]
        results = convert_batch(files, cfg=default_config)

        assert len(results) == 2
        for _, (success, _, _) in results.items():
            assert success is False

    @pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not available")
    def test_convert_batch_with_callback(self, test_h264_mkv, default_config, temp_dir):
        """Test convert_batch with progress callback."""
        from mkv2cast.converter import convert_batch

        callback_calls = []
        lock = threading.Lock()

        def callback(filepath, progress):
            with lock:
                callback_calls.append((filepath, progress.copy()))

        config = default_config
        config.encode_workers = 1

        results = convert_batch(
            [test_h264_mkv],
            cfg=config,
            output_dir=temp_dir,
            progress_callback=callback,
        )

        assert len(results) == 1
        assert len(callback_calls) > 0

    @pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not available")
    def test_convert_batch_thread_safety(self, test_h264_mkv, default_config, temp_dir):
        """Test convert_batch callback thread safety."""
        from mkv2cast.converter import convert_batch

        callback_threads = set()
        lock = threading.Lock()

        def callback(_filepath, _progress):
            with lock:
                callback_threads.add(threading.current_thread().name)

        config = default_config
        config.encode_workers = 2

        # Use same file twice (will be skipped second time)
        convert_batch(
            [test_h264_mkv],
            cfg=config,
            output_dir=temp_dir,
            progress_callback=callback,
        )

        # Should have recorded thread(s)
        assert len(callback_threads) >= 1


class TestCodecDetection:
    """Tests for codec detection functions."""

    def test_parse_bitdepth_8bit(self):
        """Test 8-bit pixel format detection."""
        from mkv2cast.converter import parse_bitdepth_from_pix

        assert parse_bitdepth_from_pix("yuv420p") == 8
        assert parse_bitdepth_from_pix("yuvj420p") == 8
        assert parse_bitdepth_from_pix("rgb24") == 8

    def test_parse_bitdepth_10bit(self):
        """Test 10-bit pixel format detection."""
        from mkv2cast.converter import parse_bitdepth_from_pix

        assert parse_bitdepth_from_pix("yuv420p10le") == 10
        assert parse_bitdepth_from_pix("p010le") == 10
        assert parse_bitdepth_from_pix("p010") == 10

    def test_parse_bitdepth_12bit(self):
        """Test 12-bit pixel format detection."""
        from mkv2cast.converter import parse_bitdepth_from_pix

        assert parse_bitdepth_from_pix("yuv420p12le") == 12

    def test_is_audio_description(self):
        """Test audio description detection."""
        from mkv2cast.converter import is_audio_description

        # These should be detected as audio descriptions
        assert is_audio_description("Audio Description") is True
        assert is_audio_description("audiodescription") is True
        assert is_audio_description("Visual Impaired") is True
        assert is_audio_description("English AD") is True
        assert is_audio_description("Track V.I") is True

        # These should NOT be detected
        assert is_audio_description("French Stereo") is False
        assert is_audio_description("English 5.1") is False
        assert is_audio_description("Dolby Surround") is False


class TestBackendSelection:
    """Tests for backend selection."""

    def test_pick_backend_cpu_explicit(self, default_config):
        """Test explicit CPU backend selection."""
        from mkv2cast.config import Config
        from mkv2cast.converter import pick_backend

        cfg = Config(hw="cpu")
        backend = pick_backend(cfg)
        assert backend == "cpu"

    def test_pick_backend_vaapi_explicit(self, default_config):
        """Test explicit VAAPI backend selection."""
        from mkv2cast.config import Config
        from mkv2cast.converter import pick_backend

        cfg = Config(hw="vaapi")
        backend = pick_backend(cfg)
        assert backend == "vaapi"

    def test_pick_backend_qsv_explicit(self, default_config):
        """Test explicit QSV backend selection."""
        from mkv2cast.config import Config
        from mkv2cast.converter import pick_backend

        cfg = Config(hw="qsv")
        backend = pick_backend(cfg)
        assert backend == "qsv"

    @pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not available")
    def test_have_encoder(self):
        """Test encoder availability check."""
        from mkv2cast.converter import have_encoder

        # libx264 should be available on most systems
        assert have_encoder("libx264") is True
        # Non-existent encoder
        assert have_encoder("nonexistent_encoder") is False


class TestVideoArgs:
    """Tests for video argument generation."""

    def test_video_args_cpu(self, default_config):
        """Test CPU video arguments."""
        from mkv2cast.config import Config
        from mkv2cast.converter import video_args_for

        cfg = Config(preset="slow", crf=20)
        args = video_args_for("cpu", cfg)

        assert "-c:v" in args
        assert "libx264" in args
        assert "-preset" in args
        assert "slow" in args
        assert "-crf" in args
        assert "20" in args
        assert "-profile:v" in args
        assert "high" in args

    def test_video_args_vaapi(self, default_config):
        """Test VAAPI video arguments."""
        from mkv2cast.config import Config
        from mkv2cast.converter import video_args_for

        cfg = Config(vaapi_device="/dev/dri/renderD128", vaapi_qp=23)
        args = video_args_for("vaapi", cfg)

        assert "-vaapi_device" in args
        assert "/dev/dri/renderD128" in args
        assert "-c:v" in args
        assert "h264_vaapi" in args
        assert "-qp" in args
        assert "23" in args

    def test_video_args_qsv(self, default_config):
        """Test QSV video arguments."""
        from mkv2cast.config import Config
        from mkv2cast.converter import video_args_for

        cfg = Config(qsv_quality=23)
        args = video_args_for("qsv", cfg)

        assert "-c:v" in args
        assert "h264_qsv" in args
        assert "-global_quality" in args
        assert "23" in args


class TestDecision:
    """Tests for conversion decision logic."""

    @pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not available")
    def test_decide_for_h265_needs_transcode(self, test_sample_mkv, default_config):
        """Test that H.265 file needs transcoding."""
        from mkv2cast.config import Config
        from mkv2cast.converter import decide_for

        cfg = Config()
        decision = decide_for(test_sample_mkv, cfg)

        # H.265 should need video transcoding by default
        assert decision.vcodec in ("hevc", "h265")
        assert decision.need_v is True

    @pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not available")
    def test_decide_for_h264_compatible(self, test_h264_mkv, default_config):
        """Test that compatible H.264 file is skipped."""
        from mkv2cast.config import Config
        from mkv2cast.converter import decide_for

        cfg = Config()
        decision = decide_for(test_h264_mkv, cfg)

        assert decision.vcodec == "h264"
        assert decision.need_v is False  # H.264 8-bit SDR should be OK

    @pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not available")
    def test_decide_for_force_h264(self, test_h264_mkv, default_config):
        """Test force-h264 flag."""
        from mkv2cast.config import Config
        from mkv2cast.converter import decide_for

        cfg = Config(force_h264=True)
        decision = decide_for(test_h264_mkv, cfg)

        assert decision.need_v is True  # Forced transcode
        assert "force-h264" in decision.reason_v.lower()


class TestBuildCommand:
    """Tests for ffmpeg command building."""

    @pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not available")
    def test_build_transcode_cmd_mkv(self, test_sample_mkv, temp_dir, default_config):
        """Test command building for MKV output."""
        from mkv2cast.config import Config
        from mkv2cast.converter import build_transcode_cmd, decide_for

        cfg = Config(container="mkv")
        decision = decide_for(test_sample_mkv, cfg)
        tmp_out = temp_dir / "output.mkv"

        cmd, stage = build_transcode_cmd(test_sample_mkv, decision, "cpu", tmp_out, cfg=cfg)

        assert cmd[0] == "ffmpeg"
        assert "-f" in cmd
        assert "matroska" in cmd
        assert str(tmp_out) in cmd

    @pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not available")
    def test_build_transcode_cmd_mp4(self, test_sample_mkv, temp_dir, default_config):
        """Test command building for MP4 output."""
        from mkv2cast.config import Config
        from mkv2cast.converter import build_transcode_cmd, decide_for

        cfg = Config(container="mp4")
        decision = decide_for(test_sample_mkv, cfg)
        tmp_out = temp_dir / "output.mp4"

        cmd, stage = build_transcode_cmd(test_sample_mkv, decision, "cpu", tmp_out, cfg=cfg)

        assert cmd[0] == "ffmpeg"
        assert "-f" in cmd
        assert "mp4" in cmd
        assert "+faststart" in cmd or "faststart" in str(cmd)


class TestGetOutputTag:
    """Tests for output filename tag generation."""

    def test_get_output_tag_video_only(self):
        """Test tag for video-only transcode."""
        from mkv2cast.converter import Decision, get_output_tag

        decision = Decision(
            need_v=True,
            need_a=False,
            aidx=0,
            add_silence=False,
            reason_v="test",
            vcodec="hevc",
            vpix="yuv420p",
            vbit=8,
            vhdr=False,
            vprof="main",
            vlevel=51,
            acodec="aac",
            ach=2,
            alang="fre",
            format_name="matroska",
        )

        tag = get_output_tag(decision)
        assert tag == ".h264"

    def test_get_output_tag_audio_only(self):
        """Test tag for audio-only transcode."""
        from mkv2cast.converter import Decision, get_output_tag

        decision = Decision(
            need_v=False,
            need_a=True,
            aidx=0,
            add_silence=False,
            reason_v="",
            vcodec="h264",
            vpix="yuv420p",
            vbit=8,
            vhdr=False,
            vprof="high",
            vlevel=41,
            acodec="ac3",
            ach=6,
            alang="eng",
            format_name="matroska",
        )

        tag = get_output_tag(decision)
        assert tag == ".aac"

    def test_get_output_tag_both(self):
        """Test tag for video+audio transcode."""
        from mkv2cast.converter import Decision, get_output_tag

        decision = Decision(
            need_v=True,
            need_a=True,
            aidx=0,
            add_silence=False,
            reason_v="test",
            vcodec="hevc",
            vpix="yuv420p",
            vbit=8,
            vhdr=False,
            vprof="main",
            vlevel=51,
            acodec="ac3",
            ach=6,
            alang="fre",
            format_name="matroska",
        )

        tag = get_output_tag(decision)
        assert tag == ".h264.aac"

    def test_get_output_tag_remux(self):
        """Test tag for remux only."""
        from mkv2cast.converter import Decision, get_output_tag

        decision = Decision(
            need_v=False,
            need_a=False,
            aidx=0,
            add_silence=False,
            reason_v="",
            vcodec="h264",
            vpix="yuv420p",
            vbit=8,
            vhdr=False,
            vprof="high",
            vlevel=41,
            acodec="aac",
            ach=2,
            alang="eng",
            format_name="matroska",
        )

        tag = get_output_tag(decision)
        assert tag == ".remux"
