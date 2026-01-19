Library Usage Guide
===================

This guide provides comprehensive documentation for using mkv2cast as a Python library
in your applications.

.. contents:: Table of Contents
   :local:
   :depth: 3

Overview
--------

mkv2cast exposes a clean Python API that allows you to:

- Convert video files programmatically
- Monitor conversion progress via callbacks
- Process multiple files in parallel
- Integrate with your existing applications

Architecture
------------

The mkv2cast API is organized into several modules:

.. code-block:: text

   mkv2cast/
   ├── Config          # Configuration dataclass
   ├── convert_file()  # Single file conversion
   ├── convert_batch() # Parallel batch conversion
   ├── decide_for()    # Codec analysis
   ├── pick_backend()  # Backend selection
   └── HistoryDB       # Conversion history

Data Flow
~~~~~~~~~

The conversion process follows this flow:

.. code-block:: text

   Input File
       │
       ▼
   ┌─────────────────┐
   │ decide_for()    │ ─── Analyze codecs, determine if transcoding needed
   └────────┬────────┘
            │
            ▼
   ┌─────────────────┐
   │ pick_backend()  │ ─── Select best encoder (NVENC, QSV, VAAPI, CPU)
   └────────┬────────┘
            │
            ▼
   ┌─────────────────┐
   │ convert_file()  │ ─── Build FFmpeg command, run encoding
   └────────┬────────┘
            │
            ▼
      Output File

Quick Start
-----------

Minimal Example
~~~~~~~~~~~~~~~

.. code-block:: python

   from mkv2cast import convert_file, Config
   from pathlib import Path

   config = Config.for_library()
   success, output, msg = convert_file(Path("movie.mkv"), cfg=config)

With Progress Tracking
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from mkv2cast import convert_file, Config
   from pathlib import Path

   def on_progress(filepath, progress):
       print(f"{progress['stage']}: {progress['progress_percent']:.1f}%")

   config = Config.for_library(hw="vaapi")
   convert_file(Path("movie.mkv"), cfg=config, progress_callback=on_progress)

Configuration
-------------

Using Config.for_library()
~~~~~~~~~~~~~~~~~~~~~~~~~~

The recommended way to create a configuration for library usage:

.. code-block:: python

   from mkv2cast import Config

   # Basic usage - automatically disables UI features
   config = Config.for_library()

   # With custom options
   config = Config.for_library(
       hw="vaapi",           # Hardware acceleration
       crf=20,               # Quality (lower = better)
       preset="slow",        # Encoding preset
       container="mkv",      # Output format
       encode_workers=2,     # Parallel encoders for batch
   )

What Config.for_library() Does
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Automatically sets:

- ``progress=False`` - No progress bars
- ``notify=False`` - No desktop notifications
- ``pipeline=False`` - No Rich UI

This ensures clean operation when running as a library.

Manual Configuration
~~~~~~~~~~~~~~~~~~~~

You can also configure manually:

.. code-block:: python

   from mkv2cast import Config

   config = Config(
       # Output
       suffix=".cast",
       container="mkv",
       
       # Hardware
       hw="auto",            # "auto", "nvenc", "qsv", "vaapi", "cpu"
       vaapi_device="/dev/dri/renderD128",
       vaapi_qp=23,
       qsv_quality=23,
       nvenc_cq=23,
       
       # Encoding
       crf=20,               # CPU CRF (18-28)
       preset="slow",        # "ultrafast" to "veryslow"
       abr="192k",           # Audio bitrate
       
       # Behavior
       skip_when_ok=True,    # Skip compatible files
       force_h264=False,     # Force H264 transcoding
       allow_hevc=False,     # Allow HEVC passthrough
       
       # UI (disable for library)
       progress=False,
       notify=False,
       pipeline=False,
       
       # Workers
       encode_workers=2,
   )

Progress Callbacks
------------------

Callback Function Signature
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   def progress_callback(filepath: Path, progress: dict) -> None:
       """
       Called during conversion with progress updates.
       
       Args:
           filepath: Path to the file being processed
           progress: Dictionary with progress information
       """
       pass

Progress Dictionary
~~~~~~~~~~~~~~~~~~~

The ``progress`` dictionary contains:

.. code-block:: python

   {
       "stage": "encoding",        # "checking", "encoding", "done", "skipped", "failed"
       "progress_percent": 45.2,   # 0.0 to 100.0
       "fps": 120.5,               # Current FPS
       "eta_seconds": 30.5,        # Estimated time remaining
       "bitrate": "2500kbits/s",   # Current bitrate
       "speed": "2.5x",            # Encoding speed
       "current_time_ms": 1620000, # Current position
       "duration_ms": 3600000,     # Total duration
       "error": None,              # Error message if failed
   }

Stage Transitions
~~~~~~~~~~~~~~~~~

.. code-block:: text

   checking ──► encoding ──► done
       │            │
       │            └──► failed
       │
       └──► skipped (if compatible)
       │
       └──► failed (if integrity check fails)

