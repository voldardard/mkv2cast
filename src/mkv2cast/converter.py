"""
Core conversion logic for mkv2cast.

Contains:
- Codec detection and decision logic
- Backend selection (VAAPI, QSV, CPU)
- FFmpeg command building
- File conversion functions
- Progress callback support for library usage
- Batch processing with multi-threading
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from mkv2cast.config import CFG, Config

# -------------------- UTILITY FUNCTIONS --------------------


def run_quiet(cmd: List[str], timeout: float = 10.0) -> bool:
    """Run a command quietly, return True if successful."""
    try:
        p = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout)
        return p.returncode == 0
    except Exception:
        return False


def ffprobe_json(path: Path) -> Dict[str, Any]:
    """Run ffprobe and return JSON output."""
    cmd = ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)]
    out = subprocess.check_output(cmd)
    result: Dict[str, Any] = json.loads(out)
    return result


def probe_duration_ms(path: Path, debug: bool = False) -> int:
    """Get video duration in milliseconds."""
    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-of",
            "json",
            "-show_entries",
            "format=duration:stream=codec_type,duration",
            str(path),
        ]
        j = json.loads(subprocess.check_output(cmd))
        dur = None
        if "format" in j and j["format"].get("duration"):
            dur = float(j["format"]["duration"])
        if (dur is None or dur <= 0) and "streams" in j:
            for s in j["streams"]:
                if s.get("codec_type") == "video" and s.get("duration"):
                    d2 = float(s["duration"])
                    if d2 > 0:
                        dur = d2
                        break
        if dur is None or dur <= 0:
            return 0
        return int(dur * 1000)
    except Exception:
        return 0


def file_size(path: Path) -> int:
    """Get file size in bytes."""
    try:
        return path.stat().st_size
    except Exception:
        return 0


def _mb_to_bytes(mb: int) -> int:
    """Convert MB to bytes (0 for invalid values)."""
    try:
        return max(0, int(mb)) * 1024 * 1024
    except Exception:
        return 0


def check_disk_space(
    output_dir: Path,
    tmp_dir: Optional[Path],
    estimated_bytes: int,
    cfg: Config,
) -> Optional[str]:
    """Return error message if disk guard would be violated, else None."""
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    min_free_out = _mb_to_bytes(cfg.disk_min_free_mb)
    if min_free_out > 0:
        try:
            usage = shutil.disk_usage(str(output_dir))
            if usage.free - estimated_bytes < min_free_out:
                return f"Insufficient free space in {output_dir} (min {cfg.disk_min_free_mb} MB)"
        except Exception:
            pass

    if tmp_dir is not None and cfg.disk_min_free_tmp_mb > 0:
        try:
            if output_dir.exists() and tmp_dir.exists():
                if output_dir.stat().st_dev != tmp_dir.stat().st_dev:
                    usage = shutil.disk_usage(str(tmp_dir))
                    min_free_tmp = _mb_to_bytes(cfg.disk_min_free_tmp_mb)
                    if usage.free - estimated_bytes < min_free_tmp:
                        return f"Insufficient temp space in {tmp_dir} (min {cfg.disk_min_free_tmp_mb} MB)"
        except Exception:
            pass

    return None


def enforce_output_quota(output_path: Path, input_size: int, cfg: Config) -> Optional[str]:
    """Return error message if output exceeds quota, else None."""
    try:
        out_size = output_path.stat().st_size
    except Exception:
        return None

    if cfg.max_output_mb > 0:
        max_bytes = _mb_to_bytes(cfg.max_output_mb)
        if max_bytes > 0 and out_size > max_bytes:
            return f"Output exceeds max size ({cfg.max_output_mb} MB)"

    if cfg.max_output_ratio > 0 and input_size > 0:
        if out_size > int(input_size * cfg.max_output_ratio):
            return f"Output exceeds max ratio ({cfg.max_output_ratio:.2f}x)"

    return None


# -------------------- BACKEND SELECTION --------------------


def have_encoder(name: str) -> bool:
    """Check if ffmpeg has the specified encoder."""
    try:
        result = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=4.0)
        # Search for the encoder name in the output
        for line in result.stdout.split("\n"):
            # Format is like: " V....D libx264    description..."
            parts = line.split()
            if len(parts) >= 2 and parts[1] == name:
                return True
        return False
    except Exception:
        return False


def test_qsv(vaapi_device: str = "/dev/dri/renderD128") -> bool:
    """Test if QSV encoding works."""
    if not Path(vaapi_device).exists():
        return False
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-init_hw_device",
        f"qsv=hw:{vaapi_device}",
        "-filter_hw_device",
        "hw",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=128x128:rate=30",
        "-t",
        "0.2",
        "-vf",
        "format=nv12",
        "-c:v",
        "h264_qsv",
        "-global_quality",
        "35",
        "-an",
        "-f",
        "null",
        "-",
    ]
    return run_quiet(cmd, timeout=6.0)


def test_vaapi(vaapi_device: str = "/dev/dri/renderD128") -> bool:
    """Test if VAAPI encoding works."""
    if not Path(vaapi_device).exists():
        return False
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-vaapi_device",
        vaapi_device,
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=128x128:rate=30",
        "-t",
        "0.2",
        "-vf",
        "format=nv12,hwupload",
        "-c:v",
        "h264_vaapi",
        "-qp",
        "35",
        "-an",
        "-f",
        "null",
        "-",
    ]
    return run_quiet(cmd, timeout=6.0)


def test_nvenc() -> bool:
    """Test if NVIDIA NVENC encoding works."""
    # Check if nvidia-smi is available (indicates NVIDIA driver)
    try:
        subprocess.run(["nvidia-smi"], capture_output=True, timeout=5.0, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False

    # Check if h264_nvenc encoder is available
    if not have_encoder("h264_nvenc"):
        return False

    # Test actual encoding
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=128x128:rate=30",
        "-t",
        "0.2",
        "-c:v",
        "h264_nvenc",
        "-preset",
        "p4",
        "-cq",
        "23",
        "-an",
        "-f",
        "null",
        "-",
    ]
    return run_quiet(cmd, timeout=6.0)


def test_amf() -> bool:
    """Test if AMD AMF encoding works."""
    # Check if h264_amf encoder is available
    if not have_encoder("h264_amf"):
        return False

    # Test actual encoding
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=128x128:rate=30",
        "-t",
        "0.2",
        "-c:v",
        "h264_amf",
        "-quality",
        "balanced",
        "-rc",
        "cqp",
        "-qp_i",
        "23",
        "-qp_p",
        "23",
        "-qp_b",
        "23",
        "-an",
        "-f",
        "null",
        "-",
    ]
    return run_quiet(cmd, timeout=6.0)


def pick_backend(cfg: Optional[Config] = None) -> str:
    """
    Select the best available encoding backend.

    Args:
        cfg: Config instance (uses global CFG if not provided).

    Returns:
        Backend name: "nvenc", "qsv", "vaapi", or "cpu".
    """
    if cfg is None:
        cfg = CFG

    if cfg.hw != "auto":
        return cfg.hw
    # Priority: NVENC > AMF > QSV > VAAPI > CPU
    if have_encoder("h264_nvenc") and test_nvenc():
        return "nvenc"
    if have_encoder("h264_amf") and test_amf():
        return "amf"
    if have_encoder("h264_qsv") and test_qsv(cfg.vaapi_device):
        return "qsv"
    if have_encoder("h264_vaapi") and test_vaapi(cfg.vaapi_device):
        return "vaapi"
    return "cpu"


def video_args_for(backend: str, cfg: Optional[Config] = None) -> List[str]:
    """Get ffmpeg video encoding arguments for the specified backend."""
    if cfg is None:
        cfg = CFG

    if backend == "nvenc":
        # NVIDIA NVENC encoding
        # Presets: p1 (fastest) to p7 (slowest/best quality)
        # Map CPU presets to NVENC presets
        nvenc_preset_map = {
            "ultrafast": "p1",
            "superfast": "p2",
            "veryfast": "p3",
            "faster": "p4",
            "fast": "p4",
            "medium": "p5",
            "slow": "p6",
            "slower": "p7",
            "veryslow": "p7",
        }
        nvenc_preset = nvenc_preset_map.get(cfg.preset, "p4")
        return [
            "-c:v",
            "h264_nvenc",
            "-preset",
            nvenc_preset,
            "-cq",
            str(cfg.nvenc_cq),
            "-profile:v",
            "high",
            "-level",
            "4.1",
            "-rc",
            "vbr",
            "-b:v",
            "0",
        ]
    if backend == "amf":
        # AMD AMF encoding
        # Quality modes: speed, balanced, quality
        # Map CPU presets to AMF quality modes
        amf_quality_map = {
            "ultrafast": "speed",
            "superfast": "speed",
            "veryfast": "speed",
            "faster": "balanced",
            "fast": "balanced",
            "medium": "balanced",
            "slow": "quality",
            "slower": "quality",
            "veryslow": "quality",
        }
        amf_quality_mode = amf_quality_map.get(cfg.preset, "balanced")
        return [
            "-c:v",
            "h264_amf",
            "-quality",
            amf_quality_mode,
            "-rc",
            "cqp",  # Constant Quantization Parameter
            "-qp_i",
            str(cfg.amf_quality),
            "-qp_p",
            str(cfg.amf_quality),
            "-qp_b",
            str(cfg.amf_quality),
            "-profile:v",
            "high",
            "-level",
            "4.1",
        ]
    if backend == "qsv":
        return [
            "-vf",
            "format=nv12",
            "-c:v",
            "h264_qsv",
            "-global_quality",
            str(cfg.qsv_quality),
            "-profile:v",
            "high",
            "-level",
            "4.1",
        ]
    if backend == "vaapi":
        return [
            "-vaapi_device",
            cfg.vaapi_device,
            "-vf",
            "format=nv12,hwupload",
            "-c:v",
            "h264_vaapi",
            "-qp",
            str(cfg.vaapi_qp),
            "-profile:v",
            "high",
            "-level",
            "4.1",
        ]
    if backend == "cpu":
        return [
            "-c:v",
            "libx264",
            "-preset",
            cfg.preset,
            "-crf",
            str(cfg.crf),
            "-pix_fmt",
            "yuv420p",
            "-profile:v",
            "high",
            "-level",
            "4.1",
        ]
    raise RuntimeError(f"Unknown backend: {backend}")


# -------------------- DECISION LOGIC --------------------


@dataclass
class Decision:
    """Decision about what transcoding is needed for a file."""

    need_v: bool  # Need to transcode video
    need_a: bool  # Need to transcode audio
    aidx: int  # Audio stream index to use (-1 if none)
    add_silence: bool  # Add silent audio track
    reason_v: str  # Reason for video decision
    vcodec: str  # Source video codec
    vpix: str  # Source pixel format
    vbit: int  # Source bit depth
    vhdr: bool  # Is HDR content
    vprof: str  # Video profile
    vlevel: int  # Video level
    acodec: str  # Source audio codec
    ach: int  # Audio channels
    alang: str  # Audio language
    format_name: str  # Container format name
    # Subtitle info
    sidx: int = -1  # Subtitle stream index to use (-1 if none)
    slang: str = ""  # Subtitle language
    sforced: bool = False  # Is forced subtitle


def parse_bitdepth_from_pix(pix: str) -> int:
    """Parse bit depth from pixel format string."""
    pix = (pix or "").lower()
    m = re.search(r"(10|12)le", pix)
    if m:
        return int(m.group(1))
    if "p010" in pix:
        return 10
    return 8


def is_audio_description(title: str) -> bool:
    """Check if audio track is an audio description track."""
    t = (title or "").lower()
    return (
        "audio description" in t
        or "audio-description" in t
        or "audiodescription" in t
        or "visual impaired" in t
        or " v.i" in t
        or " ad" in t
    )


def select_audio_track(streams: List[dict], cfg: Optional["Config"] = None) -> Tuple[Optional[dict], str]:
    """
    Select the best audio track based on user preferences.

    Priority:
    1. Explicit track index (--audio-track)
    2. Language priority list (--audio-lang)
    3. Default French preference (fre, fra, fr)
    4. First audio track

    Args:
        streams: List of stream dictionaries from ffprobe.
        cfg: Config instance.

    Returns:
        Tuple of (selected_stream, selected_language).
    """
    if cfg is None:
        from mkv2cast.config import CFG

        cfg = CFG

    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    if not audio_streams:
        return None, ""

    def get_lang(s: dict) -> str:
        return (s.get("tags") or {}).get("language", "").lower()

    def get_title(s: dict) -> str:
        return (s.get("tags") or {}).get("title", "")

    # 1. Explicit track index
    if cfg.audio_track is not None:
        if 0 <= cfg.audio_track < len(audio_streams):
            selected = audio_streams[cfg.audio_track]
            return selected, get_lang(selected)

    # 2. Language priority list from config
    if cfg.audio_lang:
        langs = [lang.strip().lower() for lang in cfg.audio_lang.split(",")]
        for lang in langs:
            # First pass: match language, exclude audio descriptions
            for stream in audio_streams:
                stream_lang = get_lang(stream)
                if (stream_lang == lang or stream_lang.startswith(lang)) and not is_audio_description(
                    get_title(stream)
                ):
                    return stream, stream_lang
            # Second pass: match language, include audio descriptions
            for stream in audio_streams:
                stream_lang = get_lang(stream)
                if stream_lang == lang or stream_lang.startswith(lang):
                    return stream, stream_lang

    # 3. Default: prefer French (fre, fra, fr)
    fr_langs = {"fre", "fra", "fr"}
    # First pass: French without audio description
    for stream in audio_streams:
        stream_lang = get_lang(stream)
        if stream_lang in fr_langs and not is_audio_description(get_title(stream)):
            return stream, stream_lang
    # Second pass: French with audio description
    for stream in audio_streams:
        stream_lang = get_lang(stream)
        if stream_lang in fr_langs:
            return stream, stream_lang

    # 4. Fallback: first audio track
    return audio_streams[0], get_lang(audio_streams[0])


def select_subtitle_track(
    streams: List[dict], audio_lang: str, cfg: Optional["Config"] = None
) -> Optional[Tuple[dict, bool]]:
    """
    Select the best subtitle track based on user preferences.

    Priority:
    1. Explicit track index (--subtitle-track)
    2. Forced subtitles in audio language (if --prefer-forced-subs)
    3. Language priority list (--subtitle-lang)
    4. No subtitles selected

    Args:
        streams: List of stream dictionaries from ffprobe.
        audio_lang: The language of the selected audio track.
        cfg: Config instance.

    Returns:
        Tuple of (selected_stream, is_forced) or None if no subtitle selected.
    """
    if cfg is None:
        from mkv2cast.config import CFG

        cfg = CFG

    # Disabled subtitles
    if cfg.no_subtitles:
        return None

    subtitle_streams = [s for s in streams if s.get("codec_type") == "subtitle"]
    if not subtitle_streams:
        return None

    def get_lang(s: dict) -> str:
        return (s.get("tags") or {}).get("language", "").lower()

    def is_forced(s: dict) -> bool:
        disposition = s.get("disposition") or {}
        return disposition.get("forced", 0) == 1

    def is_sdh(s: dict) -> bool:
        """Check if subtitle is SDH (for hearing impaired)."""
        disposition = s.get("disposition") or {}
        title = (s.get("tags") or {}).get("title", "").lower()
        return disposition.get("hearing_impaired", 0) == 1 or "sdh" in title

    # 1. Explicit track index
    if cfg.subtitle_track is not None:
        if 0 <= cfg.subtitle_track < len(subtitle_streams):
            selected = subtitle_streams[cfg.subtitle_track]
            return selected, is_forced(selected)

    # 2. Prefer forced subtitles in audio language
    if cfg.prefer_forced_subs and audio_lang:
        # Normalize audio language for comparison
        audio_lang_norm = audio_lang[:2] if len(audio_lang) >= 2 else audio_lang
        for stream in subtitle_streams:
            stream_lang = get_lang(stream)
            stream_lang_norm = stream_lang[:2] if len(stream_lang) >= 2 else stream_lang
            if is_forced(stream) and (stream_lang == audio_lang or stream_lang_norm == audio_lang_norm):
                return stream, True

    # 3. Language priority list
    if cfg.subtitle_lang:
        langs = [lang.strip().lower() for lang in cfg.subtitle_lang.split(",")]
        for lang in langs:
            # First pass: forced subtitles in requested language
            for stream in subtitle_streams:
                stream_lang = get_lang(stream)
                if (stream_lang == lang or stream_lang.startswith(lang)) and is_forced(stream):
                    return stream, True
            # Second pass: non-SDH subtitles in requested language
            for stream in subtitle_streams:
                stream_lang = get_lang(stream)
                if (stream_lang == lang or stream_lang.startswith(lang)) and not is_sdh(stream):
                    return stream, is_forced(stream)
            # Third pass: any subtitle in requested language
            for stream in subtitle_streams:
                stream_lang = get_lang(stream)
                if stream_lang == lang or stream_lang.startswith(lang):
                    return stream, is_forced(stream)

    # 4. No subtitle selected by default (user must specify --subtitle-lang)
    return None


def decide_for(path: Path, cfg: Optional[Config] = None) -> Decision:
    """
    Analyze a file and decide what transcoding is needed.

    Args:
        path: Path to the MKV file.
        cfg: Config instance (uses global CFG if not provided).

    Returns:
        Decision dataclass with transcoding requirements.
    """
    if cfg is None:
        cfg = CFG

    j = ffprobe_json(path)
    fmt = j.get("format", {}) or {}
    format_name = fmt.get("format_name", "") or ""

    streams = j.get("streams", []) or []
    v = next((s for s in streams if s.get("codec_type") == "video"), None)

    def low(x):
        return (x or "").lower()

    vcodec = low((v or {}).get("codec_name", ""))
    vpix = low((v or {}).get("pix_fmt", ""))
    vprof = low((v or {}).get("profile", ""))
    vlevel = int((v or {}).get("level") or 0)
    vbit = parse_bitdepth_from_pix(vpix)

    cprim = low((v or {}).get("color_primaries", ""))
    ctrans = low((v or {}).get("color_transfer", ""))
    vhdr = (cprim in {"bt2020", "bt2020nc", "bt2020c"}) or (ctrans in {"smpte2084", "arib-std-b67"})

    # Audio track selection using new function
    audio_stream, alang = select_audio_track(streams, cfg)

    aidx = int(audio_stream.get("index") or -1) if audio_stream else -1
    acodec = low((audio_stream or {}).get("codec_name", ""))
    ach = int((audio_stream or {}).get("channels") or 0)

    # Subtitle track selection using new function
    subtitle_result = select_subtitle_track(streams, alang, cfg)
    sidx = -1
    slang = ""
    sforced = False
    if subtitle_result:
        sub_stream, sforced = subtitle_result
        sidx = int(sub_stream.get("index") or -1)
        slang = (sub_stream.get("tags") or {}).get("language", "")

    pname = path.name.upper()
    reason_v = ""
    video_ok = False

    if vcodec == "av1" or "AV1" in pname:
        video_ok = False
        reason_v = "AV1 (or filename AV1) => forced transcode"
    elif cfg.force_h264:
        video_ok = False
        reason_v = "--force-h264"
    elif vcodec == "h264":
        if (
            vbit <= 8
            and vpix in {"yuv420p", "yuvj420p"}
            and (not vhdr)
            and vprof not in {"high 10", "high10", "high 4:2:2", "high 4:4:4"}
            and (vlevel == 0 or vlevel <= 41)
        ):
            video_ok = True
            reason_v = "H264 8-bit SDR"
        else:
            video_ok = False
            reason_v = f"H264 constraints not OK (bit={vbit},pix={vpix},hdr={vhdr},prof={vprof},level={vlevel})"
    elif vcodec in {"hevc", "h265"}:
        if cfg.allow_hevc and (vbit <= 8) and (not vhdr):
            video_ok = True
            reason_v = "HEVC SDR 8-bit (--allow-hevc)"
        else:
            video_ok = False
            reason_v = "HEVC => transcode (default)"
    else:
        video_ok = False
        reason_v = f"video codec {vcodec} => transcode"

    need_v = not video_ok

    audio_ok = acodec in {"aac", "mp3"}
    need_a = False
    if aidx < 0:
        need_a = False
    elif cfg.force_aac:
        need_a = True
    elif not audio_ok:
        need_a = True

    add_silence = False
    if aidx < 0 and cfg.add_silence_if_no_audio:
        add_silence = True
        need_a = True

    return Decision(
        need_v=need_v,
        need_a=need_a,
        aidx=aidx,
        add_silence=add_silence,
        reason_v=reason_v,
        vcodec=vcodec,
        vpix=vpix,
        vbit=vbit,
        vhdr=vhdr,
        vprof=vprof,
        vlevel=vlevel,
        acodec=acodec,
        ach=ach,
        alang=alang,
        format_name=format_name,
        sidx=sidx,
        slang=slang,
        sforced=sforced,
    )


# -------------------- FFMPEG COMMAND BUILDING --------------------


def build_transcode_cmd(
    inp: Path,
    decision: Decision,
    backend: str,
    tmp_out: Path,
    log_path: Optional[Path] = None,
    cfg: Optional[Config] = None,
) -> Tuple[List[str], str]:
    """
    Build ffmpeg transcoding command.

    Args:
        inp: Input file path.
        decision: Decision dataclass with transcoding requirements.
        backend: Encoding backend to use.
        tmp_out: Temporary output path.
        log_path: Optional path to write command log.
        cfg: Config instance.

    Returns:
        Tuple of (command_args, stage_name).
    """
    if cfg is None:
        cfg = CFG

    ext = cfg.container
    if ext not in ("mkv", "mp4"):
        raise RuntimeError("container must be mkv or mp4")

    args = ["ffmpeg", "-hide_banner", "-y"]

    if ext == "mkv":
        args += ["-f", "matroska"]
    else:
        args += ["-f", "mp4", "-movflags", "+faststart"]

    if decision.add_silence:
        args += ["-i", str(inp), "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
        args += ["-map", "0:v:0", "-map", "1:a:0"]
        # Map selected subtitle or all subtitles
        if decision.sidx >= 0:
            args += ["-map", f"0:{decision.sidx}"]
        else:
            args += ["-map", "0:s?"]
        args += ["-shortest"]
    else:
        args += ["-i", str(inp), "-map", "0:v:0"]
        if decision.aidx >= 0:
            args += ["-map", f"0:{decision.aidx}"]
        # Map selected subtitle or all subtitles
        if decision.sidx >= 0:
            args += ["-map", f"0:{decision.sidx}"]
        elif not cfg.no_subtitles:
            args += ["-map", "0:s?"]

    if not decision.need_v:
        args += ["-c:v", "copy"]
    else:
        args += video_args_for(backend, cfg)

    if decision.add_silence:
        args += ["-c:a", "aac", "-b:a", cfg.abr, "-ac", "2"]
    else:
        if decision.aidx >= 0:
            if not decision.need_a:
                args += ["-c:a", "copy"]
            else:
                args += ["-c:a", "aac", "-b:a", cfg.abr]
                if not cfg.keep_surround:
                    args += ["-ac", "2"]

    if ext == "mkv":
        args += ["-c:s", "copy"]
    else:
        args += ["-c:s", "mov_text"]

    if cfg.preserve_metadata:
        args += ["-map_metadata", "0"]
    else:
        args += ["-map_metadata", "-1"]

    if cfg.preserve_chapters:
        args += ["-map_chapters", "0"]
    else:
        args += ["-map_chapters", "-1"]

    if cfg.preserve_attachments and ext == "mkv":
        args += ["-map", "0:t?", "-c:t", "copy"]

    args += ["-max_muxing_queue_size", "2048"]
    args += [str(tmp_out)]

    stage = "TRANSCODE"
    if (not decision.need_v) and decision.need_a:
        stage = "AUDIO"
    elif (not decision.need_v) and (not decision.need_a):
        stage = "REMUX"

    if log_path:
        with log_path.open("a", encoding="utf-8", errors="replace") as lf:
            lf.write("CMD: " + shlex.join(args) + "\n")

    return args, stage


# -------------------- PROGRESS PARSING --------------------


def parse_ffmpeg_progress(line: str, dur_ms: int) -> Dict[str, Any]:
    """
    Parse FFmpeg progress line and return progress metrics.

    Args:
        line: A line from FFmpeg stderr output.
        dur_ms: Total duration in milliseconds.

    Returns:
        Dict with progress metrics:
        - progress_percent: float (0-100)
        - fps: float
        - speed: str (e.g., "2.5x")
        - bitrate: str (e.g., "2500kbits/s")
        - current_time_ms: int
        - frame: int
        - size_bytes: int
    """
    result: Dict[str, Any] = {
        "progress_percent": 0.0,
        "fps": 0.0,
        "speed": "",
        "bitrate": "",
        "current_time_ms": 0,
        "frame": 0,
        "size_bytes": 0,
    }

    # Parse time: time=00:01:23.45 (some ffmpeg builds may use comma as decimal separator)
    # Accept both dot and comma and flexible hour width to be robust across versions/locales.
    m = re.search(r"time=\s*(\d+):(\d+):(\d+)[\.,](\d+)", line)
    if m:
        h, mi, s, cs = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        current_ms = (h * 3600 + mi * 60 + s) * 1000 + cs * 10
        result["current_time_ms"] = current_ms
        if dur_ms > 0:
            result["progress_percent"] = min(100.0, (current_ms / dur_ms) * 100)

    # Parse fps: fps=123.45
    m = re.search(r"fps=\s*([0-9.]+)", line)
    if m:
        try:
            result["fps"] = float(m.group(1))
        except ValueError:
            pass

    # Parse speed: speed=2.5x
    m = re.search(r"speed=\s*([0-9.]+)x", line)
    if m:
        result["speed"] = f"{float(m.group(1)):.1f}x"

    # Parse bitrate: bitrate=2500kbits/s
    m = re.search(r"bitrate=\s*([^\s]+)", line)
    if m:
        result["bitrate"] = m.group(1)

    # Parse frame: frame=12345
    m = re.search(r"frame=\s*(\d+)", line)
    if m:
        result["frame"] = int(m.group(1))

    # Parse size: size=12345kB
    m = re.search(r"size=\s*(\d+)kB", line)
    if m:
        result["size_bytes"] = int(m.group(1)) * 1024

    return result


def calculate_eta(current_time_ms: int, dur_ms: int, speed_str: str, start_time: float) -> float:
    """
    Calculate ETA in seconds based on progress.

    Args:
        current_time_ms: Current position in milliseconds.
        dur_ms: Total duration in milliseconds.
        speed_str: Speed string like "2.5x".
        start_time: Start time (time.time()).

    Returns:
        Estimated time remaining in seconds.
    """
    if current_time_ms <= 0 or dur_ms <= 0:
        return 0.0

    remaining_ms = dur_ms - current_time_ms
    if remaining_ms <= 0:
        return 0.0

    # Try speed-based ETA first
    if speed_str:
        m = re.match(r"([0-9.]+)x", speed_str)
        if m:
            try:
                speed_x = float(m.group(1))
                if speed_x > 0:
                    return (remaining_ms / 1000.0) / speed_x
            except ValueError:
                pass

    # Fallback to elapsed-time based ETA
    elapsed = time.time() - start_time
    if elapsed > 0 and current_time_ms > 0:
        rate = current_time_ms / elapsed
        if rate > 0:
            return remaining_ms / rate / 1000.0

    return 0.0


# -------------------- CALLBACK TYPES --------------------


# Type alias for progress callback
ProgressCallback = Callable[[Path, Dict[str, Any]], None]


def _make_progress_dict(
    stage: str,
    progress_percent: float = 0.0,
    fps: float = 0.0,
    eta_seconds: float = 0.0,
    bitrate: str = "",
    speed: str = "",
    current_time_ms: int = 0,
    duration_ms: int = 0,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a standardized progress dictionary for callbacks."""
    return {
        "stage": stage,
        "progress_percent": progress_percent,
        "fps": fps,
        "eta_seconds": eta_seconds,
        "bitrate": bitrate,
        "speed": speed,
        "current_time_ms": current_time_ms,
        "duration_ms": duration_ms,
        "error": error,
    }


