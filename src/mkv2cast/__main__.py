"""
Entry point for running mkv2cast as a module: python -m mkv2cast

This allows the package to be executed directly:
    python -m mkv2cast movie.mkv
    python -m mkv2cast --help
"""

import sys

from mkv2cast.cli import main

if __name__ == "__main__":
    sys.exit(main())
