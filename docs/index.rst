mkv2cast Documentation
======================

**mkv2cast** is a smart MKV to Chromecast-compatible converter with hardware acceleration support.

.. image:: https://github.com/voldardard/mkv2cast/actions/workflows/ci.yml/badge.svg
   :target: https://github.com/voldardard/mkv2cast/actions/workflows/ci.yml
   :alt: CI

.. image:: https://github.com/voldardard/mkv2cast/actions/workflows/docs.yml/badge.svg
   :target: https://github.com/voldardard/mkv2cast/actions/workflows/docs.yml
   :alt: Documentation

.. image:: https://img.shields.io/pypi/v/mkv2cast.svg
   :target: https://pypi.org/project/mkv2cast/
   :alt: PyPI version

.. image:: https://img.shields.io/pypi/dm/mkv2cast
   :target: https://pypi.org/project/mkv2cast/
   :alt: Downloads

.. image:: https://img.shields.io/pypi/pyversions/mkv2cast.svg
   :target: https://pypi.org/project/mkv2cast/
   :alt: Python versions

.. image:: https://img.shields.io/github/license/voldardard/mkv2cast.svg
   :target: https://github.com/voldardard/mkv2cast/blob/main/LICENSE
   :alt: License

.. image:: https://img.shields.io/badge/code%20style-ruff-000000.svg
   :target: https://github.com/astral-sh/ruff
   :alt: Ruff

Features
--------

- **Intelligent codec detection** - Automatically detects H.264, H.265/HEVC, and AV1
- **Hardware acceleration** - Supports NVIDIA NVENC, AMD AMF, Intel QSV, and VAAPI (auto-pick)
- **Parallel processing** - Multi-threaded encoding with pipeline mode
- **Rich progress UI** - Beautiful progress display with multiple workers
- **Automatic audio selection** - Prefers French audio tracks (configurable)
- **Audio & subtitle selection** - Choose by language or explicit track index
- **Integrity checking** - Verifies files before processing
- **Watch mode** - Watchdog/inotify monitoring with optional systemd service
- **JSON progress** - Stream structured events for dashboards or integrations
- **XDG compliant** - Follows XDG Base Directory specification
- **Multi-language** - Supports EN, FR, ES, IT, DE
- **Desktop notifications** - Get notified when conversions complete

Quick Start
-----------

Installation:

.. code-block:: bash

   pip install mkv2cast

Usage:

.. code-block:: bash

   # Convert all MKV files in current directory
   mkv2cast

   # Convert a single file
   mkv2cast movie.mkv

   # Use CPU encoding with fast preset
   mkv2cast --hw cpu --preset fast

Contents
--------

.. toctree::
   :maxdepth: 2
   :caption: Getting Started

   getting-started/installation
   getting-started/quickstart
   getting-started/configuration

.. toctree::
   :maxdepth: 2
   :caption: Usage Guide

   usage/basic
   usage/advanced
   usage/hardware-acceleration
   usage/filtering
   usage/library-guide
   usage/python-api

.. toctree::
   :maxdepth: 2
   :caption: API Reference

   api/index

.. toctree::
   :maxdepth: 1
   :caption: Development

   contributing

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
