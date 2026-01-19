File Filtering
==============

mkv2cast provides powerful filtering options to control which files are processed.

Ignore Patterns
---------------

Ignore files matching glob patterns:

.. code-block:: bash

   # Ignore sample files
   mkv2cast -I "*sample*"

   # Ignore multiple patterns
   mkv2cast -I "*sample*" -I "*trailer*" -I "*.eng.*"

   # Long form
   mkv2cast --ignore-pattern "*sample*"

Ignore Paths
------------

Ignore specific directories:

.. code-block:: bash

   # Ignore by folder name
   mkv2cast --ignore-path Downloads
   mkv2cast --ignore-path temp

   # Ignore by full path
   mkv2cast --ignore-path "/media/videos/temp"

Include Patterns
----------------

Only process files matching patterns:

.. code-block:: bash

   # Only French files
   mkv2cast -i "*French*"

   # Only 2024 releases
   mkv2cast -i "*2024*"

   # Multiple patterns (OR logic)
   mkv2cast -i "*French*" -i "*2024*"

Include Paths
-------------

Only process files in specific directories:

.. code-block:: bash

   mkv2cast --include-path Movies
   mkv2cast --include-path "/media/films"

Combining Filters
-----------------

Filters can be combined:

.. code-block:: bash

   # French files, excluding samples
   mkv2cast -i "*French*" -I "*sample*"

   # Movies folder, excluding trailers
   mkv2cast --include-path Movies -I "*trailer*"

Filter Logic
------------

The filtering logic works as follows:

1. If include patterns/paths are set, file must match at least one
2. Then ignore patterns/paths are applied
3. Files matching ignore are excluded

Configuration File
------------------

Filters can be set in config:

.. code-block:: toml

   [scan]
   recursive = true
   ignore_patterns = ["*sample*", "*trailer*", "*featurette*"]
   ignore_paths = ["Downloads", "temp"]
   include_patterns = []
   include_paths = []

Common Patterns
---------------

**Media organization:**

.. code-block:: bash

   # Skip samples and extras
   mkv2cast -I "*sample*" -I "*trailer*" -I "*featurette*" -I "*deleted*"

**Language filtering:**

.. code-block:: bash

   # Only process French content
   mkv2cast -i "*French*" -i "*VFF*" -i "*TRUEFRENCH*"

**Year filtering:**

.. code-block:: bash

   # Only 2024-2025 content
   mkv2cast -i "*2024*" -i "*2025*"

**Quality filtering:**

.. code-block:: bash

   # Only 1080p content
   mkv2cast -i "*1080p*"

Automatic Skip Rules
--------------------

mkv2cast automatically skips:

- Hidden files (starting with ``.``)
- Previously converted files (containing ``.cast.``)
- Temporary files (containing ``.tmp.``)
- Files with conversion tags (``.h264.``, ``.aac.``, ``.remux.``)

Debug Filtering
---------------

Use debug mode to see filtering decisions:

.. code-block:: bash

   mkv2cast --debug

This shows why files are skipped or included.
