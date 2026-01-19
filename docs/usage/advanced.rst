Advanced Usage
==============

This page covers advanced features and usage patterns.

Utility Commands
----------------

**Show configuration directories:**

.. code-block:: bash

   mkv2cast --show-dirs

**Check system requirements:**

.. code-block:: bash

   mkv2cast --check-requirements

**View conversion history:**

.. code-block:: bash

   # Last 20 conversions
   mkv2cast --history

   # Last 100 conversions
   mkv2cast --history 100

**View statistics:**

.. code-block:: bash

   mkv2cast --history-stats

Cleanup Commands
----------------

**Clean temporary files:**

.. code-block:: bash

   mkv2cast --clean-tmp

**Clean old logs:**

.. code-block:: bash

   # Remove logs older than 30 days
   mkv2cast --clean-logs 30

**Clean old history:**

.. code-block:: bash

   # Remove history older than 90 days
   mkv2cast --clean-history 90

Automated Cleanup with Systemd
------------------------------

mkv2cast includes systemd timers for automated cleanup:

.. code-block:: bash

   # Enable user timer
   systemctl --user enable mkv2cast-cleanup.timer
   systemctl --user start mkv2cast-cleanup.timer

   # Check status
   systemctl --user status mkv2cast-cleanup.timer

Using as a Python Library
-------------------------

mkv2cast can be used programmatically:

.. code-block:: python

   from mkv2cast import convert_file, Config, decide_for, pick_backend
   from pathlib import Path

   # Create custom configuration
   config = Config(
       hw="vaapi",
       crf=20,
       notify=False
   )

   # Analyze a file
   decision = decide_for(Path("movie.mkv"), config)
   print(f"Needs video transcode: {decision.need_v}")
   print(f"Needs audio transcode: {decision.need_a}")

   # Convert a file
   success, output_path, message = convert_file(
       Path("movie.mkv"),
       cfg=config,
       backend="vaapi"
   )

   if success:
       print(f"Converted to: {output_path}")
   else:
       print(f"Failed: {message}")

Batch Processing Script
-----------------------

Example script for batch processing with custom logic:

.. code-block:: python

   #!/usr/bin/env python3
   from pathlib import Path
   from mkv2cast import convert_file, Config

   config = Config(
       hw="auto",
       container="mp4",
       notify=False
   )

   input_dir = Path("/media/videos")
   output_dir = Path("/media/converted")

   for mkv_file in input_dir.glob("**/*.mkv"):
       success, output, msg = convert_file(
           mkv_file,
           cfg=config,
           output_dir=output_dir
       )
       
       if success and output:
           print(f"✓ {mkv_file.name} -> {output.name}")
       elif not success:
           print(f"✗ {mkv_file.name}: {msg}")
       else:
           print(f"⊘ {mkv_file.name}: {msg}")

Integration with Other Tools
----------------------------

**With find command:**

.. code-block:: bash

   # Process files modified in last 7 days
   find /media -name "*.mkv" -mtime -7 -exec mkv2cast {} \;

**With xargs for parallel processing:**

.. code-block:: bash

   find /media -name "*.mkv" -print0 | xargs -0 -P 2 -I {} mkv2cast {}

**With inotifywait for watch mode:**

.. code-block:: bash

   inotifywait -m -e close_write --format '%w%f' /media/incoming |
   while read file; do
       [[ "$file" == *.mkv ]] && mkv2cast "$file"
   done

Logging
-------

Conversion logs are stored in:

.. code-block:: text

   ~/.local/state/mkv2cast/logs/YYYY-MM-DD_filename.log

View logs:

.. code-block:: bash

   # List recent logs
   ls -la ~/.local/state/mkv2cast/logs/

   # View specific log
   cat ~/.local/state/mkv2cast/logs/2026-01-18_movie.log
