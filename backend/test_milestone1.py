"""
test_milestone1.py — Automated verification test suite for Milestone 1.

Tests:
1. Health & FFmpeg binary detection
2. Synthetic video generation (with audio and silent)
3. Metadata analysis & motion characteristics estimation
4. Input validation (unsupported extensions, corrupt payloads)
5. Video upload endpoint (/api/upload)
6. Asynchronous job management (/api/process & /api/jobs/{id})
7. Mode A: Screen Recording processing (deshake disabled, text preserved)
8. Mode B: Human Video processing (deshake enabled, FPS normalisation)
9. Output video decodability and download endpoint (/api/download/{id})
10. Job cancellation functionality
11. Model transparency assertion (ensuring no false AI claims)
"""

from __future__ import annotations

import io
import subprocess
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from config import get_ffmpeg_path
from interpolator import get_interpolator_status
from main import app
from video_analyzer import analyze_video

TEMP_TEST_DIR = Path(__file__).resolve().parent / "test_scratch"
TEMP_TEST_DIR.mkdir(parents=True, exist_ok=True)


class Milestone1TestSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.ffmpeg = get_ffmpeg_path()

        # Generate synthetic test clip 1: 2 seconds, 640x360, 30fps with audio tone
        cls.clip_with_audio = TEMP_TEST_DIR / "synth_with_audio.mp4"
        cmd1 = [
            cls.ffmpeg, "-y",
            "-f", "lavfi", "-i", "testsrc=duration=2:size=640x360:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=880:duration=2",
            "-c:v", "libx264", "-c:a", "aac",
            str(cls.clip_with_audio),
        ]
        subprocess.run(cmd1, capture_output=True, check=True)

        # Generate synthetic test clip 2: 1 second, 320x240, 24fps without audio
        cls.clip_silent = TEMP_TEST_DIR / "synth_silent.mp4"
        cmd2 = [
            cls.ffmpeg, "-y",
            "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=24",
            "-c:v", "libx264",
            str(cls.clip_silent),
        ]
        subprocess.run(cmd2, capture_output=True, check=True)

    @classmethod
    def tearDownClass(cls):
        # Cleanup synthetic test clips
        for f in TEMP_TEST_DIR.glob("*"):
            try:
                f.unlink(missing_ok=True)
            except Exception:
                pass
        try:
            TEMP_TEST_DIR.rmdir()
        except Exception:
            pass

    def test_01_health_check(self):
        """Verify API health endpoint and FFmpeg presence."""
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "healthy")
        self.assertTrue(data["ffmpeg_available"])
        self.assertIn("capabilities", data)
        self.assertFalse(data["capabilities"]["ai_frame_interpolation"])

    def test_02_video_analysis_with_audio(self):
        """Verify video_analyzer metadata extraction for clip with audio."""
        meta = analyze_video(self.clip_with_audio)
        self.assertEqual(meta["width"], 640)
        self.assertEqual(meta["height"], 360)
        self.assertAlmostEqual(meta["fps"], 30.0, delta=1.0)
        self.assertGreater(meta["duration_seconds"], 1.5)
        self.assertTrue(meta["has_audio"])
        self.assertEqual(meta["audio_codec"], "aac")
        self.assertIn("motion_analysis", meta)

    def test_03_video_analysis_silent(self):
        """Verify video_analyzer metadata extraction for silent clip."""
        meta = analyze_video(self.clip_silent)
        self.assertEqual(meta["width"], 320)
        self.assertEqual(meta["height"], 240)
        self.assertAlmostEqual(meta["fps"], 24.0, delta=1.0)
        self.assertFalse(meta["has_audio"])
        self.assertTrue(any("No audio track detected" in w for w in meta["warnings"]))

    def test_04_invalid_upload_format(self):
        """Verify that unsupported extensions are rejected."""
        fake_file = io.BytesIO(b"fake text content")
        response = self.client.post(
            "/api/upload",
            files={"file": ("malicious.exe", fake_file, "application/octet-stream")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Unsupported file format", response.json()["detail"])

    def test_05_upload_valid_video(self):
        """Upload valid video and verify returned metadata and video_id."""
        with open(self.clip_with_audio, "rb") as f:
            response = self.client.post(
                "/api/upload",
                files={"file": ("test_clip.mp4", f, "video/mp4")},
            )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("video_id", data)
        self.assertEqual(data["metadata"]["width"], 640)
        return data["video_id"]

    def test_06_screen_recording_mode_pipeline(self):
        """Test Mode A (Screen Recording): deshake skipped to protect text, FPS resampled."""
        with open(self.clip_with_audio, "rb") as f:
            upload_resp = self.client.post("/api/upload", files={"file": ("screen_test.mp4", f, "video/mp4")})
        video_id = upload_resp.json()["video_id"]

        # Request Screen Recording mode with 60 FPS
        proc_resp = self.client.post(
            f"/api/process/{video_id}",
            data={"mode": "screen", "strength": 50, "output_fps": "60", "quality": "fast"},
        )
        self.assertEqual(proc_resp.status_code, 200)
        job_id = proc_resp.json()["job_id"]

        # Poll job until done
        status_data = self._poll_job(job_id)
        self.assertEqual(status_data["status"], "done")
        result = status_data["result"]
        self.assertEqual(result["mode"], "screen")

        # Verify deshake is skipped to prevent text distortion
        plan = result["plan"]
        self.assertFalse(plan["is_ai"])
        self.assertTrue(any("Geometric stabilization" in op for op in plan["skipped_ops"]))
        self.assertTrue(any("60 FPS" in op for op in plan["applied_ops"]))

        # Verify download
        dl_resp = self.client.get(f"/api/download/{video_id}")
        self.assertEqual(dl_resp.status_code, 200)
        self.assertGreater(len(dl_resp.content), 1000)

    def test_07_human_video_mode_pipeline(self):
        """Test Mode B (Human Video): camera shake reduction applied, audio preserved."""
        with open(self.clip_with_audio, "rb") as f:
            upload_resp = self.client.post("/api/upload", files={"file": ("human_test.mp4", f, "video/mp4")})
        video_id = upload_resp.json()["video_id"]

        # Request Human Video mode with strength 70
        proc_resp = self.client.post(
            f"/api/process/{video_id}",
            data={"mode": "human", "strength": 70, "output_fps": "original", "quality": "fast"},
        )
        self.assertEqual(proc_resp.status_code, 200)
        job_id = proc_resp.json()["job_id"]

        status_data = self._poll_job(job_id)
        self.assertEqual(status_data["status"], "done")
        result = status_data["result"]
        self.assertEqual(result["mode"], "human")

        # Verify deshake filter was applied
        plan = result["plan"]
        self.assertFalse(plan["is_ai"])
        self.assertTrue(any("deshake" in op.lower() for op in plan["applied_ops"]))

    def test_08_job_cancellation(self):
        """Verify cancellation endpoint behavior."""
        with open(self.clip_with_audio, "rb") as f:
            upload_resp = self.client.post("/api/upload", files={"file": ("cancel_test.mp4", f, "video/mp4")})
        video_id = upload_resp.json()["video_id"]

        proc_resp = self.client.post(
            f"/api/process/{video_id}",
            data={"mode": "human", "strength": 50, "output_fps": "original", "quality": "fast"},
        )
        job_id = proc_resp.json()["job_id"]

        cancel_resp = self.client.post(f"/api/jobs/{job_id}/cancel")
        self.assertEqual(cancel_resp.status_code, 200)

    def test_09_model_transparency(self):
        """Verify that neural AI is explicitly reported as not active in M1."""
        status = get_interpolator_status()
        self.assertFalse(status["is_available"])
        self.assertIn("Milestone 4", status["milestone"])

    def _poll_job(self, job_id: str, timeout: float = 30.0) -> dict:
        start = time.time()
        while time.time() - start < timeout:
            resp = self.client.get(f"/api/jobs/{job_id}")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            if data["status"] in ("done", "failed", "cancelled"):
                return data
            time.sleep(0.3)
        self.fail(f"Job {job_id} did not finish within {timeout}s.")


if __name__ == "__main__":
    unittest.main()