# -------------------- HIGH-LEVEL CONVERSION --------------------


def get_output_tag(decision: Decision) -> str:
    """Get the output filename tag based on decision."""
    tag = ""
    if decision.need_v:
        tag += ".h264"
    if decision.need_a:
        tag += ".aac"
    if not tag:
        tag = ".remux"
    return tag


def convert_file(
    input_path: Path,
    cfg: Optional[Config] = None,
    backend: Optional[str] = None,
    output_dir: Optional[Path] = None,
    log_path: Optional[Path] = None,
    progress_callback: Optional[ProgressCallback] = None,
) -> Tuple[bool, Optional[Path], str]:
    """
    Convert a single MKV file.

    Args:
        input_path: Path to input MKV file.
        cfg: Config instance (uses global CFG if not provided).
        backend: Backend to use (auto-detected if not provided).
        output_dir: Output directory (same as input if not provided).
        log_path: Path for conversion log.
        progress_callback: Optional callback function called with progress updates.
            The callback receives (filepath, progress_dict) where progress_dict contains:
            - stage: "checking" | "encoding" | "done" | "skipped" | "failed"
            - progress_percent: float (0-100)
            - fps: float
            - eta_seconds: float
            - bitrate: str
            - speed: str
            - current_time_ms: int
            - duration_ms: int
            - error: Optional[str]

    Returns:
        Tuple of (success, output_path, message).

    Example:
        >>> def on_progress(filepath, progress):
        ...     print(f"{filepath.name}: {progress['stage']} - {progress['progress_percent']:.1f}%")
        >>> success, output, msg = convert_file(Path("movie.mkv"), progress_callback=on_progress)
    """
    if cfg is None:
        cfg = CFG

    if backend is None:
        backend = pick_backend(cfg)

    if output_dir is None:
        output_dir = input_path.parent

    def _call_callback(stage: str, **kwargs: Any) -> None:
        """Helper to safely call the progress callback."""
        if progress_callback is not None:
            try:
                progress_dict = _make_progress_dict(stage, **kwargs)
                progress_callback(input_path, progress_dict)
            except Exception:
                pass  # Don't let callback errors affect conversion

    # Signal checking stage
    _call_callback("checking", progress_percent=0.0)

    # Analyze file
    try:
        decision = decide_for(input_path, cfg)
    except Exception as e:
        _call_callback("failed", error=f"Analysis failed: {e}")
        return False, None, f"Analysis failed: {e}"

    # Check if already compatible
    if (not decision.need_v) and (not decision.need_a) and cfg.skip_when_ok:
        _call_callback("skipped", progress_percent=100.0)
        return True, None, "Already compatible"

    # Build output path
    tag = get_output_tag(decision)
    output_path = output_dir / f"{input_path.stem}{tag}{cfg.suffix}.{cfg.container}"

    if output_path.exists():
        _call_callback("skipped", progress_percent=100.0)
        return True, output_path, "Output already exists"

    input_size = file_size(input_path)
    space_error = check_disk_space(output_dir, output_dir, input_size, cfg)
    if space_error:
        _call_callback("failed", error=space_error)
        return False, None, space_error

    # Create temp path
    tmp_path = output_dir / f"{input_path.stem}{tag}{cfg.suffix}.tmp.{os.getpid()}.{cfg.container}"

    if cfg.dryrun:
        cmd, _stage = build_transcode_cmd(input_path, decision, backend, tmp_path, log_path, cfg)
        _call_callback("skipped", progress_percent=100.0)
        return True, None, f"DRYRUN: {shlex.join(cmd)}"

    # Get duration for progress calculation
    dur_ms = probe_duration_ms(input_path)

    # Signal encoding start
    _call_callback("encoding", progress_percent=0.0, duration_ms=dur_ms)

    last_error = ""
    attempts = max(0, cfg.retry_attempts)
    total_attempts = 1 + attempts
    attempt_backend = backend

    for attempt in range(total_attempts):
        if attempt > 0:
            _call_callback("retry", error=last_error)
            if cfg.retry_delay_sec > 0:
                time.sleep(cfg.retry_delay_sec)

        cmd, stage = build_transcode_cmd(input_path, decision, attempt_backend, tmp_path, log_path, cfg)

        # Run ffmpeg with progress parsing if callback is provided
        if progress_callback is not None:
            success, out_path, message = _run_ffmpeg_with_callback(
                cmd, tmp_path, output_path, stage, dur_ms, input_path, progress_callback
            )
        else:
            # Original behavior without callback
            try:
                result = subprocess.run(cmd, capture_output=True, timeout=86400)  # 24h timeout

                if result.returncode == 0:
                    # Move temp to final
                    shutil.move(str(tmp_path), str(output_path))
                    success = True
                    out_path = output_path
                    message = f"{stage} complete"
                else:
                    # Clean up temp file
                    if tmp_path.exists():
                        tmp_path.unlink()
                    success = False
                    out_path = None
                    message = f"ffmpeg error (rc={result.returncode})"

            except subprocess.TimeoutExpired:
                if tmp_path.exists():
                    tmp_path.unlink()
                success = False
                out_path = None
                message = "Timeout exceeded"

            except Exception as e:
                if tmp_path.exists():
                    tmp_path.unlink()
                success = False
                out_path = None
                message = f"Error: {e}"

        if success and out_path:
            quota_error = enforce_output_quota(out_path, input_size, cfg)
            if quota_error:
                try:
                    out_path.unlink()
                except Exception:
                    pass
                _call_callback("failed", error=quota_error)
                return False, None, quota_error
            return True, out_path, message

        last_error = message

        if attempt < total_attempts - 1:
            if cfg.retry_fallback_cpu and attempt_backend != "cpu" and attempt == total_attempts - 2:
                attempt_backend = "cpu"
            continue

    return False, None, last_error