Example: GUI Integration
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   import tkinter as tk
   from tkinter import ttk
   from mkv2cast import convert_file, Config
   from pathlib import Path
   import threading

   class ConversionGUI:
       def __init__(self):
           self.root = tk.Tk()
           self.progress = ttk.Progressbar(self.root, length=300)
           self.progress.pack(pady=20)
           self.label = tk.Label(self.root, text="Ready")
           self.label.pack()
           
       def on_progress(self, filepath, progress):
           # Update GUI from main thread
           self.root.after(0, self._update_gui, progress)
           
       def _update_gui(self, progress):
           self.progress["value"] = progress["progress_percent"]
           self.label["text"] = f"{progress['stage']}: {progress['progress_percent']:.1f}%"
           
       def convert(self, filepath):
           config = Config.for_library()
           threading.Thread(
               target=convert_file,
               args=(Path(filepath),),
               kwargs={"cfg": config, "progress_callback": self.on_progress}
           ).start()

Batch Processing
----------------

Using convert_batch()
~~~~~~~~~~~~~~~~~~~~~

Process multiple files in parallel:

.. code-block:: python

   from mkv2cast import convert_batch, Config
   from pathlib import Path

   config = Config.for_library(encode_workers=2)

   files = [
       Path("movie1.mkv"),
       Path("movie2.mkv"),
       Path("movie3.mkv"),
   ]

   results = convert_batch(files, cfg=config)

   for filepath, (success, output, msg) in results.items():
       print(f"{filepath.name}: {msg}")

Thread-Safe Callbacks
~~~~~~~~~~~~~~~~~~~~~

When using ``convert_batch()``, callbacks may be called from multiple threads.
The library handles thread safety internally, but your callback code should also be safe:

.. code-block:: python

   import threading
   from mkv2cast import convert_batch, Config

   progress_lock = threading.Lock()
   all_progress = {}

   def thread_safe_callback(filepath, progress):
       with progress_lock:
           all_progress[str(filepath)] = progress
           # Safe to access/modify shared state here

   config = Config.for_library(encode_workers=4)
   convert_batch(files, cfg=config, progress_callback=thread_safe_callback)

Controlling Parallelism
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   config = Config.for_library(
       encode_workers=4,    # 4 parallel encoding jobs
   )

- ``encode_workers=0``: Auto-detect (usually 1)
- ``encode_workers=1``: Sequential processing
- ``encode_workers=N``: N parallel jobs

Error Handling
--------------

Convert File Errors
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from mkv2cast import convert_file, Config
   from pathlib import Path

   config = Config.for_library()

   try:
       success, output, msg = convert_file(Path("movie.mkv"), cfg=config)
       
       if not success:
           print(f"Conversion failed: {msg}")
       elif output is None:
           print(f"File skipped: {msg}")
       else:
           print(f"Converted to: {output}")
           
   except Exception as e:
       print(f"Unexpected error: {e}")

Batch Error Handling
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from mkv2cast import convert_batch, Config

   results = convert_batch(files, cfg=config)

   failed_files = [
       (path, msg) 
       for path, (success, _, msg) in results.items() 
       if not success
   ]

   if failed_files:
       print("Failed files:")
       for path, msg in failed_files:
           print(f"  {path}: {msg}")

Callback Errors
~~~~~~~~~~~~~~~

Callback errors are caught and ignored to prevent affecting the conversion:

.. code-block:: python

   def buggy_callback(filepath, progress):
       raise Exception("Bug!")  # Won't stop conversion

   # Conversion continues despite callback error
   convert_file(path, cfg=config, progress_callback=buggy_callback)

Best Practices
--------------

1. Always Use Config.for_library()
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This ensures UI features are disabled:

.. code-block:: python

   # Good
   config = Config.for_library(hw="vaapi")

   # Avoid (may produce unwanted output)
   config = Config(hw="vaapi")

2. Handle All Result Cases
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   success, output, msg = convert_file(path, cfg=config)

   if success and output:
       # File was converted
       pass
   elif success and not output:
       # File was skipped (already compatible or dry run)
       pass
   else:
       # Conversion failed
       pass

3. Use Thread-Safe Callbacks for Batch
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   import threading

   lock = threading.Lock()

   def callback(filepath, progress):
       with lock:
           # Safe operations here
           pass

4. Set Appropriate Worker Count
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   import os

   # Don't use more workers than CPU cores
   config = Config.for_library(
       encode_workers=min(4, os.cpu_count() or 1)
   )

Troubleshooting
---------------

No Output When Expected
~~~~~~~~~~~~~~~~~~~~~~~

Check if file is already compatible:

.. code-block:: python

   from mkv2cast import decide_for
   
   decision = decide_for(path)
   print(f"Needs video transcode: {decision.need_v}")
   print(f"Needs audio transcode: {decision.need_a}")
   print(f"Reason: {decision.reason_v}")

Progress Callback Not Called
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Ensure you're passing the callback correctly:

.. code-block:: python

   # Correct
   convert_file(path, cfg=config, progress_callback=my_callback)

   # Wrong (callback as positional arg)
   convert_file(path, config, my_callback)

Backend Not Detected
~~~~~~~~~~~~~~~~~~~~

Test backend availability:

.. code-block:: python

   from mkv2cast import pick_backend, Config

   config = Config(hw="auto")
   backend = pick_backend(config)
   print(f"Selected backend: {backend}")

API Reference
-------------

For complete API documentation, see :doc:`../api/index`.
