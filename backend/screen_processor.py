"""
screen_processor.py — Mode A: Screen Recording Enhancement.

Preserves pixel sharpness, text readability, and UI geometry.
Never applies aggressive geometric warping or blur.
Prepares architecture for cursor tracking and path smoothing in Milestone 6.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from motion_smoother import build_screen_plan
from video_exporter import export_video


def process_screen_video(
    input_path: Path,
    output_path: Path,
    strength: int,
    output_fps: str,
    source_fps: float,
    duration_seconds: float,
    has_audio: bool,
    quality: str = "balanced",
    job: Any = None,
) -> dict[str, Any]:
    """
    Process a desktop or application screen recording:
    - Protects text clarity and UI structure
    - Resamples FPS if selected
    - Ensures standard H.264/AAC MP4 output
    """
    if job:
        job.set_progress(10, "Building text-safe screen processing plan...")

    plan = build_screen_plan(
        strength=strength,
        output_fps=output_fps,
        source_fps=source_fps,
        quality=quality,
    )

    plan.notes.append(
        "Cursor tracking & background inpainting: Scheduled for Milestone 6. "
        "Original cursor remains untouched to prevent drift."
    )

    if job:
        job.set_progress(20, "Initiating video re-encoding...")

    export_result = export_video(
        input_path=input_path,
        output_path=output_path,
        plan=plan,
        duration_seconds=duration_seconds,
        job=job,
        quality=quality,
        has_audio=has_audio,
    )

    return {
        "mode": "screen",
        "plan": plan.to_dict(),
        **export_result,
    }
