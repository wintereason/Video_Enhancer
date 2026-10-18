"""
human_processor.py — Mode B: Human & Camera Video Enhancement.

Applies motion compensation to reduce camera jitter while preserving facial expressions
and body movements.
Prepares architecture for RIFE AI frame interpolation in Milestone 4 and MediaPipe pose in Milestone 7.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from motion_smoother import build_human_plan
from video_exporter import export_video


def process_human_video(
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
    Process human or camera recorded video:
    - Camera shake reduction via FFmpeg deshake (if strength >= 15%)
    - Frame rate conversion if selected
    - Universal H.264/AAC output
    """
    if job:
        job.set_progress(10, "Building human motion stabilization plan...")

    plan = build_human_plan(
        strength=strength,
        output_fps=output_fps,
        source_fps=source_fps,
        has_audio=has_audio,
        quality=quality,
    )

    plan.notes.append(
        "AI Frame Interpolation (RIFE): Scheduled for Milestone 4. "
        "Selected FPS conversion uses conventional frame resampling."
    )
    plan.notes.append(
        "Semantic Human Pose Tracking: Scheduled for Milestone 7."
    )

    if job:
        job.set_progress(20, "Initiating video stabilization and encoding...")

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
        "mode": "human",
        "plan": plan.to_dict(),
        **export_result,
    }
