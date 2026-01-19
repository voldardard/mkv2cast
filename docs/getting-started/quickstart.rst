Quick Start
===========

This guide will get you started with mkv2cast in just a few minutes.

Basic Usage
-----------

The simplest way to use mkv2cast is to run it in a directory containing MKV files:

.. code-block:: bash

   # Navigate to your videos folder
   cd ~/Videos

   # Process all MKV files
   mkv2cast

mkv2cast will:

1. Scan for all ``.mkv`` files recursively
2. Analyze each file's codecs
3. Skip files already compatible with Chromecast
4. Transcode incompatible files to H.264/AAC

Single File Conversion
----------------------

To convert a specific file:

.. code-block:: bash

   mkv2cast movie.mkv

The output will be named ``movie.h264.cast.mkv`` (or similar based on what was transcoded).

Understanding Output Names
--------------------------

mkv2cast names output files based on what was converted:

- ``.h264.cast.mkv`` - Video was transcoded to H.264
- ``.aac.cast.mkv`` - Audio was transcoded to AAC
- ``.h264.aac.cast.mkv`` - Both video and audio were transcoded
- ``.remux.cast.mkv`` - File was just remuxed (container change only)

Dry Run Mode
------------

To see what mkv2cast would do without actually processing:

.. code-block:: bash

   mkv2cast --dryrun

Debug Mode
----------

For detailed information about decisions:

.. code-block:: bash

   mkv2cast --debug

Hardware Acceleration
---------------------

mkv2cast automatically detects available hardware:

.. code-block:: bash

   # Auto-detect (default)
   mkv2cast --hw auto

   # Force VAAPI (AMD/Intel)
   mkv2cast --hw vaapi

   # Force Intel Quick Sync
   mkv2cast --hw qsv

   # Force CPU (most compatible)
   mkv2cast --hw cpu

Checking Conversion History
---------------------------

View recent conversions:

.. code-block:: bash

   # Show last 20 conversions
   mkv2cast --history

   # Show last 100 conversions
   mkv2cast --history 100

   # Show statistics
   mkv2cast --history-stats

Next Steps
----------

- Read about :doc:`configuration` for customizing behavior
- Learn about :doc:`../usage/advanced` options
- Configure :doc:`../usage/hardware-acceleration`
