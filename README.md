# Smoothly — AI Video Smoother MVP

A CPU-friendly web MVP for uploading a video and processing it with FFmpeg. It has separate screen-recording and human/camera modes. **This starter is not yet AI-based**: screen mode preserves geometry and can change output FPS; human mode can apply FFmpeg's conventional `deshake` filter. It does not yet synthesize intermediate frames, detect a cursor, understand intended actions, or correct human pose trajectories.

## Requirements
- Windows 10/11
- Python 3.10+
- FFmpeg and FFprobe installed and available on PATH

Check installation in a new PowerShell window:
```powershell
python --version
ffmpeg -version
ffprobe -version
```

## Setup (PowerShell)
From this folder:
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
uvicorn backend.main:app --reload
```
Open http://127.0.0.1:8000 . API health: http://127.0.0.1:8000/api/health .

## Deployment

The application uses FFmpeg and long-running background jobs, so deploy the
frontend and backend separately:

1. Create a Render Web Service from this repository. Render will use
   [`render.yaml`](./render.yaml) to install the Python dependencies and start
   the FastAPI backend.
2. Copy the Render service URL, for example
   `https://your-service.onrender.com`.
3. Create a Vercel project from this repository. The root `vercel.json` builds
   the [`frontend`](./frontend/) Vite application.
4. Add the Vercel environment variable `VITE_API_URL` with the Render service
   URL, then redeploy.

The Render service uses local disk and in-memory job state, so it is suitable
for a demo deployment but not for durable production storage or multiple
backend instances.

If PowerShell blocks activation, use `venv\Scripts\python.exe -m pip install -r backend\requirements.txt`, then `venv\Scripts\python.exe -m uvicorn backend.main:app --reload`.

## What the modes do
- **Screen recording:** avoids geometric stabilization to protect text and UI; optionally resamples FPS and re-encodes.
- **Human/camera:** applies FFmpeg `deshake` if strength is at least 15. This can crop/alter edges or fail to help some footage; compare the result with the original.
- **FPS:** 30/60 is resampling, not AI interpolation. To generate believable intermediate frames, integrate a compatible pretrained frame-interpolation model later.

## Limitations and next steps
1. Add FFprobe-based metadata and duration validation.
2. Add a background job queue, progress polling, and automatic output expiry before public deployment.
3. Integrate a tested pretrained RIFE implementation for frame interpolation; benchmark CPU speed first, as it may be very slow without a supported GPU.
4. Add cursor detection/path smoothing for screen recordings as a separate feature; cursor pixels must be detected and reconstructed carefully.
5. Add human pose tracking and trajectory smoothing as an optional analysis feature, with conservative changes and artifact checks.
6. Add file-size limits at the reverse proxy, authentication, rate limiting, and isolated processing before exposing the server to the internet.

Do not expose this development server publicly as-is. It is designed for local experimentation.
