"""
Tests for the converter module.
"""

import shutil

import pytest


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
            need_v=True, need_a=False, aidx=0, add_silence=False,
            reason_v="test", vcodec="hevc", vpix="yuv420p", vbit=8,
            vhdr=False, vprof="main", vlevel=51, acodec="aac", ach=2,
            format_name="matroska"
        )

        tag = get_output_tag(decision)
        assert tag == ".h264"

    def test_get_output_tag_audio_only(self):
        """Test tag for audio-only transcode."""
        from mkv2cast.converter import Decision, get_output_tag

        decision = Decision(
            need_v=False, need_a=True, aidx=0, add_silence=False,
            reason_v="", vcodec="h264", vpix="yuv420p", vbit=8,
            vhdr=False, vprof="high", vlevel=41, acodec="ac3", ach=6,
            format_name="matroska"
        )

        tag = get_output_tag(decision)
        assert tag == ".aac"

    def test_get_output_tag_both(self):
        """Test tag for video+audio transcode."""
        from mkv2cast.converter import Decision, get_output_tag

        decision = Decision(
            need_v=True, need_a=True, aidx=0, add_silence=False,
            reason_v="test", vcodec="hevc", vpix="yuv420p", vbit=8,
            vhdr=False, vprof="main", vlevel=51, acodec="ac3", ach=6,
            format_name="matroska"
        )

        tag = get_output_tag(decision)
        assert tag == ".h264.aac"

    def test_get_output_tag_remux(self):
        """Test tag for remux only."""
        from mkv2cast.converter import Decision, get_output_tag

        decision = Decision(
            need_v=False, need_a=False, aidx=0, add_silence=False,
            reason_v="", vcodec="h264", vpix="yuv420p", vbit=8,
            vhdr=False, vprof="high", vlevel=41, acodec="aac", ach=2,
            format_name="matroska"
        )

        tag = get_output_tag(decision)
        assert tag == ".remux"
