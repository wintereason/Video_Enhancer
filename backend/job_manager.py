"""
job_manager.py — In-memory background job coordinator and lifecycle tracker.

Allows long-running video processing tasks to run asynchronously without blocking
FastAPI request-response threads.
Provides job polling, progress reporting, cancellation flags, and result storage.
"""

from __future__ import annotations

import logging
import threading
import time
import traceback
import uuid
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Job:
    def __init__(self, job_id: str, description: str = "", video_id: str = ""):
        self.job_id = job_id
        self.description = description
        self.video_id = video_id
        self.status = JobStatus.QUEUED
        self.progress = 0            # 0 to 100
        self.message = "Job queued"
        self.error: str | None = None
        self.result: Any = None
        self.created_at = time.time()
        self.updated_at = time.time()
        self._cancel_event = threading.Event()
        self._lock = threading.Lock()

    def set_running(self, message: str = "Processing started...") -> None:
        with self._lock:
            self.status = JobStatus.RUNNING
            self.message = message
            self.updated_at = time.time()

    def set_progress(self, progress: int, message: str = "") -> None:
        with self._lock:
            self.progress = max(0, min(100, int(progress)))
            if message:
                self.message = message
            self.updated_at = time.time()

    def set_done(self, result: Any = None, message: str = "Completed successfully") -> None:
        with self._lock:
            self.status = JobStatus.DONE
            self.progress = 100
            self.message = message
            self.result = result
            self.updated_at = time.time()

    def set_failed(self, error_message: str) -> None:
        with self._lock:
            self.status = JobStatus.FAILED
            self.message = "Failed"
            self.error = error_message
            self.updated_at = time.time()

    def cancel(self) -> None:
        with self._lock:
            self._cancel_event.set()
            self.status = JobStatus.CANCELLED
            self.message = "Job cancelled by user"
            self.updated_at = time.time()

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "job_id": self.job_id,
                "video_id": self.video_id,
                "description": self.description,
                "status": self.status.value,
                "progress": self.progress,
                "message": self.message,
                "error": self.error,
                "result": self.result,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
            }


# ── Global In-Memory Registry ──────────────────────────────────────────────────
_jobs: dict[str, Job] = {}
_registry_lock = threading.Lock()


def create_job(description: str = "", video_id: str = "") -> Job:
    """Create and register a new Job instance."""
    job_id = uuid.uuid4().hex
    job = Job(job_id=job_id, description=description, video_id=video_id)
    with _registry_lock:
        _jobs[job_id] = job
    return job


def get_job(job_id: str) -> Job | None:
    """Retrieve an existing job by its hex ID."""
    with _registry_lock:
        return _jobs.get(job_id)


def submit_job(job: Job, target_fn: Callable[[Job], Any]) -> None:
    """Execute target_fn(job) inside a background daemon thread."""

    def _worker():
        job.set_running("Processing started...")
        try:
            target_fn(job)
        except Exception as exc:
            logger.error("Job %s encountered error: %s", job.job_id, exc, exc_info=True)
            job.set_failed(str(exc))

    t = threading.Thread(target=_worker, daemon=True, name=f"JobWorker-{job.job_id[:8]}")
    t.start()
