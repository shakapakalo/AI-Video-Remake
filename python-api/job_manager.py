import threading
import uuid
import logging
import os
import subprocess
from datetime import datetime

logger = logging.getLogger(__name__)


def _make_static_clip(image_path: str, job_id: str, scene_num: int) -> str:
    """
    Convert a saved image into a 6-second animated video clip using ffmpeg.
    Applies a Ken Burns (zoom + pan) effect so the clip looks dynamic rather
    than a still frame.  Four patterns rotate by scene number.
    """
    out_path = os.path.join(
        os.path.dirname(__file__), "storage", "videos",
        f"{job_id}_scene{scene_num}_static.mp4"
    )

    fps = 24
    duration = 6
    total_frames = fps * duration  # 144

    patterns = [
        # 0 – slow zoom in from centre
        (
            f"scale=8000:-1,zoompan=z='min(zoom+0.0015,1.5)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={total_frames}:s=1080x1920:fps={fps}"
        ),
        # 1 – slow zoom out from centre
        (
            f"scale=8000:-1,zoompan=z='if(lte(zoom,1.0),1.5,max(zoom-0.0015,1.0))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={total_frames}:s=1080x1920:fps={fps}"
        ),
        # 2 – pan left to right while zoomed in
        (
            f"scale=8000:-1,zoompan=z='1.3':x='if(gte(on,1),x+2,0)':y='ih/2-(ih/zoom/2)'"
            f":d={total_frames}:s=1080x1920:fps={fps}"
        ),
        # 3 – pan top to bottom while zoomed in
        (
            f"scale=8000:-1,zoompan=z='1.3':x='iw/2-(iw/zoom/2)':y='if(gte(on,1),y+2,0)'"
            f":d={total_frames}:s=1080x1920:fps={fps}"
        ),
    ]

    vf = patterns[int(scene_num) % len(patterns)]

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", image_path,
        "-c:v", "libx264",
        "-t", str(duration),
        "-pix_fmt", "yuv420p",
        "-vf", vf,
        "-r", str(fps),
        "-preset", "fast",
        out_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        logger.warning("Ken Burns clip failed (%s), falling back to plain static", result.stderr[-120:])
        cmd_plain = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", image_path,
            "-c:v", "libx264", "-t", str(duration),
            "-pix_fmt", "yuv420p",
            "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black",
            "-r", str(fps),
            out_path,
        ]
        result2 = subprocess.run(cmd_plain, capture_output=True, text=True)
        if result2.returncode != 0:
            raise RuntimeError(f"Static clip from image failed: {result2.stderr[-100:]}")

    logger.info("Animated clip created (scene %s): %s", scene_num, os.path.basename(out_path))
    return out_path

_jobs: dict[str, dict] = {}
_lock = threading.Lock()

STORAGE_DIR = os.path.join(os.path.dirname(__file__), "storage")


def create_job(youtube_url: str, params: dict) -> str:
    job_id = str(uuid.uuid4())
    with _lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "url": youtube_url,
            "params": params,
            "status": "queued",
            "step": "Waiting to start",
            "total_scenes": 0,
            "completed_scenes": 0,
            "scenes": [],
            "final_video_url": None,
            "error": None,
            "created_at": datetime.utcnow().isoformat(),
            "finished_at": None,
        }
    return job_id


def get_job(job_id: str) -> dict | None:
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def _update(job_id: str, **kwargs):
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(kwargs)


