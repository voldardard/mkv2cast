Installation
============

mkv2cast can be installed through several methods depending on your needs.

Prerequisites
-------------

mkv2cast requires:

- **Python 3.8+** - The interpreter
- **ffmpeg** - For video processing and encoding
- **ffprobe** - For media analysis (usually included with ffmpeg)

Optional dependencies:

- **rich** - For beautiful progress UI (``pip install rich``)
- **tomli** - For TOML config support on Python < 3.11
- **plyer** - For desktop notifications fallback
- **libnotify** - For notify-send desktop notifications

PyPI (Recommended)
------------------

The simplest way to install mkv2cast:

.. code-block:: bash

   # Basic installation
   pip install mkv2cast

   # With all optional features
   pip install "mkv2cast[full]"

   # With just the rich UI
   pip install "mkv2cast[rich]"

Arch Linux (AUR)
----------------

For Arch Linux users:

.. code-block:: bash

   # Using yay
   yay -S mkv2cast

   # Using paru
   paru -S mkv2cast

   # Manual PKGBUILD
   git clone https://aur.archlinux.org/mkv2cast.git
   cd mkv2cast
   makepkg -si

Debian/Ubuntu
-------------

Download the .deb package from the releases page:

.. code-block:: bash

   sudo dpkg -i mkv2cast_1.1.0_all.deb
   sudo apt-get install -f  # Install dependencies

Script Installation
-------------------

For a quick install without package managers:

.. code-block:: bash

   # Install to ~/.local
   curl -fsSL https://raw.githubusercontent.com/voldardard/mkv2cast/main/install.sh | bash

   # System-wide installation (requires sudo)
   curl -fsSL https://raw.githubusercontent.com/voldardard/mkv2cast/main/install.sh | sudo bash -s -- --system

Development Installation
------------------------

For development or contributing:

.. code-block:: bash

   # Clone the repository
   git clone https://github.com/voldardard/mkv2cast.git
   cd mkv2cast

   # Install in editable mode with dev dependencies
   pip install -e ".[dev,full]"

   # Run tests
   pytest

Verifying Installation
----------------------

After installation, verify everything works:

.. code-block:: bash

   # Check version
   mkv2cast --version

   # Check requirements
   mkv2cast --check-requirements

   # Show configuration directories
   mkv2cast --show-dirs