def _run_ffmpeg_with_callback(
    cmd: List[str],
    tmp_path: Path,
    output_path: Path,
    stage: str,
    dur_ms: int,
    input_path: Path,
    progress_callback: ProgressCallback,
) -> Tuple[bool, Optional[Path], str]:
    """
    Run FFmpeg command while parsing progress and calling callback.

    Args:
        cmd: FFmpeg command to run.
        tmp_path: Temporary output path.
        output_path: Final output path.
        stage: Stage name (e.g., "TRANSCODE").
        dur_ms: Duration in milliseconds.
        input_path: Input file path.
        progress_callback: Callback function for progress updates.

    Returns:
        Tuple of (success, output_path, message).
    """
    start_time = time.time()

    try:
        # Start process with stderr pipe for progress
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
        )

        # Read stderr for progress updates
        last_progress = 0.0

        while True:
            if process.stderr is None:
                break
            line = process.stderr.readline()
            if not line:
                break

            line_str = line.decode("utf-8", errors="replace")

            # Parse progress from FFmpeg output
            progress_data = parse_ffmpeg_progress(line_str, dur_ms)

            # Only call callback if progress changed significantly
            if progress_data["progress_percent"] > last_progress + 0.5 or progress_data["fps"] > 0:
                last_progress = progress_data["progress_percent"]

                # Calculate ETA
                eta = calculate_eta(progress_data["current_time_ms"], dur_ms, progress_data["speed"], start_time)

                try:
                    progress_dict = _make_progress_dict(
                        stage="encoding",
                        progress_percent=progress_data["progress_percent"],
                        fps=progress_data["fps"],
                        eta_seconds=eta,
                        bitrate=progress_data["bitrate"],
                        speed=progress_data["speed"],
                        current_time_ms=progress_data["current_time_ms"],
                        duration_ms=dur_ms,
                    )
                    progress_callback(input_path, progress_dict)
                except Exception:
                    pass

        # Wait for process to complete
        process.wait()

        if process.returncode == 0:
            # Move temp to final
            shutil.move(str(tmp_path), str(output_path))

            # Signal done
            try:
                progress_dict = _make_progress_dict(
                    stage="done",
                    progress_percent=100.0,
                    duration_ms=dur_ms,
                )
                progress_callback(input_path, progress_dict)
            except Exception:
                pass

            return True, output_path, f"{stage} complete"
        else:
            # Clean up temp file
            if tmp_path.exists():
                tmp_path.unlink()

            error_msg = f"ffmpeg error (rc={process.returncode})"
            try:
                progress_dict = _make_progress_dict(
                    stage="failed",
                    error=error_msg,
                )
                progress_callback(input_path, progress_dict)
            except Exception:
                pass

            return False, None, error_msg

    except subprocess.TimeoutExpired:
        if tmp_path.exists():
            tmp_path.unlink()
        error_msg = "Timeout exceeded"
        try:
            progress_dict = _make_progress_dict(stage="failed", error=error_msg)
            progress_callback(input_path, progress_dict)
        except Exception:
            pass
        return False, None, error_msg

    except Exception as e:
        if tmp_path.exists():
            tmp_path.unlink()
        error_msg = f"Error: {e}"
        try:
            progress_dict = _make_progress_dict(stage="failed", error=error_msg)
            progress_callback(input_path, progress_dict)
        except Exception:
            pass
        return False, None, error_msg


