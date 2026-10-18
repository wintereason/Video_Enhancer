"""
video_exporter.py — Stage 5 & 6: Re-encode, remux, and validate output video.

Uses FFmpeg with streaming-friendly flags (+faststart) and standard YUV420p pixel format
for universal browser decodability.
Parses FFmpeg's progress output to report granular percentages to background jobs.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from config import (
    DEFAULT_AUDIO_BITRATE,
    DEFAULT_AUDIO_CODEC,
    DEFAULT_VIDEO_CODEC,
    QUALITY_PROFILES,
    get_ffmpeg_path,
)
from motion_smoother import SmoothingPlan


class ExportError(Exception):
    """Raised when video export or re-encoding fails."""


def export_video(
    input_path: Path,
    output_path: Path,
    plan: SmoothingPlan,
    duration_seconds: float = 0.0,
    job: Any = None,
    quality: str = "balanced",
    has_audio: bool = True,
) -> dict[str, Any]:
    """
    Re-encode *input_path* with *plan.filters* and output to *output_path*.
    Reports progress to *job* if provided.
    """
    if not input_path.exists():
        raise ExportError(f"Input video file missing: {input_path}")

    ffmpeg = get_ffmpeg_path()
    vf_str = plan.vf_string()

    profile = QUALITY_PROFILES.get(quality, QUALITY_PROFILES["balanced"])
    crf = profile["crf"]
    preset = profile["preset"]

    cmd: list[str] = [
        ffmpeg, "-y",
        "-i", str(input_path),
        "-map", "0:v:0",
    ]

    if has_audio:
        cmd += ["-map", "0:a?"]

    cmd += [
        "-vf", vf_str,
        "-c:v", DEFAULT_VIDEO_CODEC,
        "-preset", preset,
        "-crf", str(crf),
        "-pix_fmt", "yuv420p",
    ]

    if has_audio:
        cmd += [
            "-c:a", DEFAULT_AUDIO_CODEC,
            "-b:a", DEFAULT_AUDIO_BITRATE,
            "-async", "1",
        ]

    cmd += [
        "-movflags", "+faststart",
        str(output_path),
    ]

    if job:
        job.set_progress(25, "Encoding enhanced video with FFmpeg...")

    try:
        # Run process and monitor output
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        # Parse stderr for progress updates
        stderr_accumulator = []
        if proc.stderr:
            time_regex = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")
            for line in proc.stderr:
                stderr_accumulator.append(line)
                if job and duration_seconds > 0:
                    match = time_regex.search(line)
                    if match:
                        h, m, s = match.groups()
                        curr_sec = int(h) * 3600 + int(m) * 60 + float(s)
                        pct = int(25 + (curr_sec / duration_seconds) * 65)
                        pct = max(25, min(92, pct))
                        job.set_progress(pct, f"Processing frames: {pct}% complete")

        proc.wait(timeout=3600)
    except subprocess.TimeoutExpired:
        if proc:
            proc.kill()
        raise ExportError("FFmpeg encoding timed out after 60 minutes.")
    except Exception as exc:
        raise ExportError(f"Failed to execute FFmpeg process: {exc}")
    finally:
        if proc:
            if proc.stdout:
                proc.stdout.close()
            if proc.stderr:
                proc.stderr.close()

    if proc.returncode != 0:
        err_snippet = "".join(stderr_accumulator[-40:])
        raise ExportError(f"FFmpeg encoding failed (exit code {proc.returncode}):\n{err_snippet}")

    if job:
        job.set_progress(95, "Validating output decodability...")

    # Stage 6: Output decodability validation
    validation = validate_video_output(output_path, ffmpeg)
    if not validation["ok"]:
        raise ExportError(f"Output verification failed: {validation['message']}")

    if job:
        job.set_progress(100, "Processing complete!")

    file_size_bytes = output_path.stat().st_size
    return {
        "output_path": str(output_path),
        "file_size_bytes": file_size_bytes,
        "file_size_mb": round(file_size_bytes / (1024 * 1024), 2),
        "vf_filters": vf_str,
        "quality_profile": profile["label"],
        "validation": validation,
    }


def validate_video_output(output_path: Path, ffmpeg_exe: str) -> dict[str, Any]:
    """
    Stage 6 Quality validation: Verify that the output exists, is non-empty,
    and can be decoded cleanly by FFmpeg without fatal stream errors.
    """
    if not output_path.exists():
        return {"ok": False, "message": "Output file does not exist on disk."}

    size = output_path.stat().st_size
    if size < 512:
        return {"ok": False, "message": f"Output file is abnormally small ({size} bytes)."}

    cmd = [
        ffmpeg_exe,
        "-v", "error",
        "-i", str(output_path),
        "-t", "3",
        "-f", "null", "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            return {
                "ok": False,
                "message": f"FFmpeg validation decode test failed: {proc.stderr[:300]}",
            }
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": "Output validation decode timed out."}
    except Exception as exc:
        return {"ok": False, "message": f"Output validation failed: {exc}"}

    return {"ok": True, "message": "Video successfully validated and playable."}
