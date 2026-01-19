Using mkv2cast as a Python Package
===================================

mkv2cast can be imported and used as a Python library in your scripts, allowing you to programmatically convert video files with full control over the conversion process.

Installation
------------

First, ensure mkv2cast is installed:

.. code-block:: bash

   pip install mkv2cast

Basic Usage
-----------

The simplest way to use mkv2cast programmatically is with the ``convert_file`` function:

.. code-block:: python

   from mkv2cast import convert_file
   from pathlib import Path

   # Convert a single file
   success, output_path, message = convert_file(Path("movie.mkv"))

   if success:
       if output_path:
           print(f"Converted to: {output_path}")
       else:
           print(f"Skipped: {message}")
   else:
       print(f"Failed: {message}")

The ``convert_file`` function returns a tuple of:
- ``success`` (bool): Whether the operation succeeded
- ``output_path`` (Path | None): Path to output file if created, None if skipped
- ``message`` (str): Status message explaining the result

Configuration
-------------

Create a custom configuration to control encoding settings:

.. code-block:: python

   from mkv2cast import Config, convert_file
   from pathlib import Path

   # Create custom configuration
   config = Config(
       hw="vaapi",           # Use VAAPI hardware acceleration
       crf=20,               # Quality setting (lower = better quality)
       preset="slow",        # Encoding preset
       container="mp4",      # Output container format
       suffix=".cast",       # Output file suffix
       notify=False          # Disable notifications in scripts
   )

   # Convert with custom config
   success, output_path, message = convert_file(
       Path("movie.mkv"),
       cfg=config
   )

Available Configuration Options
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``Config`` class supports all command-line options:

.. code-block:: python

   config = Config(
       # Output settings
       suffix=".cast",
       container="mkv",  # or "mp4"
       
       # Hardware acceleration
       hw="auto",  # "auto", "nvenc", "qsv", "vaapi", "cpu"
       vaapi_device="/dev/dri/renderD128",
       vaapi_qp=23,
       qsv_quality=23,
       nvenc_cq=23,
       
       # Encoding quality
       crf=20,
       preset="slow",  # "ultrafast" to "veryslow"
       abr="192k",
       
       # Codec decisions
       skip_when_ok=True,
       force_h264=False,
       allow_hevc=False,
       force_aac=False,
       keep_surround=False,
       
       # Audio/Subtitle selection
       audio_lang="fre,fra,fr",  # Comma-separated language codes
       audio_track=None,  # Explicit track index (0-based)
       subtitle_lang="fre,eng",
       subtitle_track=None,
       prefer_forced_subs=True,
       no_subtitles=False,
       
       # Integrity checks
       integrity_check=True,
       stable_wait=3,
       deep_check=False,
       
       # Notifications
       notify=True,
       notify_on_success=True,
       notify_on_failure=True,
   )

Analyzing Files
---------------

Before converting, you can analyze a file to see what transcoding is needed:

.. code-block:: python

   from mkv2cast import decide_for, pick_backend
   from pathlib import Path

   # Analyze a file
   decision = decide_for(Path("movie.mkv"))

   print(f"Video codec: {decision.vcodec}")
   print(f"Audio codec: {decision.acodec}")
   print(f"Needs video transcode: {decision.need_v}")
   print(f"Needs audio transcode: {decision.need_a}")
   print(f"Reason: {decision.reason_v}")
   print(f"Video profile: {decision.vprof}")
   print(f"Video level: {decision.vlevel}")
   print(f"Is HDR: {decision.vhdr}")
   print(f"Audio language: {decision.alang}")
   print(f"Audio channels: {decision.ach}")

   # Check available backend
   backend = pick_backend()
   print(f"Best backend: {backend}")

The ``Decision`` object contains detailed information about the file:

- ``need_v``: Whether video transcoding is needed
- ``need_a``: Whether audio transcoding is needed
- ``vcodec``: Source video codec name
- ``acodec``: Source audio codec name
- ``aidx``: Selected audio track index
- ``sidx``: Selected subtitle track index
- ``reason_v``: Explanation of video decision
- And more...

Batch Processing
----------------

Process multiple files with custom logic:

