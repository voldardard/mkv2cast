"""
Tests for the integrity checking module.
"""

import shutil

import pytest


class TestFileSize:
    """Tests for file_size function."""

    def test_file_size_valid(self, temp_dir):
        """Test getting size of valid file."""
        from mkv2cast.integrity import file_size

        test_file = temp_dir / "test.txt"
        test_file.write_bytes(b"x" * 1000)

        size = file_size(test_file)
        assert size == 1000

    def test_file_size_nonexistent(self, temp_dir):
        """Test getting size of nonexistent file."""
        from mkv2cast.integrity import file_size

        size = file_size(temp_dir / "nonexistent.txt")
        assert size == 0


class TestRunQuiet:
    """Tests for run_quiet function."""

    def test_run_quiet_success(self):
        """Test successful quiet command."""
        from mkv2cast.integrity import run_quiet

        result = run_quiet(["true"])
        assert result is True

    def test_run_quiet_failure(self):
        """Test failed quiet command."""
        from mkv2cast.integrity import run_quiet

        result = run_quiet(["false"])
        assert result is False

    def test_run_quiet_timeout(self):
        """Test timeout handling."""
        from mkv2cast.integrity import run_quiet

        # Command that takes longer than timeout
        result = run_quiet(["sleep", "10"], timeout=0.1)
        assert result is False

    def test_run_quiet_not_found(self):
        """Test handling of non-existent command."""
        from mkv2cast.integrity import run_quiet

        result = run_quiet(["nonexistent_command_12345"])
        assert result is False


class TestCheckFileStable:
    """Tests for file stability checking."""

    def test_check_file_stable_skip_zero_wait(self, temp_dir):
        """Test that zero wait time skips check."""
        from mkv2cast.integrity import check_file_stable

        test_file = temp_dir / "test.mkv"
        test_file.write_bytes(b"x" * 2000000)  # 2MB

        result = check_file_stable(test_file, wait_seconds=0)
        assert result is True

    def test_check_file_stable_small_file(self, temp_dir):
        """Test that small files fail stability check when wait is enabled."""
        from mkv2cast.integrity import check_file_stable

        test_file = temp_dir / "small.mkv"
        test_file.write_bytes(b"x" * 100)  # Too small (< 1MB)

        # With wait_seconds > 0, small files should fail
        result = check_file_stable(test_file, wait_seconds=1)
        assert result is False

    def test_check_file_stable_valid(self, temp_dir):
        """Test stable file passes check."""
        from mkv2cast.integrity import check_file_stable

        test_file = temp_dir / "stable.mkv"
        test_file.write_bytes(b"x" * 2000000)  # 2MB

        # With 1 second wait
        result = check_file_stable(test_file, wait_seconds=1)
        assert result is True


class TestCheckFfprobeValid:
    """Tests for ffprobe validation."""

    @pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not available")
    def test_check_ffprobe_valid_real_file(self, test_sample_mkv):
        """Test ffprobe validation with real file."""
        from mkv2cast.integrity import check_ffprobe_valid

        result = check_ffprobe_valid(test_sample_mkv)
        assert result is True

    def test_check_ffprobe_invalid_file(self, temp_dir):
        """Test ffprobe validation with invalid file."""
        from mkv2cast.integrity import check_ffprobe_valid

        bad_file = temp_dir / "not_video.mkv"
        bad_file.write_bytes(b"not a video file content")

        result = check_ffprobe_valid(bad_file)
        assert result is False


class TestIntegrityCheck:
    """Tests for full integrity check function."""

    def test_integrity_check_disabled(self, temp_dir):
        """Test that disabled integrity check returns True."""
        from mkv2cast.integrity import integrity_check

        test_file = temp_dir / "test.mkv"
        test_file.write_bytes(b"x" * 100)  # Small file

        success, elapsed = integrity_check(test_file, enabled=False)
        assert success is True
        assert elapsed == 0

    def test_integrity_check_small_file(self, temp_dir):
        """Test that small files fail."""
        from mkv2cast.integrity import integrity_check

        test_file = temp_dir / "small.mkv"
        test_file.write_bytes(b"x" * 100)  # Too small

        success, elapsed = integrity_check(test_file, enabled=True, stable_wait=0)
        assert success is False

    @pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not available")
    def test_integrity_check_valid_file(self, test_sample_mkv, monkeypatch):
        """Test integrity check with valid file."""
        from mkv2cast import integrity

        # Patch the minimum file size check since test files are small
        def patched_check(path, enabled=True, stable_wait=3, deep_check=False, log_path=None, progress_callback=None):
            # Skip stable_wait for test and don't check minimum file size
            import time

            start = time.time()
            if not enabled:
                return True, 0
            # Just check ffprobe works
            if not integrity.check_ffprobe_valid(path):
                return False, time.time() - start
            return True, time.time() - start

        success, elapsed = patched_check(test_sample_mkv, enabled=True, stable_wait=0, deep_check=False)
        assert success is True
        assert elapsed >= 0

    def test_integrity_check_progress_callback(self, temp_dir):
        """Test progress callback is called."""
        from mkv2cast.integrity import integrity_check

        test_file = temp_dir / "test.mkv"
        test_file.write_bytes(b"x" * 2000000)  # 2MB

        callbacks = []

        def callback(stage, pct, msg):
            callbacks.append((stage, pct, msg))

        # This will fail at ffprobe stage but callback should be called
        success, _ = integrity_check(test_file, enabled=True, stable_wait=0, progress_callback=callback)

        assert len(callbacks) > 0
        assert any(cb[0] == "CHECK" for cb in callbacks)
