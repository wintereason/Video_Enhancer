import React, { useState, useEffect, useRef } from 'react';
import {
  Upload,
  Film,
  Monitor,
  User,
  Sliders,
  CheckCircle2,
  AlertCircle,
  Play,
  Pause,
  Download,
  RotateCcw,
  Sparkles,
  Info,
  Layers,
  Clock,
  HardDrive
} from 'lucide-react';

interface HealthData {
  status: string;
  ffmpeg_available: boolean;
  app_name: string;
  app_version: string;
  capabilities: Record<string, boolean>;
}

interface VideoMetadata {
  filename: string;
  file_size_mb: number;
  duration_seconds: number;
  width: number;
  height: number;
  fps: number;
  frame_count: number | null;
  video_codec: string;
  audio_codec: string | null;
  has_audio: boolean;
  bit_rate_kbps: number | null;
  warnings: string[];
  motion_analysis?: {
    motion_intensity: string;
    avg_frame_delta: number;
    recommendation: string;
  };
}

interface SmoothingPlan {
  mode: string;
  applied_ops: string[];
  skipped_ops: string[];
  is_ai: boolean;
  notes: string[];
  quality: string;
  vf_filters: string;
}

interface JobResult {
  video_id: string;
  download_url: string;
  preview_url: string;
  mode: string;
  plan: SmoothingPlan;
  file_size_mb: number;
  quality_profile: string;
}

