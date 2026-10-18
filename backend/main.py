"""
main.py — FastAPI Application Entrypoint for AI Video Smoother.

Implements all required REST API endpoints:
- GET  /api/health               — System and FFmpeg availability check
- POST /api/upload               — Validate, upload, and inspect video metadata
- GET  /api/video/{video_id}     — Retrieve metadata and processing history
- POST /api/process/{video_id}   — Start background enhancement job with settings
- GET  /api/jobs/{job_id}        — Poll job progress, messages, and results
- POST /api/jobs/{job_id}/cancel — Cancel an in-progress job
- GET  /api/download/{video_id}  — Download processed MP4 output
- GET  /api/preview/original/{video_id}  — Stream source video for side-by-side preview
- GET  /api/preview/processed/{video_id} — Stream enhanced video for side-by-side preview
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from config import (
    ALLOWED_EXTENSIONS,
    ALLOWED_OUTPUT_FPS,
    APP_NAME,
    APP_VERSION,
    CAPABILITIES,
    DEFAULT_QUALITY,
    DEFAULT_STRENGTH,
    FRONTEND_DIST_DIR,
    MAX_STRENGTH,
    MAX_UPLOAD_BYTES,
    MAX_UPLOAD_MB,
    MIN_STRENGTH,
    OUTPUTS_DIR,
    QUALITY_PROFILES,
    UPLOADS_DIR,
    get_ffmpeg_path,
)
from human_processor import process_human_video
from interpolator import get_interpolator_status
from job_manager import Job, create_job, get_job, submit_job
from screen_processor import process_screen_video
from stabilizer import get_stabilizer_info
from video_analyzer import VideoAnalysisError, analyze_video

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai_video_smoother")

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="Local, CPU-friendly AI-assisted video motion enhancement and stabilization.",
)

# Enable CORS for frontend Vite dev server (e.g. localhost:5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory registry for uploaded videos and their metadata
_videos: dict[str, dict[str, Any]] = {}


def _validate_hex_id(identifier: str, name: str = "ID") -> str:
    """Ensure identifier is a safe 32-character hexadecimal string."""
    clean = str(identifier).strip().lower()
    if not clean.isalnum() or len(clean) != 32:
        raise HTTPException(status_code=400, detail=f"Invalid {name} format.")
    return clean


# ── Health Endpoint ────────────────────────────────────────────────────────────

@app.get("/api/health")
def health() -> dict[str, Any]:
    """Check application health and verify FFmpeg binary availability."""
    ffmpeg_ok = False
    ffmpeg_path_found = None
    try:
        ffmpeg_path_found = get_ffmpeg_path()
        ffmpeg_ok = True
    except Exception as exc:
        logger.warning("FFmpeg check failed: %s", exc)

    return {
        "status": "healthy" if ffmpeg_ok else "degraded",
        "app_name": APP_NAME,
        "app_version": APP_VERSION,
        "ffmpeg_available": ffmpeg_ok,
        "ffmpeg_path": ffmpeg_path_found,
        "capabilities": CAPABILITIES,
        "stabilizer_info": get_stabilizer_info(),
        "interpolator_info": get_interpolator_status(),
    }


# ── Upload Endpoint ────────────────────────────────────────────────────────────

@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...)) -> dict[str, Any]:
    """
    Stage 1 & 2: Accept video upload, validate extension and size limit,
    save to local disk, and perform full metadata inspection.
    """
    orig_name = file.filename or "video.mp4"
    ext = Path(orig_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    video_id = uuid.uuid4().hex
    saved_path = UPLOADS_DIR / f"{video_id}{ext}"

    total_bytes = 0
    try:
        with saved_path.open("wb") as buffer:
            while True:
                chunk = await file.read(1024 * 1024)  # 1 MB chunk
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_BYTES:
                    saved_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"Video exceeds the {MAX_UPLOAD_MB} MB upload limit.",
                    )
                buffer.write(chunk)
    finally:
        await file.close()

    # Stage 2: Analyze metadata
    try:
        metadata = analyze_video(saved_path)
    except VideoAnalysisError as err:
        saved_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=f"Video validation failed: {err}")
    except Exception as exc:
        saved_path.unlink(missing_ok=True)
        logger.error("Unexpected error analyzing video %s: %s", video_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="An error occurred while analyzing the video.")

    video_record = {
        "video_id": video_id,
        "original_filename": orig_name,
        "extension": ext,
        "file_path": str(saved_path),
        "metadata": metadata,
        "latest_job_id": None,
        "processed": False,
    }
    _videos[video_id] = video_record

    return {
        "video_id": video_id,
        "filename": orig_name,
        "metadata": metadata,
        "message": "Video uploaded and analyzed successfully.",
    }


# ── Video Info Endpoint ────────────────────────────────────────────────────────

@app.get("/api/video/{video_id}")
def get_video_info(video_id: str) -> dict[str, Any]:
    """Retrieve metadata and current status for an uploaded video."""
    v_id = _validate_hex_id(video_id, "video_id")
    record = _videos.get(v_id)
    if not record:
        raise HTTPException(status_code=404, detail="Video record not found.")

    output_path = OUTPUTS_DIR / f"{v_id}_enhanced.mp4"
    processed_exists = output_path.exists()

    return {
        "video_id": v_id,
        "filename": record["original_filename"],
        "metadata": record["metadata"],
        "is_processed": processed_exists,
        "latest_job_id": record.get("latest_job_id"),
        "download_url": f"/api/download/{v_id}" if processed_exists else None,
    }


# ── Process Endpoint ───────────────────────────────────────────────────────────

@app.post("/api/process/{video_id}")
def start_processing(
    video_id: str,
    mode: str = Form("human"),
    strength: int = Form(DEFAULT_STRENGTH),
    output_fps: str = Form("original"),
    quality: str = Form(DEFAULT_QUALITY),
) -> dict[str, Any]:
    """
    Stage 3 & 4: Initiate background video enhancement with selected parameters.
    Returns immediately with a job_id for client-side progress polling.
    """
    v_id = _validate_hex_id(video_id, "video_id")
    record = _videos.get(v_id)
    if not record:
        raise HTTPException(status_code=404, detail="Video not found. Please upload it first.")

    input_path = Path(record["file_path"])
    if not input_path.exists():
        raise HTTPException(status_code=404, detail="Source video file is missing on server.")

    # Validation
    if mode not in {"screen", "human"}:
        raise HTTPException(status_code=400, detail="Mode must be either 'screen' or 'human'.")
    if not (MIN_STRENGTH <= strength <= MAX_STRENGTH):
        raise HTTPException(
            status_code=400,
            detail=f"Strength must be an integer between {MIN_STRENGTH} and {MAX_STRENGTH}.",
        )
    if output_fps not in ALLOWED_OUTPUT_FPS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid output FPS. Allowed: {', '.join(sorted(ALLOWED_OUTPUT_FPS))}.",
        )
    if quality not in QUALITY_PROFILES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid quality. Allowed: {', '.join(sorted(QUALITY_PROFILES.keys()))}.",
        )

    output_path = OUTPUTS_DIR / f"{v_id}_enhanced.mp4"
    meta = record.get("metadata", {})
    source_fps = float(meta.get("fps", 0.0))
    duration_sec = float(meta.get("duration_seconds", 0.0))
    has_audio = bool(meta.get("has_audio", False))

    job = create_job(description=f"{mode.capitalize()} video enhancement", video_id=v_id)
    record["latest_job_id"] = job.job_id

    def _execute(job_handle: Job):
        if mode == "screen":
            result = process_screen_video(
                input_path=input_path,
                output_path=output_path,
                strength=strength,
                output_fps=output_fps,
                source_fps=source_fps,
                duration_seconds=duration_sec,
                has_audio=has_audio,
                quality=quality,
                job=job_handle,
            )
        else:
            result = process_human_video(
                input_path=input_path,
                output_path=output_path,
                strength=strength,
                output_fps=output_fps,
                source_fps=source_fps,
                duration_seconds=duration_sec,
                has_audio=has_audio,
                quality=quality,
                job=job_handle,
            )

        record["processed"] = True
        job_handle.set_done(
            result={
                "video_id": v_id,
                "download_url": f"/api/download/{v_id}",
                "preview_url": f"/api/preview/processed/{v_id}",
                **result,
            },
            message="Video enhancement completed successfully.",
        )

    submit_job(job, _execute)

    return {
        "job_id": job.job_id,
        "video_id": v_id,
        "status": "queued",
        "message": "Processing started in background.",
    }


# ── Job Status & Cancellation Endpoints ────────────────────────────────────────

@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str) -> dict[str, Any]:
    """Retrieve progress percentage, status, and result payload for a job."""
    j_id = _validate_hex_id(job_id, "job_id")
    job = get_job(j_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job.to_dict()


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict[str, Any]:
    """Cancel a running or queued job."""
    j_id = _validate_hex_id(job_id, "job_id")
    job = get_job(j_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    job.cancel()
    return {"message": "Job cancellation requested.", "job_id": j_id}


# ── Video Streaming Preview Endpoints ──────────────────────────────────────────

@app.get("/api/preview/original/{video_id}")
def preview_original_video(video_id: str):
    """Stream the uploaded original video for in-browser playback."""
    v_id = _validate_hex_id(video_id, "video_id")
    record = _videos.get(v_id)
    if not record:
        raise HTTPException(status_code=404, detail="Video record not found.")

    path = Path(record["file_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Original video file not found.")

    ext = record.get("extension", ".mp4")
    media_type = f"video/{ext.lstrip('.')}" if ext != ".mkv" else "video/mp4"
    return FileResponse(path, media_type=media_type)


@app.get("/api/preview/processed/{video_id}")
def preview_processed_video(video_id: str):
    """Stream the enhanced MP4 video for in-browser comparison playback."""
    v_id = _validate_hex_id(video_id, "video_id")
    path = OUTPUTS_DIR / f"{v_id}_enhanced.mp4"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Enhanced video not ready or does not exist.")
    return FileResponse(path, media_type="video/mp4")


# ── Download Endpoint ──────────────────────────────────────────────────────────

@app.get("/api/download/{video_id}")
def download_processed_video(video_id: str):
    """Download the enhanced MP4 file."""
    v_id = _validate_hex_id(video_id, "video_id")
    path = OUTPUTS_DIR / f"{v_id}_enhanced.mp4"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Enhanced video output not found.")

    record = _videos.get(v_id)
    stem = Path(record["original_filename"]).stem if record else "enhanced_video"
    download_filename = f"{stem}_smoothed.mp4"

    return FileResponse(
        path,
        media_type="video/mp4",
        filename=download_filename,
    )


# ── Serve Built Frontend if present ───────────────────────────────────────────
if FRONTEND_DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST_DIR, html=True), name="frontend-dist")
