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

Language
--------

**Force specific language:**

.. code-block:: bash

   mkv2cast --lang fr
   mkv2cast --lang de
   mkv2cast --lang es
