"""
motion_smoother.py — Stage 3/4: Enhancement Plan construction and filter coordination.

Builds explicit FFmpeg filter chains for both Screen Recording and Human Video modes.
Every applied or skipped operation is recorded with human-readable rationale so the
user interface can display complete transparency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from stabilizer import compute_stabilization_parameters


@dataclass
class SmoothingPlan:
    """
    Detailed plan describing which filters and transformations will be applied.
    Returned to the client for full transparency.
    """
    mode: str = "human"
    filters: list[str] = field(default_factory=list)
    applied_ops: list[str] = field(default_factory=list)
    skipped_ops: list[str] = field(default_factory=list)
    is_ai: bool = False
    notes: list[str] = field(default_factory=list)
    quality: str = "balanced"

    def vf_string(self) -> str:
        """Return the FFmpeg -vf filter graph string, or 'null' if none are applied."""
        return ",".join(self.filters) if self.filters else "null"

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "applied_ops": self.applied_ops,
            "skipped_ops": self.skipped_ops,
            "is_ai": self.is_ai,
            "notes": self.notes,
            "quality": self.quality,
            "vf_filters": self.vf_string(),
        }


def build_screen_plan(
    strength: int,
    output_fps: str,
    source_fps: float,
    quality: str = "balanced",
) -> SmoothingPlan:
    """
    Construct filter plan for Screen Recording mode.
    Guarantees:
    - Never warps or crops frames, ensuring text, code, and UI elements stay sharp.
    - Accurately converts FPS via resampling when requested.
    """
    plan = SmoothingPlan(mode="screen", quality=quality)

    # Frame rate conversion
    if output_fps != "original" and _fps_differs(output_fps, source_fps):
        plan.filters.append(f"fps={output_fps}")
        plan.applied_ops.append(
            f"Frame-rate conversion to {output_fps} FPS (conventional resampling; not AI interpolation)."
        )
    else:
        plan.skipped_ops.append(
            f"Frame-rate conversion skipped: target '{output_fps}' matches source ({source_fps:.1f} FPS)."
        )

    # Explain why deshake is deliberately skipped in screen mode
    plan.skipped_ops.append(
        "Geometric stabilization (deshake) deliberately disabled for screen recording: "
        "stabilization warps pixels and would blur or distort code editors and text."
    )

    plan.notes.append(
        "Screen Recording Mode: High-fidelity preservation of UI borders, crisp fonts, and code. "
        "No AI interpolation or cursor-path altering applied."
    )
    return plan


def build_human_plan(
    strength: int,
    output_fps: str,
    source_fps: float,
    has_audio: bool,
    quality: str = "balanced",
) -> SmoothingPlan:
    """
    Construct filter plan for Human Video mode.
    - Applies camera shake reduction via FFmpeg deshake if strength >= 15.
    - Resamples FPS if requested.
    - Maintains audio sync.
    """
    plan = SmoothingPlan(mode="human", quality=quality)

    # Stabilization
    stab = compute_stabilization_parameters(strength)
    if stab["enabled"]:
        plan.filters.append(stab["filter_string"])
        plan.applied_ops.append(
            f"Camera-shake reduction (FFmpeg 'deshake' filter, search radius = {stab['radius']}px, "
            f"blocksize = {stab['blocksize']}, mirror edge compensation)."
        )
    else:
        plan.skipped_ops.append(
            f"Stabilization skipped: {stab.get('reason', 'strength below threshold')}."
        )

    # Frame rate conversion
    if output_fps != "original" and _fps_differs(output_fps, source_fps):
        plan.filters.append(f"fps={output_fps}")
        plan.applied_ops.append(
            f"Frame-rate conversion to {output_fps} FPS (conventional resampling; not AI interpolation)."
        )
    else:
        plan.skipped_ops.append(
            f"Frame-rate conversion skipped: target '{output_fps}' matches source ({source_fps:.1f} FPS)."
        )

    if not has_audio:
        plan.notes.append("Source has no audio track; resulting MP4 will be silent.")

    plan.notes.append(
        "Human Video Mode: Uses conventional motion compensation. "
        "AI frame interpolation (RIFE) is scheduled for Milestone 4."
    )
    return plan


def _fps_differs(target_fps_str: str, source_fps: float) -> bool:
    try:
        target = float(target_fps_str)
    except ValueError:
        return False
    if source_fps <= 0:
        return True
    return abs(target - source_fps) > 0.5