def run_job(job_id: str):
    from prompt_extractor import extract_prompt
    from gpt_processor import process_with_gpt
    from image_generator import generate_image
    from video_generator import generate_video
    from video_combiner import save_image, save_video, combine_videos
    from sound_manager import apply_sound_to_clip

    job = _jobs[job_id]
    params = job["params"]

    # GPT controls
    max_scenes    = params.get("max_scenes")
    language      = params.get("language")
    chat_id_gpt   = params.get("chat_id_gpt")
    # Image controls
    image_style     = params.get("image_style")
    negative_prompt = params.get("negative_prompt")
    chat_id_image   = params.get("chat_id_image")
    # Video generation controls (Grok API)
    chat_id_video        = params.get("chat_id_video")
    aspect_ratio         = params.get("aspect_ratio", "9:16")
    video_length         = int(params.get("video_length", 6))
    resolution           = params.get("resolution", "720p")
    preset               = params.get("preset", "normal")
    motion_strength      = params.get("motion_strength")
    seed                 = params.get("seed")
    loop                 = bool(params.get("loop", False))
    negative_video_prompt = params.get("negative_video_prompt")
    # Final video controls (ffmpeg)
    video_speed          = float(params.get("video_speed", 1.0))
    transition           = params.get("transition", "none")
    fade_duration        = float(params.get("fade_duration", 0.5))
    fps                  = int(params.get("fps", 24))
    watermark_text       = params.get("watermark_text")
    mute_original_audio  = bool(params.get("mute_original_audio", False))
    intro_text           = params.get("intro_text")
    outro_text           = params.get("outro_text")
    bg_color             = params.get("bg_color", "black")
    fade                 = params.get("fade", False)
    # Music controls
    background_music     = params.get("background_music")
    music_volume         = float(params.get("music_volume", 0.3))
    music_fade_in        = float(params.get("music_fade_in", 0.0))
    music_fade_out       = float(params.get("music_fade_out", 0.0))
    # Optional features
    sound_effects        = bool(params.get("sound_effects", False))
    trim_silence_opt     = bool(params.get("trim_silence", False))
    extract_voiceover_opt = bool(params.get("extract_voiceover", False))
    trending_sounds      = bool(params.get("trending_sounds", False))

    try:
        # ── Trending sounds ────────────────────────────────────
        if trending_sounds:
            from sound_manager import ensure_trending_sounds
            _update(job_id, step="Downloading trending sounds")
            ensure_trending_sounds()

        # ── Voiceover extraction ───────────────────────────────
        voiceover_text = None
        voiceover_param_raw = params.get("voiceover") or ""

        if voiceover_param_raw and voiceover_param_raw.strip().lower().startswith(("http://", "https://")):
            from voiceover_extractor import extract_voiceover
            voiceover_url = voiceover_param_raw.strip()
            _update(job_id, step="Extracting transcript from voiceover URL")
            logger.info("[JOB %s] voiceover param is a URL — extracting transcript: %s", job_id, voiceover_url)
            voiceover_text = extract_voiceover(voiceover_url)
            if voiceover_text:
                logger.info("[JOB %s] Voiceover extracted from URL (%d chars)", job_id, len(voiceover_text))
                voiceover_param_raw = voiceover_text
            else:
                logger.warning("[JOB %s] Voiceover URL extraction returned nothing", job_id)
                voiceover_param_raw = ""

        elif extract_voiceover_opt and job.get("url"):
            from voiceover_extractor import extract_voiceover, is_supported_url
            if is_supported_url(job["url"]):
                _update(job_id, step="Extracting voice-over from video")
                logger.info("[JOB %s] Extracting voiceover from %s", job_id, job["url"])
                voiceover_text = extract_voiceover(job["url"])
                if voiceover_text:
                    logger.info("[JOB %s] Voiceover extracted (%d chars)", job_id, len(voiceover_text))

        # ── Content extraction ─────────────────────────────────
        direct_details = params.get("details")
        if direct_details:
            logger.info("[JOB %s] Using provided details directly (skipping YouTube extraction)", job_id)
            _update(job_id, status="processing", step="Using provided video details")
            extracted_text = direct_details
        else:
            _update(job_id, status="extracting", step="Extracting YouTube video content")
            extracted_text = extract_prompt(job["url"])

        if voiceover_text:
            extracted_text = f"{extracted_text}\n\n[VOICE-OVER TRANSCRIPT]\n{voiceover_text}"

        _update(job_id, status="processing", step="Analyzing scenes with GPT")
        gpt_result = process_with_gpt(
            extracted_text,
            chat_id=chat_id_gpt,
            max_scenes=max_scenes,
            language=language,
            sound_effects=sound_effects,
            trending_sounds=trending_sounds,
            voiceover=voiceover_param_raw or None,
        )

        scenes = gpt_result.get("scenes", [])
        total = len(scenes)
        _update(job_id, total_scenes=total)
        logger.info("[JOB %s] %d scenes to process", job_id, total)

        completed_scenes = []
        saved_video_paths = []

        for i, scene in enumerate(scenes, 1):
            scene_num = scene["scene"]

            # ── Image generation ──────────────────────────────
            _update(job_id, step=f"Scene {i}/{total}: Generating image", completed_scenes=i - 1)
            logger.info("[JOB %s] Scene %d/%d — generating image", job_id, i, total)

            image_url = generate_image(
                scene["image_prompt"],
                chat_id=chat_id_image,
                image_style=image_style,
                negative_prompt=negative_prompt,
            )

            logger.info("[JOB %s] Scene %d — saving image", job_id, i)
            local_image_path = save_image(image_url, job_id, scene_num)
            image_local_url = f"/api/files/images/{os.path.basename(local_image_path)}"

            # ── Video generation ──────────────────────────────
            _update(job_id, step=f"Scene {i}/{total}: Generating video")
            logger.info("[JOB %s] Scene %d/%d — generating video", job_id, i, total)
            video_url = None
            try:
                video_url = generate_video(
                    image_url=image_url,
                    video_prompt=scene["video_prompt"],
                    chat_id=chat_id_video or chat_id_image or "6a0ed42f-ecb0-8324-a176-6954e97a9a44",
                    aspect_ratio=aspect_ratio,
                    video_length=video_length,
                    resolution=resolution,
                    preset=preset,
                    motion_strength=motion_strength,
                    seed=seed,
                    loop=loop,
                    negative_video_prompt=negative_video_prompt,
                )
                _update(job_id, step=f"Scene {i}/{total}: Saving video")
                logger.info("[JOB %s] Scene %d — downloading & saving video", job_id, i)
                local_video_path = save_video(video_url, job_id, scene_num)
            except Exception as vid_err:
                logger.warning("[JOB %s] Scene %d video failed: %s — using Ken Burns static clip", job_id, i, vid_err)
                _update(job_id, step=f"Scene {i}/{total}: Video failed — animated static clip")
                local_video_path = _make_static_clip(local_image_path, job_id, scene_num)

            video_local_url = f"/api/files/videos/{os.path.basename(local_video_path)}"

            # ── Sound effect ──────────────────────────────────
            sound_name = scene.get("sound_effect", "") or ""
            sound_name = sound_name.strip() if isinstance(sound_name, str) else ""
            if sound_effects and sound_name and sound_name.lower() not in ("null", "none", ""):
                _update(job_id, step=f"Scene {i}/{total}: Mixing sound effect")
                logger.info("[JOB %s] Scene %d — applying sound '%s'", job_id, i, sound_name)
                sound_out = local_video_path.replace(".mp4", "_sfx.mp4")
                final_clip_path = apply_sound_to_clip(
                    clip_path=local_video_path,
                    sound_name=sound_name,
                    output_path=sound_out,
                )
            else:
                final_clip_path = local_video_path

            saved_video_paths.append(final_clip_path)

            scene_result = {
                "scene": scene_num,
                "image_prompt": scene["image_prompt"],
                "video_prompt": scene["video_prompt"],
                "sound_effect": sound_name or None,
                "image_url": image_url,
                "image_local_url": image_local_url,
                "video_url": video_url,
                "video_local_url": video_local_url,
            }
            completed_scenes.append(scene_result)
            _update(job_id, scenes=list(completed_scenes), completed_scenes=i)

        if not saved_video_paths:
            raise RuntimeError("All scene video generations failed — no video to combine.")

        skipped = total - len(saved_video_paths)
        step_msg = (
            f"Combining {len(saved_video_paths)}/{total} videos"
            + (f" ({skipped} scene(s) skipped)" if skipped else "")
        )
        _update(job_id, status="combining", step=step_msg)
        logger.info("[JOB %s] %s", job_id, step_msg)

        final_path = combine_videos(
            video_paths=saved_video_paths,
            job_id=job_id,
            background_music_url=background_music,
            music_volume=music_volume,
            music_fade_in=music_fade_in,
            music_fade_out=music_fade_out,
            fade=bool(fade),
            fade_duration=fade_duration,
            video_speed=video_speed,
            transition=transition,
            fps=fps,
            watermark_text=watermark_text,
            mute_original_audio=mute_original_audio,
            intro_text=intro_text,
            outro_text=outro_text,
            bg_color=bg_color,
        )

        # ── Trim silence (optional) ───────────────────────────
        if trim_silence_opt:
            from silence_trimmer import trim_silence
            _update(job_id, status="combining", step="Trimming silence from final video")
            logger.info("[JOB %s] Trimming silence from final video", job_id)
            trimmed_path = final_path.replace("_final.mp4", "_trimmed.mp4")
            final_path = trim_silence(final_path, trimmed_path)

        final_url = f"/api/files/final/{os.path.basename(final_path)}"

        extra = {}
        if voiceover_text:
            extra["voiceover_transcript"] = voiceover_text

        _update(
            job_id,
            status="completed",
            step="Done",
            completed_scenes=total,
            title=gpt_result.get("title", "Generated Story"),
            final_video_url=final_url,
            finished_at=datetime.utcnow().isoformat(),
            **extra,
        )
        logger.info("[JOB %s] Completed. Final video: %s", job_id, final_url)

    except Exception as e:
        logger.error("[JOB %s] Failed: %s", job_id, e)
        _update(
            job_id,
            status="failed",
            step="Failed",
            error=str(e),
            finished_at=datetime.utcnow().isoformat(),
        )


def start_job(job_id: str):
    t = threading.Thread(target=run_job, args=(job_id,), daemon=True)
    t.start()
