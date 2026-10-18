"""
config.py — Central configuration and environment settings for AI Video Smoother.
All tuneable parameters, path definitions, and system binary locators live here.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

# ── Root and Data Paths ────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = BACKEND_DIR.parent
UPLOADS_DIR = ROOT_DIR / "uploads"
OUTPUTS_DIR = ROOT_DIR / "outputs"
TEMP_DIR = ROOT_DIR / "temp"
FRONTEND_DIR = ROOT_DIR / "frontend"
FRONTEND_DIST_DIR = FRONTEND_DIR / "dist"

for _dir in (UPLOADS_DIR, OUTPUTS_DIR, TEMP_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

# ── Upload Limits ─────────────────────────────────────────────────────────────
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "500"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}

# ── Processing Constraints ────────────────────────────────────────────────────
MAX_VIDEO_DURATION_SECONDS = int(os.getenv("MAX_DURATION_SEC", "3600"))  # 1 hour
JOB_TIMEOUT_SECONDS = int(os.getenv("JOB_TIMEOUT_SEC", "3600"))

# ── Export Defaults & Quality Profiles ────────────────────────────────────────
DEFAULT_VIDEO_CODEC = "libx264"
DEFAULT_AUDIO_CODEC = "aac"
DEFAULT_AUDIO_BITRATE = "192k"

# CRF profiles (lower = better quality / larger file)
QUALITY_PROFILES = {
    "high": {"crf": 18, "preset": "veryfast", "label": "High Quality (CRF 18)"},
    "balanced": {"crf": 22, "preset": "veryfast", "label": "Balanced (CRF 22)"},
    "fast": {"crf": 26, "preset": "ultrafast", "label": "Fast / Compressed (CRF 26)"},
}
DEFAULT_QUALITY = "balanced"

# Allowed target frame rates
ALLOWED_OUTPUT_FPS = {"original", "24", "30", "60", "120"}

# Processing strength range
MIN_STRENGTH = 0
MAX_STRENGTH = 100
DEFAULT_STRENGTH = 50

# ── Version and Capability Flags ──────────────────────────────────────────────
APP_NAME = "AI Video Smoother"
APP_VERSION = "1.0.0-milestone1"

# Feature flags indicating what is actually active at this milestone
CAPABILITIES = {
    "conventional_shake_reduction": True,   # FFmpeg deshake
    "conventional_fps_resampling": True,    # FFmpeg fps filter
    "ai_frame_interpolation": False,       # Pretrained RIFE in Milestone 4
    "cursor_tracking_smoothing": False,     # Screen cursor in Milestone 6
    "human_pose_analysis": False,           # MediaPipe pose in Milestone 7
    "gpu_acceleration": False,              # Windows CPU-only MVP
}


def get_ffmpeg_path() -> str:
    """
    Locate the FFmpeg binary.
    Prioritises imageio-ffmpeg bundled binary so it works without system install.
    """
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).exists():
            return exe
    except Exception:
        pass

    sys_exe = shutil.which("ffmpeg")
    if sys_exe:
        return sys_exe

    raise RuntimeError(
        "FFmpeg executable not found. Ensure imageio-ffmpeg is installed or ffmpeg is on PATH."
    )


def get_ffprobe_path() -> str | None:
    """Return path to ffprobe binary if available in PATH or imageio directory."""
    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        cand = Path(ffmpeg_exe).parent / "ffprobe.exe"
        if cand.exists():
            return str(cand)
    except Exception:
        pass
    return shutil.which("ffprobe")
