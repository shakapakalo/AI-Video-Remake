# AI Video Remake

A Python Flask API that generates AI-powered short videos from scene descriptions. Paste a video script or YouTube URL, and it produces images per scene, animates them into video clips, then merges everything into a final MP4 — with optional voiceover, music, sound effects, and transitions.

## Run & Operate

- `python python-api/app.py` — run the Flask API (port 8080, served at `/api`)
- Required env: `PORT` — defaults to 8080

## Stack

- Python 3.11, Flask 3.x
- ffmpeg / ffprobe for video processing
- yt-dlp for YouTube extraction
- GPT-4o via private VPS for scene analysis
- Image generation via private VPS (gpt-image-2 model)
- Video generation via private VPS (grok-imagine-1.0-video model)

## Where things live

- `python-api/app.py` — Flask app entry point, all API routes
- `python-api/job_manager.py` — in-memory job queue + job runner (threading)
- `python-api/gpt_processor.py` — GPT scene analysis
- `python-api/image_generator.py` — image generation with retry logic
- `python-api/video_generator.py` — video generation (Grok API)
- `python-api/video_combiner.py` — ffmpeg pipeline: combine, speed, fade, watermark, music
- `python-api/sound_manager.py` — sound catalog + trending sound generation
- `python-api/prompt_extractor.py` — YouTube content extraction via yt-dlp
- `python-api/storage/` — generated images, videos, and final outputs

## API Endpoints

- `POST /api/generate` — submit a job (pass `details` text or `url` YouTube link)
- `GET /api/job/<job_id>` — poll job status and get result URLs
- `GET /api/files/<path>` — serve generated files (images, videos, final)
- `GET /api/healthz` — health check

## Architecture decisions

- Jobs run in background threads; in-memory `_jobs` dict tracks state — restarts clear job history
- Scene video failures fall back to a static image clip (6s) so the job always completes
- All VPS calls use `Bearer ranaji` auth to the private GPU server at 217.77.8.115

## User preferences

_Populate as you build — explicit user instructions worth remembering across sessions._

## Gotchas

- Always pass `PORT=8080` when running manually; the workflow config sets this automatically
- Sound effect MP3s must exist in `python-api/storage/sounds/` — they are downloaded from the repo
- Trending sounds are generated on first use via ffmpeg
