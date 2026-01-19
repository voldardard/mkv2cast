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

The AUR package ships the man page, bash/zsh completions, and both user + system cleanup timers automatically.

Debian/Ubuntu
-------------

**APT Repository (Recommended)**

Add the official APT repository for automatic updates:

.. code-block:: bash

   # Add the repository
   echo "deb [trusted=yes] https://voldardard.github.io/mkv2cast/apt stable main" | sudo tee /etc/apt/sources.list.d/mkv2cast.list

   # Update and install
   sudo apt update
   sudo apt install mkv2cast

**Manual Installation**

Download the ``.deb`` package from `GitHub Releases <https://github.com/voldardard/mkv2cast/releases>`_:

.. code-block:: bash

   wget https://github.com/voldardard/mkv2cast/releases/download/v1.2.5/mkv2cast_1.2.5-1_all.deb
   sudo dpkg -i mkv2cast_1.2.5-1_all.deb
   sudo apt-get install -f  # Install dependencies

Debian packages install the man page, bash/zsh completions, the user cleanup timer, and the optional system-wide cleanup timer. The watch mode service and timer are also available as user units.

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
