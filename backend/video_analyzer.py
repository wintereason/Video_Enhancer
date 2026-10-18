"""
video_analyzer.py — Stage 2: Inspect uploaded video and return structured metadata.

Uses ffprobe if available; otherwise falls back to OpenCV + FFmpeg stream parsing
so analysis works out of the box on Windows with zero external installations.
Also computes quick motion analysis by sampling frames across the video.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import cv2

from config import (
    MAX_VIDEO_DURATION_SECONDS,
    get_ffmpeg_path,
    get_ffprobe_path,
)


class VideoAnalysisError(Exception):
    """Raised when video inspection fails or file is corrupt."""


def analyze_video(video_path: Path) -> dict[str, Any]:
    """
    Inspect *video_path* and return comprehensive structured metadata:
    - filename, file_size_bytes
    - duration_seconds, width, height, fps, frame_count
    - video_codec, audio_codec, has_audio, bit_rate_kbps
    - motion_analysis: estimated motion intensity and stability hints
    - warnings: list of human-friendly notices
    """
    if not video_path.exists():
        raise VideoAnalysisError(f"Video file not found: {video_path}")

    file_size_bytes = video_path.stat().st_size
    if file_size_bytes == 0:
        raise VideoAnalysisError("Uploaded video file is empty (0 bytes).")

    # 1. Try ffprobe if available
    ffprobe_exe = get_ffprobe_path()
    meta: dict[str, Any] | None = None
    if ffprobe_exe:
        try:
            meta = _probe_with_ffprobe(video_path, ffprobe_exe)
        except Exception:
            meta = None

    # 2. Fall back to OpenCV + FFmpeg stream inspection
    if meta is None:
        meta = _probe_with_opencv_and_ffmpeg(video_path)

    # 3. Add file-level metrics
    meta["filename"] = video_path.name
    meta["file_size_bytes"] = file_size_bytes
    meta["file_size_mb"] = round(file_size_bytes / (1024 * 1024), 2)

    # 4. Perform light motion and scene stability sampling via OpenCV
    motion_info = _sample_motion_characteristics(video_path, meta.get("frame_count") or 0)
    meta["motion_analysis"] = motion_info

    # 5. Populate actionable validation warnings
    warnings: list[str] = meta.get("warnings", [])
    dur = meta.get("duration_seconds", 0.0)
    if dur <= 0:
        warnings.append("Duration could not be determined accurately; the video might have incomplete headers.")
    elif dur > MAX_VIDEO_DURATION_SECONDS:
        warnings.append(
            f"Duration ({dur:.1f}s) exceeds recommended limit ({MAX_VIDEO_DURATION_SECONDS}s). "
            "Processing may take a long time on CPU."
        )

    fps = meta.get("fps", 0.0)
    if fps <= 0:
        warnings.append("Frame rate could not be detected reliably.")
    elif fps < 15:
        warnings.append(f"Very low frame rate ({fps:.1f} FPS) detected.")

    if not meta.get("has_audio"):
        warnings.append("No audio track detected in source video.")

    if meta.get("width", 0) == 0 or meta.get("height", 0) == 0:
        raise VideoAnalysisError("Could not decode video stream dimensions. File may be unsupported or corrupted.")

    meta["warnings"] = warnings
    return meta


def _probe_with_ffprobe(video_path: Path, ffprobe_exe: str) -> dict[str, Any]:
    cmd = [
        ffprobe_exe,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(video_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        raise RuntimeError("ffprobe exited with error")

    probe = json.loads(proc.stdout)
    streams = probe.get("streams", [])
    fmt = probe.get("format", {})

    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not video_stream:
        raise VideoAnalysisError("No video stream found in container.")

    width = int(video_stream.get("width", 0))
    height = int(video_stream.get("height", 0))
    fps = _parse_fps(video_stream.get("r_frame_rate") or video_stream.get("avg_frame_rate", "0/1"))

    raw_dur = video_stream.get("duration") or fmt.get("duration", "0")
    try:
        duration_seconds = round(float(raw_dur), 2)
    except (ValueError, TypeError):
        duration_seconds = 0.0

    raw_nb_frames = video_stream.get("nb_frames")
    frame_count = int(raw_nb_frames) if raw_nb_frames and raw_nb_frames != "N/A" else None
    if frame_count is None and fps > 0 and duration_seconds > 0:
        frame_count = int(duration_seconds * fps)

    video_codec = video_stream.get("codec_name", "unknown")

    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    has_audio = audio_stream is not None
    audio_codec = audio_stream.get("codec_name") if audio_stream else None

    bit_rate_raw = fmt.get("bit_rate")
    try:
        bit_rate_kbps = int(int(bit_rate_raw) / 1000) if bit_rate_raw else None
    except (ValueError, TypeError):
        bit_rate_kbps = None

    return {
        "width": width,
        "height": height,
        "fps": round(fps, 2),
        "duration_seconds": duration_seconds,
        "frame_count": frame_count,
        "video_codec": video_codec,
        "audio_codec": audio_codec,
        "has_audio": has_audio,
        "bit_rate_kbps": bit_rate_kbps,
        "warnings": [],
    }


def _probe_with_opencv_and_ffmpeg(video_path: Path) -> dict[str, Any]:
    """Inspect video using OpenCV VideoCapture combined with FFmpeg stderr stream inspection."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise VideoAnalysisError("Cannot open video file with OpenCV. Format may be unsupported or corrupted.")

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cap.release()

    duration_seconds = round(frame_count / fps, 2) if (fps > 0 and frame_count > 0) else 0.0

    # Parse FFmpeg banner output to inspect codecs and audio tracks
    video_codec = "h264"
    audio_codec = None
    has_audio = False
    bit_rate_kbps = None

    try:
        ffmpeg_exe = get_ffmpeg_path()
        proc = subprocess.run(
            [ffmpeg_exe, "-hide_banner", "-i", str(video_path)],
            capture_output=True,
            text=True,
            timeout=20,
        )
        stderr = proc.stderr or ""

        # Parse duration if opencv duration was missing or 0
        if duration_seconds <= 0:
            dur_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", stderr)
            if dur_match:
                hours, minutes, seconds = dur_match.groups()
                duration_seconds = round(int(hours) * 3600 + int(minutes) * 60 + float(seconds), 2)
                if frame_count <= 0 and fps > 0:
                    frame_count = int(duration_seconds * fps)

        # Parse bitrate
        br_match = re.search(r"bitrate:\s*(\d+)\s*kb/s", stderr)
        if br_match:
            bit_rate_kbps = int(br_match.group(1))

        # Parse video codec
        v_match = re.search(r"Stream #\d+:\d+.*Video:\s*([a-zA-Z0-9_\-]+)", stderr)
        if v_match:
            video_codec = v_match.group(1)

        # Parse audio stream
        a_match = re.search(r"Stream #\d+:\d+.*Audio:\s*([a-zA-Z0-9_\-]+)", stderr)
        if a_match:
            has_audio = True
            audio_codec = a_match.group(1)
    except Exception:
        pass

    return {
        "width": width,
        "height": height,
        "fps": round(fps, 2),
        "duration_seconds": duration_seconds,
        "frame_count": frame_count if frame_count > 0 else None,
        "video_codec": video_codec,
        "audio_codec": audio_codec,
        "has_audio": has_audio,
        "bit_rate_kbps": bit_rate_kbps,
        "warnings": [],
    }


