#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mkv2cast - Smart MKV to Chromecast-compatible converter with hardware acceleration.

This is a compatibility wrapper for the mkv2cast package.
For new installations, install via pip: pip install mkv2cast

Copyright (C) 2024-2026 voldardard
License: GPL-3.0 (https://www.gnu.org/licenses/gpl-3.0.html)
"""

import sys
from pathlib import Path

# Allow running directly from source checkout (before pip install)
_src_path = Path(__file__).parent / "src"
if _src_path.exists() and str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

try:
    from mkv2cast.cli import main
except ImportError as e:
    print(f"Error: Could not import mkv2cast package: {e}", file=sys.stderr)
    print("Please install the package: pip install -e .", file=sys.stderr)
    sys.exit(1)

if __name__ == "__main__":
    sys.exit(main())
