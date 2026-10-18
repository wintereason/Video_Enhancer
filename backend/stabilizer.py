"""
stabilizer.py — Motion stabilization engine and parameter calculator.

Handles camera shake reduction for Human / Camera footage.
Milestone 1: Computes valid, tested parameters for FFmpeg's 'deshake' motion compensation filter.
Milestone 3+: Prepares architecture for libvidstab two-pass stabilization.
Milestone 7+: Prepares architecture for pose-guided stabilization.
"""

from __future__ import annotations

from typing import Any


def get_stabilizer_info() -> dict[str, Any]:
    """Return capability and status flags for video stabilization."""
    return {
        "basic_deshake": True,          # Available in Milestone 1
        "vidstab_twopass": False,       # Milestone 3
        "pose_guided": False,           # Milestone 7
        "filter_name": "deshake",
        "description": "Motion compensation filter for camera shake reduction.",
    }


def compute_stabilization_parameters(strength: int) -> dict[str, Any]:
    """
    Map user strength (0-100) to valid FFmpeg deshake parameters.
    FFmpeg deshake AVOptions:
    - rx/ry: rectangular search radius (0 to 64, default 16)
    - edge: edge mode: mirror (3) to reflect border pixels
    - blocksize: motion search blocksize (4 to 128, default 8)
    - contrast: contrast threshold for blocks (1 to 255, default 125)
    - search: 0 for exhaustive search
    """
    clamped_strength = max(0, min(100, strength))
    if clamped_strength < 15:
        return {
            "enabled": False,
            "reason": f"Strength ({clamped_strength}%) is below the 15% activation threshold.",
        }

    # Normalized factor from 0.0 at 15% to 1.0 at 100%
    factor = (clamped_strength - 15) / 85.0
    if factor < 0.35:
        radius = 16
    elif factor < 0.70:
        radius = 32
    elif factor < 0.90:
        radius = 48
    else:
        radius = 64
    blocksize = 16 if factor < 0.5 else 32
    contrast = int(125 - factor * 40)     # slightly lower threshold for subtle motion

    filter_str = f"deshake=rx={radius}:ry={radius}:edge=mirror:blocksize={blocksize}:contrast={contrast}:search=0"

    return {
        "enabled": True,
        "radius": radius,
        "edge": "mirror",
        "blocksize": blocksize,
        "contrast": contrast,
        "filter_string": filter_str,
    }
