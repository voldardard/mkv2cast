API Reference
=============

mkv2cast can be used as a Python library for programmatic video conversion.

Main Modules
------------

.. autosummary::
   :toctree: generated
   :recursive:

   mkv2cast
   mkv2cast.config
   mkv2cast.converter
   mkv2cast.history
   mkv2cast.integrity
   mkv2cast.notifications
   mkv2cast.i18n

Quick Reference
---------------

Configuration
~~~~~~~~~~~~~

.. code-block:: python

   from mkv2cast import Config, get_app_dirs, load_config_file

   # Create custom configuration
   config = Config(
       suffix=".cast",
       container="mkv",
       hw="auto",
       crf=20,
       preset="slow",
       notify=True
   )

   # Get application directories
   dirs = get_app_dirs()
   print(dirs["config"])  # ~/.config/mkv2cast

Conversion
~~~~~~~~~~

.. code-block:: python

   from mkv2cast import decide_for, pick_backend, convert_file
   from pathlib import Path

   # Analyze a file
   decision = decide_for(Path("movie.mkv"))
   print(f"Video: {decision.vcodec} -> need transcode: {decision.need_v}")
   print(f"Audio: {decision.acodec} -> need transcode: {decision.need_a}")

   # Auto-detect best backend
   backend = pick_backend()
   print(f"Using backend: {backend}")

   # Convert file
   success, output_path, message = convert_file(Path("movie.mkv"))

History
~~~~~~~

.. code-block:: python

   from mkv2cast import HistoryDB, get_app_dirs

   dirs = get_app_dirs()
   history = HistoryDB(dirs["state"])

   # Get recent conversions
   recent = history.get_recent(20)
   for entry in recent:
       print(f"{entry['status']}: {entry['input_path']}")

   # Get statistics
   stats = history.get_stats()
   print(f"Total done: {stats['by_status'].get('done', 0)}")

Notifications
~~~~~~~~~~~~~

.. code-block:: python

   from mkv2cast import send_notification

   # Send a notification
   send_notification(
       title="Conversion Complete",
       message="Successfully converted 5 files",
       urgency="normal"
   )

Internationalization
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from mkv2cast import setup_i18n, _

   # Setup French translations
   setup_i18n("fr")

   # Use translations
   print(_("Conversion complete"))  # "Conversion terminée"

Decision Class
--------------

.. autoclass:: mkv2cast.converter.Decision
   :members:
   :undoc-members:

Config Class
------------

.. autoclass:: mkv2cast.config.Config
   :members:
   :undoc-members:

HistoryDB Class
---------------

.. autoclass:: mkv2cast.history.HistoryDB
   :members:
   :undoc-members:
