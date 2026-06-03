# AI Video Remake API

Convert any YouTube URL or text script into an AI-generated short video (9:16 portrait, MP4) with per-scene images, animated clips, music, sound effects, and voiceover support.

---

## Quick Start

### 1. Submit a job

```bash
# From a YouTube URL
curl -X POST https://YOUR_SERVER/api/generate \
  -H "Content-Type: application/json" \
  -d '{"url": "https://youtube.com/watch?v=XXXXXXX"}'

# From a text script/description
curl -X POST https://YOUR_SERVER/api/generate \
  -H "Content-Type: application/json" \
  -d '{"details": "A lone astronaut lands on Mars and discovers an ancient temple buried in red sand."}'
```

**Response:**
```json
{ "job_id": "abc123-..." }
```

---

### 2. Poll for status

```bash
curl https://YOUR_SERVER/api/job/abc123-...
```

**Response (in progress):**
```json
{
  "job_id": "abc123",
  "status": "processing",
  "step": "Scene 2/5: Generating video",
  "total_scenes": 5,
  "completed_scenes": 1,
  "scenes": [...],
  "final_video_url": null
}
```

**Response (done):**
```json
{
  "status": "completed",
  "final_video_url": "/api/files/final/abc123_final.mp4",
  "scenes": [...]
}
```

**Status values:** `queued` → `extracting` → `processing` → `combining` → `completed` / `failed`

---

### 3. Download the video

```bash
curl -O https://YOUR_SERVER/api/files/final/abc123_final.mp4
```

Files also served at:
- `/api/files/images/<filename>` — per-scene images
- `/api/files/videos/<filename>` — per-scene video clips

---

## POST /api/generate — All Parameters

### Input (required — one of)

| Parameter | Type | Description |
|-----------|------|-------------|
| `url` | string | YouTube URL to extract content from |
| `details` | string | Direct text script or scene description (skips YouTube extraction) |

---

