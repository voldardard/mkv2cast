"""
Sphinx configuration file for mkv2cast documentation.
"""

import os
import sys

# Add source directory to path for autodoc
sys.path.insert(0, os.path.abspath("../src"))

# Import version from package
from mkv2cast import __version__

# Project information
project = "mkv2cast"
copyright = "2024-2026, voldardard"
author = "voldardard"
release = __version__
version = ".".join(__version__.split(".")[:2])  # e.g. "1.1" from "1.1.0"

# General configuration
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.viewcode",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "myst_parser",
]

# Add support for markdown files
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# HTML output options
html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
html_title = f"{project} {release}"
html_logo = "_static/mkv2cast-logo.svg"
html_favicon = "_static/favicon-32x32.png"

# Theme options
html_theme_options = {
    "logo_only": False,
    "display_version": True,
    "prev_next_buttons_location": "bottom",
    "style_external_links": False,
    "collapse_navigation": True,
    "sticky_navigation": True,
    "navigation_depth": 4,
    "includehidden": True,
    "titles_only": False,
}

# Autodoc configuration
autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
}

autodoc_member_order = "bysource"

# Napoleon configuration (for Google-style docstrings)
napoleon_google_docstring = True
napoleon_numpy_docstring = True

# Intersphinx configuration
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

# MyST configuration (for Markdown)
myst_enable_extensions = [
    "colon_fence",
    "deflist",
]