def convert_batch(
    input_paths: List[Path],
    cfg: Optional[Config] = None,
    progress_callback: Optional[ProgressCallback] = None,
    output_dir: Optional[Path] = None,
    backend: Optional[str] = None,
) -> Dict[Path, Tuple[bool, Optional[Path], str]]:
    """
    Convert multiple files in parallel using multi-threading.

    This function processes multiple files concurrently, respecting the
    configured number of workers. Each file's progress is reported via
    the optional callback.

    Args:
        input_paths: List of input file paths to convert.
        cfg: Config instance (uses global CFG if not provided).
            The number of parallel workers is determined by cfg.encode_workers.
        progress_callback: Optional callback function called with progress updates.
            The callback receives (filepath, progress_dict) for each file.
            The callback should be thread-safe if processing multiple files.
        output_dir: Output directory for all files (same as input if not provided).
        backend: Backend to use (auto-detected if not provided).

    Returns:
        Dict mapping input_path -> (success, output_path, message).

    Example:
        >>> from mkv2cast import convert_batch, Config
        >>> from pathlib import Path
        >>>
        >>> config = Config.for_library(hw="vaapi", encode_workers=2)
        >>>
        >>> def on_progress(filepath, progress):
        ...     print(f"{filepath.name}: {progress['progress_percent']:.1f}%")
        >>>
        >>> files = [Path("movie1.mkv"), Path("movie2.mkv")]
        >>> results = convert_batch(files, cfg=config, progress_callback=on_progress)
        >>>
        >>> for filepath, (success, output, msg) in results.items():
        ...     print(f"{filepath.name}: {'OK' if success else 'FAIL'} - {msg}")
    """
    if cfg is None:
        cfg = CFG

    if backend is None:
        backend = pick_backend(cfg)

    # Determine number of workers
    max_workers = cfg.encode_workers if cfg.encode_workers > 0 else 1

    # Thread-safe results dict
    results: Dict[Path, Tuple[bool, Optional[Path], str]] = {}
    results_lock = threading.Lock()

    # Thread-safe callback wrapper
    callback_lock = threading.Lock()

    def thread_safe_callback(filepath: Path, progress: Dict[str, Any]) -> None:
        """Thread-safe wrapper for the progress callback."""
        if progress_callback is not None:
            with callback_lock:
                try:
                    progress_callback(filepath, progress)
                except Exception:
                    pass

    def process_file(input_path: Path) -> Tuple[Path, Tuple[bool, Optional[Path], str]]:
        """Process a single file and return the result."""
        out_dir = output_dir if output_dir is not None else input_path.parent

        result = convert_file(
            input_path,
            cfg=cfg,
            backend=backend,
            output_dir=out_dir,
            progress_callback=thread_safe_callback if progress_callback else None,
        )

        return input_path, result

    # Process files in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        futures = {executor.submit(process_file, path): path for path in input_paths}

        # Collect results as they complete
        for future in as_completed(futures):
            input_path = futures[future]
            try:
                path, result = future.result()
                with results_lock:
                    results[path] = result
            except Exception as e:
                # Handle unexpected errors
                with results_lock:
                    results[input_path] = (False, None, f"Error: {e}")

                # Signal failure via callback
                if progress_callback:
                    thread_safe_callback(input_path, _make_progress_dict(stage="failed", error=str(e)))

    return results