### GPT / Scene Analysis

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_scenes` | integer | auto | Limit number of scenes GPT generates (e.g. `5`) |
| `language` | string | auto | Output language for prompts (e.g. `"english"`, `"hindi"`, `"urdu"`) |
| `chat_id_gpt` | string | internal | Custom chat session ID for GPT calls |

---

### Image Generation

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `image_style` | string | none | Art style prefix (e.g. `"cinematic"`, `"anime"`, `"watercolor"`, `"photorealistic"`) |
| `negative_prompt` | string | none | Things to avoid in images (e.g. `"blurry, low quality, text"`) |
| `chat_id_image` | string | internal | Custom chat session ID for image API calls |

---

### Video Generation (Grok API)

| Parameter | Type | Default | Options | Description |
|-----------|------|---------|---------|-------------|
| `aspect_ratio` | string | `"9:16"` | `"9:16"`, `"16:9"`, `"1:1"`, `"3:2"`, `"2:3"` | Output video aspect ratio |
| `video_length` | integer | `6` | `6`, `10`, `15` | Clip length in seconds per scene |
| `resolution` | string | `"720p"` | `"480p"`, `"720p"` | Video resolution |
| `preset` | string | `"normal"` | `"normal"`, `"fun"`, `"spicy"` | Motion style preset |
| `motion_strength` | float | null | `0.0`–`1.0` | How much the scene moves (reserved, not yet active) |
| `seed` | integer | null | any | Reproducibility seed for video generation |
| `loop` | boolean | `false` | `true`/`false` | Make the video loop seamlessly |
| `negative_video_prompt` | string | none | — | Motion elements to avoid (e.g. `"camera shake, flash"`) |
| `chat_id_video` | string | internal | — | Custom chat session ID for video API calls |

> **Note:** If video generation fails (VPS tokens expired, timeout, etc.), each scene automatically falls back to an animated Ken Burns clip (zoom + pan effect, 1080×1920, 24fps, 6s).

---

### Final Video Assembly (ffmpeg)

| Parameter | Type | Default | Options | Description |
|-----------|------|---------|---------|-------------|
| `video_speed` | float | `1.0` | `0.5`–`3.0` | Playback speed multiplier (e.g. `1.5` = 50% faster) |
| `transition` | string | `"none"` | `"none"`, `"fade"`, `"crossfade"` | Scene-to-scene transition |
| `fade_duration` | float | `0.5` | seconds | Fade/crossfade duration |
| `fps` | integer | `24` | `24`, `30`, `60` | Output video frame rate |
| `watermark_text` | string | none | — | Text overlay watermark (e.g. `"@myhandle"`) |
| `mute_original_audio` | boolean | `false` | — | Strip all audio from source clips |
| `intro_text` | string | none | — | Title card text shown at the start |
| `outro_text` | string | none | — | End card text shown at the finish |
| `bg_color` | string | `"black"` | CSS color / hex | Background fill color (e.g. `"black"`, `"#1a1a2e"`) |
| `fade` | boolean | `false` | — | Apply fade-in/out to the entire video |

---

### Background Music

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `background_music` | string | none | URL to an MP3/audio file to mix behind all scenes |
| `music_volume` | float | `0.3` | `0.0`–`1.0` — Music volume level |
| `music_fade_in` | float | `0.0` | Seconds to fade music in at the start |
| `music_fade_out` | float | `0.0` | Seconds to fade music out at the end |

---

### Sound Effects

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `sound_effects` | boolean | `false` | Let GPT assign sound effects per scene |
| `trending_sounds` | boolean | `false` | Pre-generate a library of trending sounds before processing |

---

### Voiceover / Transcript

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `voiceover` | string | none | Transcript text — OR — a URL (YouTube, etc.) from which the transcript is auto-extracted |
| `extract_voiceover` | boolean | `false` | Auto-extract voiceover from the main `url` parameter |
| `trim_silence` | boolean | `false` | Remove silent sections from the final video |

---

## Full Example Request

```json
POST /api/generate
{
  "url": "https://youtube.com/watch?v=XXXXXXX",
  "max_scenes": 6,
  "language": "english",
  "image_style": "cinematic",
  "negative_prompt": "blurry, watermark, text overlay",
  "aspect_ratio": "9:16",
  "video_length": 6,
  "resolution": "720p",
  "preset": "normal",
  "negative_video_prompt": "camera shake, flash, distortion",
  "video_speed": 1.0,
  "transition": "fade",
  "fade_duration": 0.5,
  "fps": 24,
  "watermark_text": "@myaccount",
  "background_music": "https://example.com/lofi.mp3",
  "music_volume": 0.25,
  "music_fade_in": 2.0,
  "music_fade_out": 3.0,
  "sound_effects": true,
  "voiceover": "https://youtube.com/watch?v=YYYYYYY",
  "trim_silence": false
}
```

---

## Health Check

```bash
curl https://YOUR_SERVER/api/healthz
# → {"status": "ok"}
```

---

## Architecture

```
POST /api/generate
  │
  ├─ YouTube URL?  ──► yt-dlp extract transcript/description
  │   OR text details?  ──► used directly
  │
  ├─ GPT-4o  ──► break into scenes: image_prompt + video_prompt + sound_effect
  │
  ├─ Per scene (parallel for images):
  │   ├─ Image VPS (gpt-image-2)  ──► 1080×1920 PNG
  │   └─ Video VPS (grok-imagine-1.0-video)
  │       └─ on failure: Ken Burns animated clip from image (ffmpeg)
  │
  └─ ffmpeg combine:
      speed · transitions · watermark · music · intro/outro · silence trim
      └─► final_<job_id>.mp4
```

---

## Contabo VPS — Install & Update

See [`install.sh`](./install.sh) for 1-click Contabo setup.  
See [`update.sh`](./update.sh) for 1-click pull-and-restart from GitHub.

**GitHub repo:** https://github.com/shakapakalo/AI-Video-Remake
