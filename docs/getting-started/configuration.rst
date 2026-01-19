Configuration
=============

mkv2cast can be configured through configuration files, environment variables, or command-line arguments.

Configuration Priority
----------------------

Settings are applied in this order (later overrides earlier):

1. Built-in defaults
2. System config (``/etc/mkv2cast/config.toml``)
3. User config (``~/.config/mkv2cast/config.toml``)
4. Environment variables
5. Command-line arguments

Configuration File
------------------

mkv2cast uses TOML format for configuration (with INI fallback).

Default location: ``~/.config/mkv2cast/config.toml``

Example configuration:

.. code-block:: toml

   # Output settings
   [output]
   suffix = ".cast"
   container = "mkv"

   # Scan settings
   [scan]
   recursive = true
   ignore_patterns = ["*sample*", "*.eng.*"]
   ignore_paths = ["Downloads/temp"]

   # Encoding settings
   [encoding]
   backend = "auto"  # auto, vaapi, qsv, cpu
   crf = 20
   preset = "slow"
   abr = "192k"

   # Worker settings
   [workers]
   encode = 0     # 0 = auto-detect
   integrity = 0  # 0 = auto-detect

   # Integrity checking
   [integrity]
   enabled = true
   stable_wait = 3
   deep_check = false

   # Notifications
   [notifications]
   enabled = true
   on_success = true
   on_failure = true

   # Internationalization
   [i18n]
   # lang = "fr"  # Override system language

Environment Variables
---------------------

Some settings can be controlled via environment:

- ``MKV2CAST_LANG`` - Override language (e.g., ``fr``, ``en``, ``de``)
- ``XDG_CONFIG_HOME`` - Config directory base (default: ``~/.config``)
- ``XDG_STATE_HOME`` - State directory base (default: ``~/.local/state``)
- ``XDG_CACHE_HOME`` - Cache directory base (default: ``~/.cache``)

XDG Directories
---------------

mkv2cast follows the XDG Base Directory specification:

.. code-block:: text

   ~/.config/mkv2cast/
   ├── config.toml      # User configuration

   ~/.local/state/mkv2cast/
   ├── history.db       # Conversion history (SQLite)
   └── logs/            # Conversion logs
       └── YYYY-MM-DD_filename.log

   ~/.cache/mkv2cast/
   └── tmp/             # Temporary files during encoding

View these directories:

.. code-block:: bash

   mkv2cast --show-dirs

Creating Default Config
-----------------------

A default config file is created automatically on first run.
You can also manually create one:

.. code-block:: bash

   mkdir -p ~/.config/mkv2cast
   mkv2cast --show-dirs  # This creates default config

Common Configuration Examples
-----------------------------

**Fast encoding for weak hardware:**

.. code-block:: toml

   [encoding]
   backend = "cpu"
   preset = "faster"
   crf = 23

**High quality with hardware acceleration:**

.. code-block:: toml

   [encoding]
   backend = "vaapi"

   [workers]
   encode = 2
   integrity = 3

**Ignore sample and trailer files:**

.. code-block:: toml

   [scan]
   ignore_patterns = ["*sample*", "*trailer*", "*featurette*"]

**French language and notifications:**

.. code-block:: toml

   [i18n]
   lang = "fr"

   [notifications]
   enabled = true
   on_success = true
   on_failure = true
