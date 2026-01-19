"""
mkv2cast - Smart MKV to Chromecast-compatible converter with hardware acceleration.

This tool converts MKV video files to formats compatible with Chromecast devices
and smart TVs, using VAAPI, QSV, or CPU encoding with intelligent codec detection.

Copyright (C) 2024-2026 voldardard
License: GPL-3.0 (https://www.gnu.org/licenses/gpl-3.0.html)

Example usage:
    # As a command-line tool
    $ mkv2cast movie.mkv
    $ mkv2cast --hw vaapi --vaapi-qp 20

    # As a Python module
    from mkv2cast import convert_file, Config

    config = Config(hw="vaapi", crf=20)
    result = convert_file("movie.mkv", config)
"""

__version__ = "1.2.0"
__author__ = "voldardard"
__license__ = "GPL-3.0"
__copyright__ = "Copyright (C) 2024-2026 voldardard"
__url__ = "https://github.com/voldardard/mkv2cast"
__description__ = "Smart MKV to Chromecast-compatible converter with hardware acceleration"

# Public API exports
from mkv2cast.config import Config, get_app_dirs, load_config_file
from mkv2cast.converter import (
    Decision,
    build_transcode_cmd,
    convert_file,
    decide_for,
    pick_backend,
)
from mkv2cast.history import HistoryDB
from mkv2cast.i18n import _, setup_i18n
from mkv2cast.integrity import integrity_check
from mkv2cast.json_progress import JSONProgressOutput, parse_ffmpeg_progress_for_json
from mkv2cast.notifications import send_notification

__all__ = [
    # Version info
    "__version__",
    "__author__",
    "__license__",
    "__url__",
    # Config
    "Config",
    "get_app_dirs",
    "load_config_file",
    # Converter
    "Decision",
    "decide_for",
    "pick_backend",
    "build_transcode_cmd",
    "convert_file",
    # History
    "HistoryDB",
    # Integrity
    "integrity_check",
    # i18n
    "_",
    "setup_i18n",
    # Notifications
    "send_notification",
    # JSON progress
    "JSONProgressOutput",
    "parse_ffmpeg_progress_for_json",
]
