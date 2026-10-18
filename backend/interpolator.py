"""
interpolator.py — Pretrained AI Frame Interpolation interface and model manager.

Provides the architecture for AI-assisted frame interpolation (RIFE).
In Milestone 1, it explicitly reports model availability, hardware constraints,
and CPU feasibility warnings, cleanly separating conventional FFmpeg fps resampling
from neural intermediate frame synthesis.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class InterpolatorError(Exception):
    """Raised when frame interpolation fails or is requested when unsupported."""


class AIInterpolator:
    """
    Interface for AI Frame Interpolation.
    Designed for pretrained RIFE (Real-Time Intermediate Flow Estimation) integration.
    """

    def __init__(self, model_name: str = "rife-v4.6", device: str = "cpu"):
        self.model_name = model_name
        self.device = device
        self.model_loaded = False
        self.supported_devices = ["cpu", "cuda"]

    def is_available(self) -> bool:
        """
        Check if AI frame interpolation model weights and runtime are loaded.
        Returns False in Milestone 1 CPU-only MVP.
        """
        return self.model_loaded

    def get_status(self) -> dict[str, Any]:
        """
        Return the operational status of the neural interpolation engine.
        Ensures the application never misleads the user regarding AI processing.
        """
        return {
            "model_name": self.model_name,
            "is_available": self.model_loaded,
            "device": self.device,
            "milestone": "Planned for Milestone 4 (Pretrained RIFE)",
            "cpu_limitation_warning": (
                "Neural frame interpolation on CPU requires substantial compute "
                "(approx. 2-5 seconds per frame). GPU acceleration will be optional in M4."
            ),
            "conventional_fallback": "Conventional frame-rate resampling (FFmpeg 'fps' filter) is currently used.",
        }

    def interpolate_video(
        self,
        input_path: Path,
        output_path: Path,
        target_fps: int,
        source_fps: float,
        job: Any = None,
    ) -> dict[str, Any]:
        """
        Synthesize intermediate frames using deep optical flow / neural model.
        """
        if not self.model_loaded:
            raise InterpolatorError(
                "Neural AI frame interpolation is scheduled for Milestone 4. "
                "For Milestone 1, select 30 or 60 FPS in the UI for conventional video resampling."
            )
        raise NotImplementedError("RIFE model weights not initialized.")


# Global singleton instance
_interpolator_instance = AIInterpolator()


def get_interpolator_status() -> dict[str, Any]:
    return _interpolator_instance.get_status()


def is_ai_interpolation_active() -> bool:
    return _interpolator_instance.is_available()