.. code-block:: python

   from pathlib import Path
   from mkv2cast import convert_file, Config

   config = Config(
       hw="auto",
       container="mkv",
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

Advanced: Building Custom Commands
----------------------------------

For more control, you can build FFmpeg commands manually:

.. code-block:: python

   from mkv2cast import decide_for, pick_backend, build_transcode_cmd
   from pathlib import Path
   import subprocess

   input_file = Path("movie.mkv")
   output_file = Path("movie.h264.cast.mkv")
   config = Config()

   # Analyze file
   decision = decide_for(input_file, config)

   # Select backend
   backend = pick_backend(config)

   # Build command (log_path is optional)
   cmd, stage = build_transcode_cmd(
       input_file,
       decision,
       backend,
       output_file,
       log_path=None,  # Optional: Path to log file
       cfg=config
   )

   # Run manually
   result = subprocess.run(cmd)
   if result.returncode == 0:
       print(f"{stage} completed successfully")

Working with History
--------------------

Access conversion history programmatically:

.. code-block:: python

   from mkv2cast import HistoryDB, get_app_dirs

   # Get history database
   dirs = get_app_dirs()
   history = HistoryDB(dirs["state"])

   # Get recent conversions
   recent = history.get_recent(20)
   for entry in recent:
       status = entry.get("status", "unknown")
       input_path = entry.get("input_path", "unknown")
       started = entry.get("started_at", "unknown")
       print(f"[{started}] {status}: {input_path}")

   # Get statistics
   stats = history.get_stats()
   by_status = stats.get("by_status", {})
   total = sum(by_status.values())
   
   print(f"Total conversions: {total}")
   for status, count in by_status.items():
       print(f"  {status}: {count}")

   # Get average encode time
   avg_time = stats.get("avg_encode_time", 0)
   print(f"Average encode time: {avg_time:.1f}s")

Loading Configuration Files
---------------------------

Load settings from configuration files:

.. code-block:: python

   from mkv2cast import load_config_file, get_app_dirs, Config

   # Get config directory
   dirs = get_app_dirs()

   # Load config file (TOML or INI)
   file_config = load_config_file(dirs["config"])

   # Create base config
   config = Config()

   # Manually apply file config to Config instance
   if "encoding" in file_config:
       encoding = file_config["encoding"]
       if "backend" in encoding:
           config.hw = encoding["backend"]
       if "crf" in encoding:
           config.crf = encoding["crf"]
       if "preset" in encoding:
           config.preset = encoding["preset"]
       if "abr" in encoding:
           config.abr = encoding["abr"]
   
   if "output" in file_config:
       output = file_config["output"]
       if "suffix" in output:
           config.suffix = output["suffix"]
       if "container" in output:
           config.container = output["container"]

   # Now config contains values from file
   print(f"Hardware: {config.hw}")
   print(f"CRF: {config.crf}")

Getting Application Directories
-------------------------------

Get XDG-compliant directories used by mkv2cast:

.. code-block:: python

   from mkv2cast import get_app_dirs

   dirs = get_app_dirs()
   
   print(f"Config: {dirs['config']}")      # ~/.config/mkv2cast
   print(f"State: {dirs['state']}")        # ~/.local/state/mkv2cast
   print(f"Logs: {dirs['logs']}")          # ~/.local/state/mkv2cast/logs
   print(f"Cache: {dirs['cache']}")        # ~/.cache/mkv2cast
   print(f"Tmp: {dirs['tmp']}")            # ~/.cache/mkv2cast/tmp

Sending Notifications
---------------------

Send desktop notifications from your scripts:

.. code-block:: python

   from mkv2cast import send_notification

   # Send a notification
   send_notification(
       title="Conversion Complete",
       message="Successfully converted 5 files",
       urgency="normal"  # "low", "normal", "critical"
   )

Internationalization
--------------------

Setup language for messages:

.. code-block:: python

   from mkv2cast import setup_i18n, _

   # Setup French translations
   setup_i18n("fr")

   # Use translations
   print(_("Conversion complete"))  # "Conversion terminée"

Available languages: ``en``, ``fr``, ``es``, ``it``, ``de``.

Complete Example Script
------------------------

Here's a complete example that processes files with error handling and logging:

.. code-block:: python

   #!/usr/bin/env python3
   """Batch convert MKV files with custom configuration."""
   
   import sys
   from pathlib import Path
   from mkv2cast import convert_file, Config, get_app_dirs, HistoryDB
   
   def main():
       # Configuration
       config = Config(
           hw="auto",
           container="mkv",
           crf=20,
           preset="slow",
           notify=False,
           integrity_check=True
       )
       
       # Input/output directories
       input_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
       output_dir = input_dir / "converted"
       output_dir.mkdir(exist_ok=True)
       
       # Statistics
       converted = 0
       skipped = 0
       failed = 0
       
       # Process files
       for mkv_file in input_dir.glob("**/*.mkv"):
           print(f"Processing: {mkv_file.name}")
           
           success, output, msg = convert_file(
               mkv_file,
               cfg=config,
               output_dir=output_dir
           )
           
           if success and output:
               converted += 1
               print(f"  ✓ Converted: {output.name}")
           elif not success:
               failed += 1
               print(f"  ✗ Failed: {msg}")
           else:
               skipped += 1
               print(f"  ⊘ Skipped: {msg}")
       
       # Print summary
       print(f"\nSummary:")
       print(f"  Converted: {converted}")
       print(f"  Skipped: {skipped}")
       print(f"  Failed: {failed}")
       
       # Save to history
       dirs = get_app_dirs()
       history = HistoryDB(dirs["state"])
       # History is automatically updated by convert_file
       
       return 0 if failed == 0 else 1
   
   if __name__ == "__main__":
       sys.exit(main())

JSON Progress Output
--------------------

For integration with web UIs or monitoring tools, use the ``JSONProgressOutput`` class or the ``--json-progress`` CLI flag:

**CLI Usage:**

.. code-block:: bash

   mkv2cast --json-progress movie.mkv

This outputs JSON events to stdout:

.. code-block:: json

   {"version":"1.0","event":"start","overall":{"total_files":1,"backend":"vaapi"}}
   {"version":"1.0","event":"file_start","file":"movie.mkv"}
   {"version":"1.0","event":"progress","files":{"movie.mkv":{"progress_percent":45.2,"fps":120.5}}}
   {"version":"1.0","event":"file_done","file":"movie.mkv","status":"done"}
   {"version":"1.0","event":"complete"}

**Python Usage:**

.. code-block:: python

   import json
   import subprocess
   from typing import Generator, Dict, Any

   def stream_progress(filepath: str) -> Generator[Dict[str, Any], None, None]:
       """Stream JSON progress events from mkv2cast."""
       proc = subprocess.Popen(
           ["mkv2cast", "--json-progress", filepath],
           stdout=subprocess.PIPE,
           text=True
       )
       for line in proc.stdout:
           yield json.loads(line)

   # Example: Display progress
   for event in stream_progress("movie.mkv"):
       if event["event"] == "progress":
           for filename, data in event.get("files", {}).items():
               percent = data.get("progress_percent", 0)
               fps = data.get("fps", 0)
               eta = data.get("eta_seconds", 0)
               print(f"{filename}: {percent:.1f}% @ {fps:.1f}fps, ETA: {eta:.0f}s")

**Using JSONProgressOutput Directly:**

.. code-block:: python

   from mkv2cast import JSONProgressOutput
   import sys

   # Create a JSON progress output
   json_out = JSONProgressOutput(stream=sys.stdout)

   # Signal start
   json_out.start(total_files=5, backend="vaapi", encode_workers=1, integrity_workers=2)

   # Update file progress
   from pathlib import Path
   filepath = Path("movie.mkv")

   json_out.file_queued(filepath, duration_ms=3600000)  # 1 hour
   json_out.file_encoding_start(filepath)
   json_out.file_progress(
       filepath,
       frame=1000,
       fps=120.5,
       time_ms=60000,  # 1 minute
       bitrate="2500kbits/s",
       speed="2.5x"
   )
   json_out.file_done(filepath, output_path=Path("movie.h264.cast.mkv"))
   json_out.complete()

**JSON Event Types:**

- ``start``: Processing started, includes total files and backend info
- ``file_checking``: Integrity check started for a file
- ``file_start``: Encoding started for a file
- ``progress``: Progress update with percentage, FPS, ETA
- ``file_done``: File processing completed (done, skipped, or failed)
- ``complete``: All processing finished

**Progress Data Fields:**

.. code-block:: python

   {
       "filename": "movie.mkv",
       "filepath": "/path/to/movie.mkv",
       "status": "encoding",  # queued, checking, encoding, done, skipped, failed
       "progress_percent": 45.2,
       "current_time_ms": 1620000,
       "duration_ms": 3600000,
       "fps": 120.5,
       "speed": "2.5x",
       "bitrate": "2500kbits/s",
       "eta_seconds": 30.5,
       "started_at": 1704067200.0,
       "finished_at": null,
       "output_path": null,
       "error": null
   }

API Reference
------------

For complete API documentation, see :doc:`../api/index`.
