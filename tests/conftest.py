"""
Pytest configuration and shared fixtures for mkv2cast tests.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Generator

import pytest

# Add src to path for testing
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture(scope="session")
def test_data_dir() -> Path:
    """Return the test data directory path."""
    return Path(__file__).parent / "data"


@pytest.fixture(scope="session")
def test_sample_mkv(test_data_dir: Path) -> Path:
    """
    Create a small test MKV file using ffmpeg.

    This creates a ~2MB test file with:
    - H.265 video (to trigger transcoding)
    - AAC audio
    - 5 seconds duration
    """
    test_data_dir.mkdir(parents=True, exist_ok=True)
    mkv_path = test_data_dir / "test_sample.mkv"

    # Skip if file already exists and is valid
    if mkv_path.exists() and mkv_path.stat().st_size > 100000:
        return mkv_path

    # Check if ffmpeg is available
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not available for creating test files")

    # Create test file with H.265 video and AAC audio
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=duration=5:size=320x240:rate=24",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=5",
        "-c:v",
        "libx265",
        "-preset",
        "ultrafast",
        "-crf",
        "35",
        "-c:a",
        "aac",
        "-b:a",
        "64k",
        str(mkv_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=120)
        if result.returncode != 0:
            pytest.skip(f"Failed to create test file: {result.stderr.decode()[:200]}")
    except subprocess.TimeoutExpired:
        pytest.skip("Timeout creating test file")
    except Exception as e:
        pytest.skip(f"Error creating test file: {e}")

    return mkv_path


@pytest.fixture(scope="session")
def test_h264_mkv(test_data_dir: Path) -> Path:
    """
    Create a test MKV file with H.264 video (should not need transcoding).
    """
    test_data_dir.mkdir(parents=True, exist_ok=True)
    mkv_path = test_data_dir / "test_h264.mkv"

    if mkv_path.exists() and mkv_path.stat().st_size > 100000:
        return mkv_path

    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not available")

    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=duration=3:size=320x240:rate=24",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=3",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "35",
        "-pix_fmt",
        "yuv420p",
        "-profile:v",
        "high",
        "-level",
        "4.1",
        "-c:a",
        "aac",
        "-b:a",
        "64k",
        str(mkv_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        if result.returncode != 0:
            pytest.skip("Failed to create test file")
    except Exception as e:
        pytest.skip(f"Error: {e}")

    return mkv_path


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test outputs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_config_dir(temp_dir: Path) -> Path:
    """Create a temporary config directory."""
    config_dir = temp_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


@pytest.fixture
def temp_state_dir(temp_dir: Path) -> Path:
    """Create a temporary state directory."""
    state_dir = temp_dir / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


@pytest.fixture
def mock_xdg_dirs(temp_dir: Path, monkeypatch):
    """Mock XDG directories to use temporary paths."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(temp_dir / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(temp_dir / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(temp_dir / "cache"))


@pytest.fixture
def default_config():
    """Return a default Config instance for testing."""
    from mkv2cast.config import Config

    return Config()
