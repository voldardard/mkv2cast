"""
User interface components for mkv2cast.

Provides both Rich-based and legacy text-based progress displays.
"""

import importlib.util

from mkv2cast.ui.legacy_ui import LegacyProgressUI, UIState

# Check if Rich is available using importlib
RICH_AVAILABLE = importlib.util.find_spec("rich") is not None

__all__ = [
    "RICH_AVAILABLE",
    "LegacyProgressUI",
    "UIState",
]

# Conditionally export Rich UI classes
if RICH_AVAILABLE:
    from mkv2cast.ui.rich_ui import RichProgressUI  # noqa: F401
    from mkv2cast.ui.simple_rich import SimpleRichUI  # noqa: F401

    __all__.append("RichProgressUI")
    __all__.append("SimpleRichUI")
