Basic Usage
===========

This page covers common usage patterns for mkv2cast.

Processing Files
----------------

**All files in current directory:**

.. code-block:: bash

   mkv2cast

**Single file:**

.. code-block:: bash

   mkv2cast movie.mkv

**Non-recursive (current directory only):**

.. code-block:: bash

   mkv2cast --no-recursive

Output Options
--------------

**Change output suffix:**

.. code-block:: bash

   mkv2cast --suffix ".converted"
   # Output: movie.h264.converted.mkv

**Change container format:**

.. code-block:: bash

   mkv2cast --container mp4
   # Output: movie.h264.cast.mp4

Codec Control
-------------

**Force H.264 transcoding:**

.. code-block:: bash

   # Even if input is already H.264
   mkv2cast --force-h264

**Allow HEVC passthrough:**

.. code-block:: bash

   # For TVs that support HEVC
   mkv2cast --allow-hevc

**Force AAC audio:**

.. code-block:: bash

   mkv2cast --force-aac

**Keep surround sound:**

.. code-block:: bash

   # Don't downmix to stereo
   mkv2cast --keep-surround

Quality Settings
----------------

**Encoding quality (CPU mode):**

.. code-block:: bash

   # CRF value (lower = better quality, larger file)
   mkv2cast --hw cpu --crf 18

   # Preset (slower = better quality)
   mkv2cast --hw cpu --preset slower

**Audio bitrate:**

.. code-block:: bash

   mkv2cast --abr 256k

Parallel Processing
-------------------

**Enable pipeline mode (default):**

.. code-block:: bash

   mkv2cast --pipeline

**Sequential mode:**

.. code-block:: bash

   mkv2cast --no-pipeline

**Custom worker counts:**

.. code-block:: bash

   mkv2cast --encode-workers 2 --integrity-workers 3

Integrity Checking
------------------

**Disable integrity check:**

.. code-block:: bash

   mkv2cast --no-integrity-check

**Custom stability wait:**

.. code-block:: bash

   mkv2cast --stable-wait 5

**Enable deep decode check:**

.. code-block:: bash

   # Slower but catches more issues
   mkv2cast --deep-check

UI Options
----------

**Disable progress bar:**

.. code-block:: bash

   mkv2cast --no-progress

**Debug output:**

.. code-block:: bash

   mkv2cast --debug

Notifications
-------------

**Enable notifications (default):**

.. code-block:: bash

   mkv2cast --notify

**Disable notifications:**

.. code-block:: bash

   mkv2cast --no-notify

Audio Track Selection
---------------------

**By language priority:**

.. code-block:: bash

   # Prefer French, then English
   mkv2cast --audio-lang fre,fra,fr,eng

   # Japanese with English fallback
   mkv2cast --audio-lang jpn,ja,eng

**By track index:**

.. code-block:: bash

   # Use second audio track (0-indexed)
   mkv2cast --audio-track 1

Subtitle Selection
------------------

**By language:**

.. code-block:: bash

   # Include English subtitles
   mkv2cast --subtitle-lang eng

   # French or English subtitles
   mkv2cast --subtitle-lang fre,fra,eng

**By track index:**

.. code-block:: bash

   mkv2cast --subtitle-track 0

**Forced subtitles:**

.. code-block:: bash

   # Prefer forced subtitles in audio language (default)
   mkv2cast --prefer-forced-subs

   # Don't prefer forced subtitles
   mkv2cast --no-forced-subs

**Disable subtitles:**

.. code-block:: bash

   mkv2cast --no-subtitles

Watch Mode
----------

Monitor a directory for new MKV files and convert automatically.

**Watch current directory:**

.. code-block:: bash

   mkv2cast --watch

**Watch specific directory:**

.. code-block:: bash

   mkv2cast --watch /path/to/folder

**Custom polling interval:**

.. code-block:: bash

   mkv2cast --watch --watch-interval 10

Watch mode uses ``watchdog`` library if available for efficient file system monitoring.
Install with: ``pip install mkv2cast[watch]``

**Systemd service:**

You can run watch mode as a systemd service for automatic startup:

.. code-block:: bash

   # Copy service file to user systemd directory
   cp systemd/mkv2cast-watch.service ~/.config/systemd/user/
   
   # Edit the service to set your watch directory
   # Edit Environment="MKV2CAST_WATCH_DIR=..." in the service file
   
   # Enable and start the service
   systemctl --user enable mkv2cast-watch.service
   systemctl --user start mkv2cast-watch.service
   
   # Check status
   systemctl --user status mkv2cast-watch.service
   
   # View logs
   journalctl --user -u mkv2cast-watch -f

Language
--------

**Force UI language:**

.. code-block:: bash

   mkv2cast --lang fr
   mkv2cast --lang de
   mkv2cast --lang es
