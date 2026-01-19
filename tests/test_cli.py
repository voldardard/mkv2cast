"""Tests for CLI module."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock


class TestSystemDetection:
    """Tests for system detection functions."""

    def test_is_running_as_root_normal_user(self, monkeypatch):
        """Test is_running_as_root returns False for normal user."""
        from mkv2cast.cli import is_running_as_root

        monkeypatch.setattr(os, "geteuid", lambda: 1000)
        assert is_running_as_root() is False

    def test_is_running_as_root_as_root(self, monkeypatch):
        """Test is_running_as_root returns True for root."""
        from mkv2cast.cli import is_running_as_root

        monkeypatch.setattr(os, "geteuid", lambda: 0)
        assert is_running_as_root() is True

    def test_get_total_ram_gb(self):
        """Test get_total_ram_gb returns reasonable value."""
        from mkv2cast.cli import get_total_ram_gb

        ram = get_total_ram_gb()
        assert isinstance(ram, int)
        assert ram >= 1  # At least 1GB

    def test_get_total_ram_gb_fallback(self, monkeypatch, tmp_path):
        """Test get_total_ram_gb returns fallback when /proc/meminfo unavailable."""
        from mkv2cast.cli import get_total_ram_gb

        # Mock open to raise error
        def mock_open(*args, **kwargs):
            raise FileNotFoundError()

        monkeypatch.setattr("builtins.open", mock_open)
        ram = get_total_ram_gb()
        assert ram == 8  # Default fallback

    def test_get_gpu_info(self):
        """Test get_gpu_info returns tuple."""
        from mkv2cast.cli import get_gpu_info

        gpu_type, vram = get_gpu_info()
        assert isinstance(gpu_type, str)
        assert gpu_type in ("nvidia", "amd", "intel", "unknown")
        assert isinstance(vram, int)
        assert vram >= 0

    def test_auto_detect_workers_vaapi(self, monkeypatch):
        """Test auto_detect_workers for vaapi backend."""
        from mkv2cast.cli import auto_detect_workers

        monkeypatch.setattr("mkv2cast.cli.get_total_ram_gb", lambda: 16)
        monkeypatch.setattr("mkv2cast.cli.get_gpu_info", lambda: ("intel", 2048))
        monkeypatch.setattr("os.cpu_count", lambda: 8)

        encode, integrity = auto_detect_workers("vaapi")
        assert encode >= 1
        assert integrity >= encode

    def test_auto_detect_workers_cpu(self, monkeypatch):
        """Test auto_detect_workers for cpu backend."""
        from mkv2cast.cli import auto_detect_workers

        monkeypatch.setattr("mkv2cast.cli.get_total_ram_gb", lambda: 8)
        monkeypatch.setattr("os.cpu_count", lambda: 4)

        encode, integrity = auto_detect_workers("cpu")
        assert encode >= 1
        assert integrity >= 1


class TestFileFiltering:
    """Tests for file filtering functions."""

    def test_is_our_output_or_tmp_output(self):
        """Test is_our_output_or_tmp detects output files."""
        from mkv2cast.cli import is_our_output_or_tmp
        from mkv2cast.config import Config

        cfg = Config()
        assert is_our_output_or_tmp("video.cast.mkv", cfg) is True
        assert is_our_output_or_tmp("video.h264.cast.mkv", cfg) is True
        assert is_our_output_or_tmp("video.aac.cast.mkv", cfg) is True

    def test_is_our_output_or_tmp_tmp(self):
        """Test is_our_output_or_tmp detects temp files."""
        from mkv2cast.cli import is_our_output_or_tmp
        from mkv2cast.config import Config

        cfg = Config()
        assert is_our_output_or_tmp("video.tmp.12345.0.mkv", cfg) is True
        assert is_our_output_or_tmp("video.h264.cast.tmp.12345.0.mkv", cfg) is True

    def test_is_our_output_or_tmp_normal(self):
        """Test is_our_output_or_tmp ignores normal files."""
        from mkv2cast.cli import is_our_output_or_tmp
        from mkv2cast.config import Config

        cfg = Config()
        assert is_our_output_or_tmp("video.mkv", cfg) is False
        assert is_our_output_or_tmp("movie.mkv", cfg) is False

    def test_output_exists_for_input(self, tmp_path):
        """Test output_exists_for_input detection."""
        from mkv2cast.cli import output_exists_for_input
        from mkv2cast.config import Config

        cfg = Config()
        input_file = tmp_path / "video.mkv"
        input_file.touch()

        # No output exists
        assert output_exists_for_input(input_file, cfg) is False

        # Create output
        output_file = tmp_path / "video.cast.mkv"
        output_file.touch()
        assert output_exists_for_input(input_file, cfg) is True


class TestCollectTargets:
    """Tests for collect_targets function."""

    def test_collect_targets_single_file(self, tmp_path, monkeypatch):
        """Test collect_targets with single file argument."""
        from mkv2cast.cli import collect_targets
        from mkv2cast.config import Config

        cfg = Config()
        test_file = tmp_path / "video.mkv"
        test_file.touch()

        monkeypatch.chdir(tmp_path)
        targets, ignored = collect_targets(tmp_path, test_file, cfg)

        assert len(targets) == 1
        assert targets[0] == test_file

    def test_collect_targets_directory(self, tmp_path, monkeypatch):
        """Test collect_targets scanning directory."""
        from mkv2cast.cli import collect_targets
        from mkv2cast.config import Config

        cfg = Config()
        cfg.recursive = False

        # Create test files
        (tmp_path / "video1.mkv").touch()
        (tmp_path / "video2.mkv").touch()
        (tmp_path / "other.txt").touch()

        monkeypatch.chdir(tmp_path)
        targets, ignored = collect_targets(tmp_path, None, cfg)

        assert len(targets) == 2
        assert all(t.suffix == ".mkv" for t in targets)

    def test_collect_targets_ignores_output(self, tmp_path, monkeypatch):
        """Test collect_targets ignores output files."""
        from mkv2cast.cli import collect_targets
        from mkv2cast.config import Config

        cfg = Config()
        cfg.recursive = False

        # Create test files
        (tmp_path / "video.mkv").touch()
        (tmp_path / "video.cast.mkv").touch()  # Output file

        monkeypatch.chdir(tmp_path)
        targets, ignored = collect_targets(tmp_path, None, cfg)

        assert len(targets) == 1
        assert targets[0].name == "video.mkv"


class TestPathFunctions:
    """Tests for path utility functions."""

    def test_get_log_path(self, monkeypatch, tmp_path):
        """Test get_log_path generates correct path."""
        # Mock APP_DIRS
        import mkv2cast.cli
        from mkv2cast.cli import get_log_path

        mkv2cast.cli.APP_DIRS = {"logs": tmp_path / "logs"}

        input_file = Path("/videos/movie.mkv")
        log_path = get_log_path(input_file)

        assert log_path.suffix == ".log"
        assert "movie" in log_path.name

    def test_get_tmp_path(self, monkeypatch, tmp_path):
        """Test get_tmp_path generates correct path."""
        # Mock APP_DIRS
        import mkv2cast.cli
        from mkv2cast.cli import get_tmp_path
        from mkv2cast.config import Config

        mkv2cast.cli.APP_DIRS = {"tmp": tmp_path / "tmp"}

        cfg = Config()
        input_file = Path("/videos/movie.mkv")
        tmp_out = get_tmp_path(input_file, worker_id=0, tag=".h264", cfg=cfg)

        assert ".tmp." in tmp_out.name
        assert tmp_out.suffix == ".mkv"


class TestCheckRequirements:
    """Tests for check_requirements function."""

    def test_check_requirements_runs(self):
        """Test check_requirements executes without error."""
        from mkv2cast.cli import check_requirements

        # Should return 0 (success) or continue without crash
        result = check_requirements()
        assert result == 0


class TestParseArgs:
    """Tests for argument parsing."""

    def test_parse_args_no_args(self, monkeypatch):
        """Test parse_args with no arguments."""
        from mkv2cast.cli import parse_args

        monkeypatch.setattr(sys, "argv", ["mkv2cast"])
        cfg, single = parse_args()

        assert single is None
        assert cfg.recursive is True
        assert cfg.suffix == ".cast"

    def test_parse_args_single_file(self, monkeypatch, tmp_path):
        """Test parse_args with single file."""
        from mkv2cast.cli import parse_args

        test_file = tmp_path / "video.mkv"
        test_file.touch()

        monkeypatch.setattr(sys, "argv", ["mkv2cast", str(test_file)])
        cfg, single = parse_args()

        assert single == test_file

    def test_parse_args_options(self, monkeypatch):
        """Test parse_args with various options."""
        from mkv2cast.cli import parse_args

        monkeypatch.setattr(
            sys, "argv", ["mkv2cast", "--no-recursive", "--hw", "cpu", "--crf", "25", "--suffix", ".converted"]
        )
        cfg, single = parse_args()

        assert cfg.recursive is False
        assert cfg.hw == "cpu"
        assert cfg.crf == 25
        assert cfg.suffix == ".converted"

    def test_parse_args_language(self, monkeypatch):
        """Test parse_args with language option."""
        from mkv2cast.cli import parse_args

        monkeypatch.setattr(sys, "argv", ["mkv2cast", "--lang", "fr"])
        cfg, single = parse_args()

        assert cfg.lang == "fr"


class TestUtilityCommands:
    """Tests for utility commands."""

    def test_show_dirs(self, monkeypatch, capsys):
        """Test --show-dirs command."""
        from mkv2cast.cli import handle_utility_commands
        from mkv2cast.config import Config

        cfg = Config()
        args = MagicMock()
        args.check_requirements = False
        args.show_dirs = True
        args.clean_tmp = False
        args.clean_logs = None
        args.clean_history = None
        args.history = None
        args.history_stats = False

        result = handle_utility_commands(cfg, args)

        assert result == 0
        captured = capsys.readouterr()
        assert "Config:" in captured.out


class TestMultiUserCleanup:
    """Tests for multi-user cleanup functions."""

    def test_get_all_users_mkv2cast_dirs_no_home(self, monkeypatch):
        """Test get_all_users_mkv2cast_dirs when /home doesn't exist."""
        from mkv2cast.cli import get_all_users_mkv2cast_dirs

        monkeypatch.setattr(Path, "exists", lambda self: False)
        users = get_all_users_mkv2cast_dirs()
        assert users == []

    def test_cleanup_all_users_logs_no_users(self, monkeypatch):
        """Test cleanup_all_users_logs with no users."""
        from mkv2cast.cli import cleanup_all_users_logs

        monkeypatch.setattr("mkv2cast.cli.get_all_users_mkv2cast_dirs", lambda: [])
        results = cleanup_all_users_logs(7, verbose=False)
        assert results == {}

    def test_cleanup_all_users_tmp_no_users(self, monkeypatch):
        """Test cleanup_all_users_tmp with no users."""
        from mkv2cast.cli import cleanup_all_users_tmp

        monkeypatch.setattr("mkv2cast.cli.get_all_users_mkv2cast_dirs", lambda: [])
        results = cleanup_all_users_tmp(0, verbose=False)
        assert results == {}
