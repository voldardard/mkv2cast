"""
Tests for configuration loading and management.
"""

from pathlib import Path


class TestConfig:
    """Tests for Config dataclass."""

    def test_config_defaults(self):
        """Test default config values."""
        from mkv2cast.config import Config
        cfg = Config()

        assert cfg.suffix == ".cast"
        assert cfg.container == "mkv"
        assert cfg.recursive is True
        assert cfg.ignore_patterns == []
        assert cfg.ignore_paths == []
        assert cfg.include_patterns == []
        assert cfg.include_paths == []
        assert cfg.debug is False
        assert cfg.dryrun is False
        assert cfg.skip_when_ok is True
        assert cfg.hw == "auto"
        assert cfg.notify is True

    def test_config_custom_values(self):
        """Test config with custom values."""
        from mkv2cast.config import Config
        cfg = Config(
            suffix=".converted",
            container="mp4",
            recursive=False,
            debug=True,
            crf=23,
            preset="fast"
        )

        assert cfg.suffix == ".converted"
        assert cfg.container == "mp4"
        assert cfg.recursive is False
        assert cfg.debug is True
        assert cfg.crf == 23
        assert cfg.preset == "fast"


class TestXDGDirectories:
    """Tests for XDG directory functions."""

    def test_get_xdg_config_home_default(self, monkeypatch):
        """Test default config home."""
        from mkv2cast.config import get_xdg_config_home

        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        config_home = get_xdg_config_home()
        assert config_home == Path.home() / ".config"

    def test_get_xdg_config_home_custom(self, monkeypatch, temp_dir):
        """Test custom config home."""
        from mkv2cast.config import get_xdg_config_home

        monkeypatch.setenv("XDG_CONFIG_HOME", str(temp_dir))
        config_home = get_xdg_config_home()
        assert config_home == temp_dir

    def test_get_xdg_state_home_default(self, monkeypatch):
        """Test default state home."""
        from mkv2cast.config import get_xdg_state_home

        monkeypatch.delenv("XDG_STATE_HOME", raising=False)
        state_home = get_xdg_state_home()
        assert state_home == Path.home() / ".local" / "state"

    def test_get_xdg_cache_home_default(self, monkeypatch):
        """Test default cache home."""
        from mkv2cast.config import get_xdg_cache_home

        monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
        cache_home = get_xdg_cache_home()
        assert cache_home == Path.home() / ".cache"

    def test_get_app_dirs(self, mock_xdg_dirs, temp_dir):
        """Test app directories creation."""
        from mkv2cast.config import get_app_dirs

        dirs = get_app_dirs()

        assert "config" in dirs
        assert "state" in dirs
        assert "logs" in dirs
        assert "cache" in dirs
        assert "tmp" in dirs

        # Check directories are created
        assert dirs["config"].exists()
        assert dirs["state"].exists()
        assert dirs["logs"].exists()
        assert dirs["cache"].exists()
        assert dirs["tmp"].exists()


class TestConfigFileLoading:
    """Tests for configuration file loading."""

    def test_load_config_file_empty(self, temp_config_dir):
        """Test loading from empty directory."""
        from mkv2cast.config import load_config_file

        config = load_config_file(temp_config_dir)
        assert config == {}

    def test_load_config_file_ini(self, temp_config_dir):
        """Test loading INI config."""
        from mkv2cast.config import load_config_file

        ini_content = """
[output]
suffix = .custom
container = mp4

[encoding]
crf = 25
preset = fast

[scan]
recursive = false
"""
        ini_path = temp_config_dir / "config.ini"
        ini_path.write_text(ini_content)

        config = load_config_file(temp_config_dir)

        assert config.get("output", {}).get("suffix") == ".custom"
        assert config.get("output", {}).get("container") == "mp4"
        assert config.get("encoding", {}).get("crf") == 25
        assert config.get("encoding", {}).get("preset") == "fast"
        assert config.get("scan", {}).get("recursive") is False

    def test_apply_config_to_args(self, temp_config_dir):
        """Test applying file config to Config instance."""
        from mkv2cast.config import Config, apply_config_to_args

        file_config = {
            "output": {
                "suffix": ".custom",
                "container": "mp4"
            },
            "encoding": {
                "crf": 23,
                "preset": "medium"
            },
            "notifications": {
                "enabled": False
            }
        }

        cfg = Config()
        apply_config_to_args(file_config, cfg)

        assert cfg.suffix == ".custom"
        assert cfg.container == "mp4"
        assert cfg.crf == 23
        assert cfg.preset == "medium"
        assert cfg.notify is False

    def test_save_default_config(self, temp_config_dir):
        """Test saving default config file."""
        from mkv2cast.config import TOML_AVAILABLE, save_default_config

        path = save_default_config(temp_config_dir)

        assert path.exists()
        content = path.read_text()
        assert "suffix" in content
        assert "container" in content

        if TOML_AVAILABLE:
            assert path.suffix == ".toml"
        else:
            assert path.suffix == ".ini"


class TestParseIniValue:
    """Tests for INI value parsing."""

    def test_parse_bool_true(self):
        """Test parsing boolean true values."""
        from mkv2cast.config import _parse_ini_value

        assert _parse_ini_value("true") is True
        assert _parse_ini_value("yes") is True
        assert _parse_ini_value("on") is True
        assert _parse_ini_value("True") is True
        assert _parse_ini_value("YES") is True

    def test_parse_bool_false(self):
        """Test parsing boolean false values."""
        from mkv2cast.config import _parse_ini_value

        assert _parse_ini_value("false") is False
        assert _parse_ini_value("no") is False
        assert _parse_ini_value("off") is False
        assert _parse_ini_value("False") is False
        assert _parse_ini_value("NO") is False

    def test_parse_int(self):
        """Test parsing integer values."""
        from mkv2cast.config import _parse_ini_value

        assert _parse_ini_value("42") == 42
        assert _parse_ini_value("0") == 0
        assert _parse_ini_value("-5") == -5

    def test_parse_float(self):
        """Test parsing float values."""
        from mkv2cast.config import _parse_ini_value

        assert _parse_ini_value("3.14") == 3.14
        assert _parse_ini_value("0.5") == 0.5

    def test_parse_list(self):
        """Test parsing comma-separated list."""
        from mkv2cast.config import _parse_ini_value

        result = _parse_ini_value("a, b, c")
        assert result == ["a", "b", "c"]

        result = _parse_ini_value("one,two")
        assert result == ["one", "two"]

    def test_parse_string(self):
        """Test parsing regular string."""
        from mkv2cast.config import _parse_ini_value

        assert _parse_ini_value("hello") == "hello"
        assert _parse_ini_value(".cast") == ".cast"