export default function App() {
  // System Health
  const [health, setHealth] = useState<HealthData | null>(null);

  // Upload & Video State
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [videoId, setVideoId] = useState<string | null>(null);
  const [metadata, setMetadata] = useState<VideoMetadata | null>(null);

  // Enhancement Settings
  const [mode, setMode] = useState<'screen' | 'human'>('human');
  const [strength, setStrength] = useState<number>(50);
  const [outputFps, setOutputFps] = useState<string>('original');
  const [quality, setQuality] = useState<string>('balanced');

  // Job & Processing State
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<string | null>(null);
  const [progress, setProgress] = useState<number>(0);
  const [statusMessage, setStatusMessage] = useState<string>('');
  const [jobResult, setJobResult] = useState<JobResult | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Comparison Player State
  const originalVideoRef = useRef<HTMLVideoElement | null>(null);
  const processedVideoRef = useRef<HTMLVideoElement | null>(null);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Fetch health on mount
  useEffect(() => {
    fetch('/api/health')
      .then((res) => res.json())
      .then((data: HealthData) => setHealth(data))
      .catch((err) => {
        console.warn('Could not fetch health:', err);
        setHealth({
          status: 'offline',
          ffmpeg_available: false,
          app_name: 'AI Video Smoother',
          app_version: '1.0.0',
          capabilities: {},
        });
      });
  }, []);

  // Poll Job Status
  useEffect(() => {
    if (!jobId || jobStatus === 'done' || jobStatus === 'failed' || jobStatus === 'cancelled') {
      return;
    }

    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/jobs/${jobId}`);
        if (!res.ok) throw new Error('Failed to fetch job status');
        const data = await res.json();
        setJobStatus(data.status);
        setProgress(data.progress || 0);
        setStatusMessage(data.message || 'Processing video...');

        if (data.status === 'done' && data.result) {
          setJobResult(data.result);
          clearInterval(interval);
        } else if (data.status === 'failed') {
          setErrorMessage(data.error || 'Video processing failed.');
          clearInterval(interval);
        } else if (data.status === 'cancelled') {
          setErrorMessage('Job was cancelled.');
          clearInterval(interval);
        }
      } catch (err: any) {
        console.error('Job polling error:', err);
      }
    }, 500);

    return () => clearInterval(interval);
  }, [jobId, jobStatus]);

  // File Upload Handler
  const handleFileUpload = async (file: File) => {
    setErrorMessage(null);
    setIsUploading(true);
    setUploadProgress(10);

    const formData = new FormData();
    formData.append('file', file);

    try {
      setUploadProgress(40);
      const res = await fetch('/api/upload', {
        method: 'POST',
        body: formData,
      });
      setUploadProgress(85);

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Upload failed');
      }

      setVideoId(data.video_id);
      setMetadata(data.metadata);
      setUploadProgress(100);

      // Auto-tune initial mode suggestion
      if (data.metadata?.motion_analysis?.recommendation?.toLowerCase().includes('screen')) {
        setMode('screen');
      }
    } catch (err: any) {
      setErrorMessage(err.message || 'An error occurred while uploading.');
    } finally {
      setIsUploading(false);
    }
  };

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const onDragLeave = () => {
    setIsDragging(false);
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileUpload(e.dataTransfer.files[0]);
    }
  };

  // Start Processing
  const handleStartProcessing = async () => {
    if (!videoId) return;
    setErrorMessage(null);
    setJobResult(null);
    setProgress(5);
    setJobStatus('queued');
    setStatusMessage('Submitting enhancement job...');

    const formData = new FormData();
    formData.append('mode', mode);
    formData.append('strength', strength.toString());
    formData.append('output_fps', outputFps);
    formData.append('quality', quality);

    try {
      const res = await fetch(`/api/process/${videoId}`, {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to start processing');
      }
      setJobId(data.job_id);
      setJobStatus('running');
    } catch (err: any) {
      setErrorMessage(err.message || 'Could not initiate video processing.');
      setJobStatus(null);
    }
  };

  // Cancel Job
  const handleCancelJob = async () => {
    if (!jobId) return;
    try {
      await fetch(`/api/jobs/${jobId}/cancel`, { method: 'POST' });
      setStatusMessage('Cancelling job...');
    } catch (err) {
      console.error('Cancel request failed:', err);
    }
  };

  // Synchronized Video Comparison
  const togglePlayBoth = () => {
    const orig = originalVideoRef.current;
    const proc = processedVideoRef.current;
    if (!orig || !proc) return;

    if (orig.paused || proc.paused) {
      // Sync timestamps before starting
      proc.currentTime = orig.currentTime;
      orig.play();
      proc.play();
      setIsPlaying(true);
    } else {
      orig.pause();
      proc.pause();
      setIsPlaying(false);
    }
  };

  const handleSeekSync = (e: React.SyntheticEvent<HTMLVideoElement>) => {
    const orig = originalVideoRef.current;
    const proc = processedVideoRef.current;
    if (!orig || !proc) return;

    if (e.currentTarget === orig && Math.abs(proc.currentTime - orig.currentTime) > 0.15) {
      proc.currentTime = orig.currentTime;
    }
  };

  // Reset Application
  const handleReset = () => {
    setVideoId(null);
    setMetadata(null);
    setJobId(null);
    setJobStatus(null);
    setJobResult(null);
    setErrorMessage(null);
    setProgress(0);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  return (
    <div className="app-container">
      {/* Header */}
      <header className="app-header">
        <div className="brand-wrapper">
          <div className="brand-icon">
            <Film size={22} />
          </div>
          <div>
            <h1 className="brand-title">
              Smoothly<span>.</span>
            </h1>
            <p className="brand-tagline">AI Video Smoother &amp; Motion Enhancement</p>
          </div>
        </div>

        <div className="health-status-badge">
          <div
            className={`health-dot ${health?.ffmpeg_available ? 'healthy' : ''}`}
          />
          <span>
            {health?.ffmpeg_available
              ? 'Local CPU Engine Ready (FFmpeg 7.1)'
              : 'Engine Initializing...'}
          </span>
        </div>
      </header>

      {/* Error Banner */}
      {errorMessage && (
        <div
          style={{
            background: 'var(--danger-bg)',
            border: '1px solid #fca5a5',
            color: 'var(--danger)',
            padding: '14px 18px',
            borderRadius: 'var(--radius-md)',
            marginBottom: '20px',
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            fontSize: '14px',
            fontWeight: 500,
          }}
        >
          <AlertCircle size={20} />
          <span>{errorMessage}</span>
        </div>
      )}

      {/* Main Workspace Card */}
      <main className="main-card">
        {/* Step 1: Upload Dropzone if no video loaded */}
        {!videoId && (
          <div>
            <div
              className={`dropzone ${isDragging ? 'drag-active' : ''}`}
              onDragOver={onDragOver}
              onDragLeave={onDragLeave}
              onDrop={onDrop}
              onClick={() => fileInputRef.current?.click()}
            >
              <div className="dropzone-icon-circle">
                <Upload size={30} />
              </div>
              <h2 className="dropzone-title">Upload a video to smooth and enhance</h2>
              <p className="dropzone-desc">
                Drag and drop your file here, or click to browse. Supports MP4, MOV, MKV,
                WebM, and AVI up to 500 MB.
              </p>
              <input
                ref={fileInputRef}
                type="file"
                accept="video/*"
                className="file-input-hidden"
                onChange={(e) => {
                  if (e.target.files && e.target.files[0]) {
                    handleFileUpload(e.target.files[0]);
                  }
                }}
              />
            </div>

            {isUploading && (
              <div className="progress-container" style={{ marginTop: '20px' }}>
                <div className="progress-header">
                  <span className="progress-title">Uploading &amp; Inspecting Video...</span>
                  <span style={{ fontSize: '13px', fontWeight: 700 }}>{uploadProgress}%</span>
                </div>
                <div className="progress-bar-track">
                  <div className="progress-bar-fill" style={{ width: `${uploadProgress}%` }} />
                </div>
              </div>
            )}
          </div>
        )}

        {/* Step 2: Metadata & Controls if Video Uploaded */}
        {videoId && metadata && (
          <div>
            {/* Metadata Summary Chips */}
            <div className="metadata-container">
              <div className="metadata-header">
                <div className="file-pill-title">
                  <Film size={18} color="var(--primary)" />
                  <span>{metadata.filename}</span>
                </div>
                <button className="btn-reset" onClick={handleReset} style={{ padding: '6px 12px', fontSize: '12px' }}>
                  Change Video
                </button>
              </div>

              <div className="metadata-grid">
                <div className="metadata-chip">
                  <div className="chip-label">Resolution</div>
                  <div className="chip-value">{metadata.width} × {metadata.height}</div>
                </div>
                <div className="metadata-chip">
                  <div className="chip-label">Frame Rate</div>
                  <div className="chip-value">{metadata.fps} FPS</div>
                </div>
                <div className="metadata-chip">
                  <div className="chip-label">Duration</div>
                  <div className="chip-value">
                    {Math.floor(metadata.duration_seconds / 60)}:
                    {Math.floor(metadata.duration_seconds % 60).toString().padStart(2, '0')}s
                  </div>
                </div>
                <div className="metadata-chip">
                  <div className="chip-label">File Size</div>
                  <div className="chip-value">{metadata.file_size_mb} MB</div>
                </div>
                <div className="metadata-chip">
                  <div className="chip-label">Audio Track</div>
                  <div className="chip-value">
                    {metadata.has_audio ? (metadata.audio_codec?.toUpperCase() || 'Audio Present') : 'Silent (No Audio)'}
                  </div>
                </div>
              </div>

              {metadata.motion_analysis && (
                <div className="motion-recommendation-bar">
                  <Info size={16} />
                  <span>
                    <strong>Motion Analysis:</strong> {metadata.motion_analysis.recommendation}
                  </span>
                </div>
              )}
            </div>

            {/* Step 3: Enhancement Modes */}
            <h3 className="section-title">
              <Layers size={18} />
              1. Choose Enhancement Mode
            </h3>
            <div className="mode-grid">
              <div
                className={`mode-card ${mode === 'screen' ? 'selected' : ''}`}
                onClick={() => setMode('screen')}
              >
                <div className="mode-card-header">
                  <div className="mode-card-icon">
                    <Monitor size={20} />
                  </div>
                  <span className="mode-card-name">Mode A: Screen Recording</span>
                </div>
                <p className="mode-card-desc">
                  Optimized for desktop screencasts and app walkthroughs. Protects sharp text,
                  code editors, and screen borders. Completely avoids geometric warping.
                </p>
                <span className="mode-tag screen">Text-Preserving Architecture</span>
              </div>

              <div
                className={`mode-card ${mode === 'human' ? 'selected' : ''}`}
                onClick={() => setMode('human')}
              >
                <div className="mode-card-header">
                  <div className="mode-card-icon">
                    <User size={20} />
                  </div>
                  <span className="mode-card-name">Mode B: Human / Camera Video</span>
                </div>
                <p className="mode-card-desc">
                  Reduces handheld camera jitter with motion compensation and edge mirroring.
                  Preserves body proportions, hand gestures, and natural facial movement.
                </p>
                <span className="mode-tag human">Camera-Shake Reduction</span>
              </div>
            </div>

            {/* Step 4: Controls & Configuration */}
            <h3 className="section-title">
              <Sliders size={18} />
              2. Enhancement Settings
            </h3>
            <div className="controls-grid">
              {/* Smoothing Strength */}
              <div className="control-box">
                <div className="control-header">
                  <span className="control-label">Smoothing Strength</span>
                  <span className="control-badge">{strength}%</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={strength}
                  onChange={(e) => setStrength(Number(e.target.value))}
                  className="range-slider"
                  disabled={jobStatus === 'running'}
                />
                <p className="control-hint">
                  {mode === 'screen'
                    ? 'In screen mode, geometric shake stabilization is disabled to protect crisp code fonts.'
                    : strength < 15
                    ? 'Below 15%: Stabilization is turned off to keep frames untouched.'
                    : `Active: Applying FFmpeg motion compensation with ${strength < 35 ? '16px' : strength < 70 ? '32px' : strength < 90 ? '48px' : '64px'} search radius.`}
                </p>
              </div>

              {/* Output FPS */}
              <div className="control-box">
                <div className="control-header">
                  <span className="control-label">Target Frame Rate</span>
                  <span className="control-badge">
                    {outputFps === 'original' ? `${metadata.fps} FPS` : `${outputFps} FPS`}
                  </span>
                </div>
                <select
                  className="select-input"
                  value={outputFps}
                  onChange={(e) => setOutputFps(e.target.value)}
                  disabled={jobStatus === 'running'}
                >
                  <option value="original">Keep Original ({metadata.fps} FPS)</option>
                  <option value="24">24 FPS (Cinematic standard)</option>
                  <option value="30">30 FPS (Standard video)</option>
                  <option value="60">60 FPS (High smoothness)</option>
                  <option value="120">120 FPS (High-rate; CPU intensive)</option>
                </select>
                <p className="control-hint">
                  Conventional frame-rate resampling. (Pretrained RIFE AI interpolation is scheduled for Milestone 4).
                </p>
              </div>

              {/* Export Quality */}
              <div className="control-box">
                <div className="control-header">
                  <span className="control-label">Export Quality Profile</span>
                  <span className="control-badge">{quality.toUpperCase()}</span>
                </div>
                <select
                  className="select-input"
                  value={quality}
                  onChange={(e) => setQuality(e.target.value)}
                  disabled={jobStatus === 'running'}
                >
                  <option value="high">High Quality (CRF 18 • Best fidelity)</option>
                  <option value="balanced">Balanced (CRF 22 • Recommended)</option>
                  <option value="fast">Fast / Compressed (CRF 26 • Smallest size)</option>
                </select>
                <p className="control-hint">
                  Encodes with H.264/AAC MP4 with faststart streaming headers for universal playback.
                </p>
              </div>

              {/* Engine Status */}
              <div className="control-box">
                <div className="control-header">
                  <span className="control-label">Processing Architecture</span>
                  <span className="control-badge">CPU-Only</span>
                </div>
                <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: '4px' }}>
                  <strong>Milestone 1 MVP:</strong> Running in-process background workers. No GPU required. All
                  operations run locally on your machine with full privacy.
                </p>
              </div>
            </div>

            {/* Action Button */}
            {!jobResult && (
              <button
                className="btn-primary"
                onClick={handleStartProcessing}
                disabled={jobStatus === 'running' || jobStatus === 'queued'}
              >
                <Sparkles size={18} />
                {jobStatus === 'running' ? 'Processing Video...' : 'Enhance Video'}
              </button>
            )}

            {/* Active Job Progress Bar */}
            {jobStatus && jobStatus !== 'done' && (
              <div className="progress-container">
                <div className="progress-header">
                  <span className="progress-title">
                    <Clock size={16} />
                    {statusMessage}
                  </span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <span style={{ fontSize: '13px', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
                      {progress}%
                    </span>
                    {jobStatus === 'running' && (
                      <button className="btn-cancel" onClick={handleCancelJob}>
                        Cancel
                      </button>
                    )}
                  </div>
                </div>
                <div className="progress-bar-track">
                  <div className="progress-bar-fill" style={{ width: `${progress}%` }} />
                </div>
                <p className="progress-status-msg">
                  Processing locally on CPU. Long videos may take several moments.
                </p>
              </div>
            )}
          </div>
        )}

        {/* Step 5: Before & After Comparison & Results */}
        {jobResult && (
          <section className="result-section">
            <h3 className="section-title">
              <CheckCircle2 size={18} color="var(--success)" />
              Enhancement Complete — Side-by-Side Comparison
            </h3>

            <div className="comparison-grid">
              {/* Original Video */}
              <div className="video-player-card">
                <div className="video-player-header">
                  <span>Original Source Video</span>
                  <span style={{ opacity: 0.7 }}>{metadata?.width}×{metadata?.height}</span>
                </div>
                <video
                  ref={originalVideoRef}
                  src={`/api/preview/original/${jobResult.video_id}`}
                  className="video-element"
                  controls
                  onTimeUpdate={handleSeekSync}
                  preload="metadata"
                />
              </div>

              {/* Enhanced Video */}
              <div className="video-player-card">
                <div className="video-player-header">
                  <span style={{ color: '#818cf8' }}>Enhanced Video (Smoothed)</span>
                  <span style={{ opacity: 0.7 }}>{jobResult.quality_profile}</span>
                </div>
                <video
                  ref={processedVideoRef}
                  src={jobResult.preview_url}
                  className="video-element"
                  controls
                  preload="metadata"
                />
              </div>
            </div>

            {/* Play Both Toggle */}
            <div className="sync-bar">
              <button className="btn-sync" onClick={togglePlayBoth}>
                {isPlaying ? <Pause size={16} /> : <Play size={16} />}
                {isPlaying ? 'Pause Both Videos' : 'Play Both Videos Simultaneously'}
              </button>
            </div>

            {/* Enhancement Audit Card */}
            <div className="audit-card">
              <h4 className="audit-title">
                <HardDrive size={16} />
                Transparency Report — Enhancement Operations Applied
              </h4>
              <ul className="audit-list">
                {jobResult.plan.applied_ops.map((op, index) => (
                  <li key={index} className="audit-item">
                    <CheckCircle2 size={16} className="audit-icon applied" />
                    <span>{op}</span>
                  </li>
                ))}
                {jobResult.plan.skipped_ops.map((op, index) => (
                  <li key={index} className="audit-item">
                    <Info size={16} className="audit-icon skipped" />
                    <span style={{ color: 'var(--text-muted)' }}>{op}</span>
                  </li>
                ))}
              </ul>
              <div style={{ fontSize: '12px', color: 'var(--text-subtle)' }}>
                {jobResult.plan.notes.join(' • ')}
              </div>
            </div>

            {/* Download & New Video Actions */}
            <div className="download-bar">
              <a
                href={jobResult.download_url}
                className="btn-download"
                download
              >
                <Download size={18} />
                Download Enhanced Video ({jobResult.file_size_mb} MB MP4)
              </a>
              <button className="btn-reset" onClick={handleReset}>
                <RotateCcw size={16} style={{ display: 'inline', marginRight: '6px' }} />
                Enhance Another Video
              </button>
            </div>
          </section>
        )}
      </main>

      {/* Footer */}
      <footer className="app-footer">
        <p>
          <strong>Smoothly</strong> — CPU-friendly AI-assisted video enhancement.
        </p>
        <p>
          Runs locally on your Windows machine with FFmpeg. No files are transmitted to external servers.
        </p>
      </footer>
    </div>
  );
}