def _sample_motion_characteristics(video_path: Path, frame_count: int) -> dict[str, Any]:
    """
    Sample 5 frames across the video to assess motion intensity and camera jitter.
    Returns:
      {
        "motion_intensity": "low" | "medium" | "high",
        "avg_frame_delta": float,
        "recommendation": str
      }
    """
    if frame_count < 10:
        return {
            "motion_intensity": "low",
            "avg_frame_delta": 0.0,
            "recommendation": "Short clip. Standard processing recommended.",
        }

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return {
            "motion_intensity": "medium",
            "avg_frame_delta": 0.0,
            "recommendation": "Ready for smoothing.",
        }

    sample_indices = [
        int(frame_count * 0.1),
        int(frame_count * 0.3),
        int(frame_count * 0.5),
        int(frame_count * 0.7),
        int(frame_count * 0.9),
    ]

    deltas: list[float] = []
    prev_gray = None

    try:
        for idx in sample_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if not ret or frame is None:
                continue

            # Resize to small dimension for ultra-fast CPU comparison
            small = cv2.resize(frame, (160, 90))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

            if prev_gray is not None:
                diff = cv2.absdiff(prev_gray, gray)
                mean_diff = float(diff.mean())
                deltas.append(mean_diff)
            prev_gray = gray
    finally:
        cap.release()

    avg_delta = sum(deltas) / len(deltas) if deltas else 5.0

    if avg_delta < 3.0:
        intensity = "low"
        rec = "Static or subtle motion detected. Light stabilization or screen mode ideal."
    elif avg_delta < 12.0:
        intensity = "medium"
        rec = "Moderate motion detected. 40-60% stabilization strength recommended."
    else:
        intensity = "high"
        rec = "Dynamic camera motion or frequent screen transitions detected. Consider higher strength."

    return {
        "motion_intensity": intensity,
        "avg_frame_delta": round(avg_delta, 2),
        "recommendation": rec,
    }


def _parse_fps(fps_str: str) -> float:
    """Parse FPS strings like '30000/1001', '30/1', or '29.97'."""
    try:
        if "/" in str(fps_str):
            num, den = fps_str.split("/")
            den_int = int(den)
            return round(int(num) / den_int, 2) if den_int != 0 else 0.0
        return round(float(fps_str), 2)
    except (ValueError, ZeroDivisionError):
        return 0.0
