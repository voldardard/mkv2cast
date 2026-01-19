Hardware Acceleration
=====================

mkv2cast supports hardware-accelerated encoding for faster conversions.

Supported Backends
------------------

- **NVENC** - NVIDIA GPU encoding (fastest)
- **AMF** - AMD GPU encoding (AMD VCE/VCN)
- **QSV** - Intel Quick Sync Video
- **VAAPI** - Video Acceleration API (AMD, Intel)
- **CPU** - Software encoding with libx264 (most compatible)

Backend Selection
-----------------

**Automatic detection (default):**

.. code-block:: bash

   mkv2cast --hw auto

The auto mode tests backends in order: NVENC → AMF → QSV → VAAPI → CPU

**Force specific backend:**

.. code-block:: bash

   mkv2cast --hw nvenc   # NVIDIA GPU
   mkv2cast --hw qsv     # Intel Quick Sync
   mkv2cast --hw vaapi   # Intel/AMD VAAPI
   mkv2cast --hw cpu     # Software encoding

NVIDIA NVENC
------------

NVENC provides the fastest encoding on NVIDIA GPUs (GTX 600+ series).

**Enable NVENC:**

.. code-block:: bash

   mkv2cast --hw nvenc

**Quality parameter (0-51, lower = better):**

.. code-block:: bash

   # High quality
   mkv2cast --hw nvenc --nvenc-cq 20

   # Default quality
   mkv2cast --hw nvenc --nvenc-cq 23

   # Lower quality, faster
   mkv2cast --hw nvenc --nvenc-cq 28

**Requirements:**

- NVIDIA GPU (GTX 600+ series, or RTX)
- NVIDIA drivers installed
- FFmpeg compiled with NVENC support

VAAPI Configuration
-------------------

VAAPI is used for AMD and Intel GPUs.

**Default device:**

.. code-block:: bash

   mkv2cast --hw vaapi

**Custom device:**

.. code-block:: bash

   mkv2cast --hw vaapi --vaapi-device /dev/dri/renderD129

**Quality parameter:**

.. code-block:: bash

   # Lower QP = better quality
   mkv2cast --hw vaapi --vaapi-qp 20

Intel Quick Sync (QSV)
----------------------

**Enable QSV:**

.. code-block:: bash

   mkv2cast --hw qsv

**Quality parameter:**

.. code-block:: bash

   # Lower value = better quality
   mkv2cast --hw qsv --qsv-quality 20

CPU Encoding
------------

Software encoding is the most compatible but slowest.

**Presets (faster → better quality):**

- ultrafast
- superfast
- veryfast
- faster
- fast
- medium
- slow (default)
- slower
- veryslow

.. code-block:: bash

   mkv2cast --hw cpu --preset fast
   mkv2cast --hw cpu --preset veryslow

**CRF quality (0-51, lower = better):**

.. code-block:: bash

   # High quality
   mkv2cast --hw cpu --crf 18

   # Default quality
   mkv2cast --hw cpu --crf 20

   # Lower quality, smaller file
   mkv2cast --hw cpu --crf 24

Checking Hardware Support
-------------------------

.. code-block:: bash

   mkv2cast --check-requirements

This will show:

- Available encoders (h264_vaapi, h264_qsv)
- VAAPI device status
- GPU detection

Performance Comparison
----------------------

Approximate encoding speed on typical hardware:

+----------+-------------+------------------+
| Backend  | Speed (fps) | Quality          |
+==========+=============+==================+
| NVENC    | 300-500     | Good             |
+----------+-------------+------------------+
| AMF      | 250-450     | Good             |
+----------+-------------+------------------+
| QSV      | 200-400     | Good             |
+----------+-------------+------------------+
| VAAPI    | 150-300     | Good             |
+----------+-------------+------------------+
| CPU slow | 10-30       | Excellent        |
+----------+-------------+------------------+
| CPU fast | 50-100      | Good             |
+----------+-------------+------------------+

Troubleshooting
---------------

**NVENC not detected:**

1. Check NVIDIA driver: ``nvidia-smi``
2. Check encoder: ``ffmpeg -encoders | grep nvenc``
3. Install CUDA toolkit if needed

**AMF not detected:**

1. Check AMD GPU: ``lspci | grep -i amd``
2. Check encoder: ``ffmpeg -encoders | grep amf``
3. Ensure FFmpeg is compiled with AMF support

**VAAPI not detected:**

1. Check device exists: ``ls -la /dev/dri/``
2. Check permissions: ``groups | grep video``
3. Add user to video group: ``sudo usermod -aG video $USER``

**QSV not working:**

1. Ensure Intel GPU is available
2. Install Intel media driver
3. Check with: ``vainfo``

**Fallback to CPU:**

If hardware encoding fails, mkv2cast falls back to CPU automatically.
