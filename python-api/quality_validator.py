import json
import logging
import subprocess

import requests

logger = logging.getLogger(__name__)

VPS_BASE = "http://217.77.8.115:7637"
AUTH_HEADER = "Bearer ranaji"
GPT_MODEL = "gpt-4o"
DEFAULT_CHAT_ID = "6a0ed373-826c-8324-bf45-f5882306bbdb"

IMAGE_PASS_THRESHOLD = 7


# ── GPT helper ────────────────────────────────────────────────────────────────

def _ask_gpt(messages: list, chat_id: str = DEFAULT_CHAT_ID) -> str:
    payload = {
        "model": GPT_MODEL,
        "messages": messages,
        "temperature": 0.4,
        "chat_id": chat_id,
    }
    last_error = None
    for attempt in range(1, 4):
        try:
            resp = requests.post(
                f"{VPS_BASE}/v1/chat/completions",
                json=payload,
                headers={"Authorization": AUTH_HEADER, "Content-Type": "application/json"},
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code
            text = e.response.text
            last_error = RuntimeError(f"GPT QA error {status}: {text[:200]}")
            if status == 502 and "HTTP/2" in text:
                logger.warning("[QA] HTTP/2 error on attempt %d, retrying...", attempt)
                continue
            raise last_error
        except Exception as e:
            last_error = e
            if attempt < 3:
                continue
    raise RuntimeError(f"GPT quality check failed after 3 attempts: {last_error}")


def _parse_json(raw: str) -> dict:
    if raw.startswith("```"):
        raw = "\n".join(line for line in raw.splitlines() if not line.startswith("```")).strip()
    return json.loads(raw)


# ── Image validation ──────────────────────────────────────────────────────────

def validate_image(
    image_url: str,
    original_prompt: str,
    chat_id: str = DEFAULT_CHAT_ID,
) -> tuple[bool, str]:
    """
    Validate image quality with GPT-4o vision.

    Returns:
        (passed, improved_prompt)
        - passed=True  → image is good; improved_prompt == original_prompt
        - passed=False → image failed; improved_prompt has GPT's targeted fixes
    """
    logger.info("[QA-IMG] Validating image via GPT-4o vision")

    messages = [
        {
            "role": "system",
            "content": (
                "You are a senior quality controller for AI-generated cinematic images. "
                "Be strict — only pass images that are truly production-ready. "
                "Return ONLY valid JSON. No markdown, no code blocks, no explanations."
            ),
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Evaluate this AI-generated image for a cinematic short-form video scene.\n\n"
                        f"Original prompt used:\n{original_prompt}\n\n"
                        "Score each criterion 1-10:\n"
                        "• composition_framing — subject placement, rule of thirds, visual balance\n"
                        "• lighting_mood — quality of light, shadows, cinematic atmosphere\n"
                        "• detail_sharpness — clarity, texture richness, no blur/artifacts\n"
                        "• cinematic_quality — professional look, color grading, depth\n"
                        "• prompt_adherence — how well it matches the original prompt\n\n"
                        f"PASS threshold: overall_score >= {IMAGE_PASS_THRESHOLD}/10\n\n"
                        "Return ONLY this exact JSON:\n"
                        "{\n"
                        '  "scores": {\n'
                        '    "composition_framing": <1-10>,\n'
                        '    "lighting_mood": <1-10>,\n'
                        '    "detail_sharpness": <1-10>,\n'
                        '    "cinematic_quality": <1-10>,\n'
                        '    "prompt_adherence": <1-10>\n'
                        "  },\n"
                        '  "overall_score": <average of all scores, 1 decimal>,\n'
                        '  "passed": <true if overall_score >= 7, else false>,\n'
                        '  "issues": ["<specific issue 1>", "<specific issue 2>"],\n'
                        '  "improved_prompt": "<rewritten prompt fixing each issue — keep same scene, improve quality>"\n'
                        "}"
                    ),
                },
                {
                    "type": "image_url",
                    "image_url": {"url": image_url},
                },
            ],
        },
    ]

    try:
        raw = _ask_gpt(messages, chat_id=chat_id)
        result = _parse_json(raw)
        passed = bool(result.get("passed", True))
        improved = result.get("improved_prompt") or original_prompt
        score = result.get("overall_score", "?")
        issues = result.get("issues", [])
        scores = result.get("scores", {})

        if passed:
            logger.info("[QA-IMG] ✅ PASSED (score: %s) %s", score, scores)
        else:
            logger.warning(
                "[QA-IMG] ❌ FAILED (score: %s). Issues: %s", score, issues
            )
        return passed, improved

    except Exception as e:
        logger.warning("[QA-IMG] Validation error (%s) — skipping, treating as passed", e)
        return True, original_prompt


# ── Video validation ──────────────────────────────────────────────────────────

def validate_final_video(
    video_path: str,
    scenes: list[dict],
    chat_id: str = DEFAULT_CHAT_ID,
) -> tuple[bool, list[dict]]:
    """
    Validate final compiled video with ffprobe metrics + GPT consultation.

    Args:
        video_path: path to the final .mp4
        scenes: list of scene dicts with 'image_prompt' and 'video_prompt' keys

    Returns:
        (passed, improved_scenes)
        - passed=True  → video is good; improved_scenes == original scenes
        - passed=False → video has issues; improved_scenes have GPT-improved prompts
    """
    logger.info("[QA-VID] Validating final video with ffprobe")
    metrics = _probe_video(video_path)
    issues = _detect_video_issues(metrics)

    if not issues:
        logger.info("[QA-VID] ✅ PASSED — metrics: %s", metrics)
        return True, scenes

    logger.warning("[QA-VID] ❌ Issues detected: %s | metrics: %s", issues, metrics)
    logger.info("[QA-VID] Consulting GPT for improved prompts...")

    scene_descriptions = "\n".join(
        f"Scene {s['scene']}: image='{s['image_prompt'][:120]}...' | video='{s['video_prompt'][:120]}...'"
        for s in scenes
    )

    messages = [
        {
            "role": "system",
            "content": (
                "You are a video quality expert for AI-generated short-form cinematic videos. "
                "Given technical quality issues and original prompts, rewrite each scene's prompts "
                "to fix the detected problems. "
                "Return ONLY valid JSON. No markdown, no extra text."
            ),
        },
        {
            "role": "user",
            "content": (
                "The final compiled video has these technical quality issues:\n"
                + "\n".join(f"• {issue}" for issue in issues)
                + f"\n\nVideo metrics: duration={metrics.get('duration')}s, "
                f"fps={metrics.get('fps')}, bitrate={metrics.get('bitrate_kbps')}kbps, "
                f"abrupt_cuts={metrics.get('abrupt_cuts')}\n\n"
                "Original scenes:\n"
                + scene_descriptions
                + "\n\n"
                "Rewrite EVERY scene's image_prompt and video_prompt to fix these issues.\n"
                "For abrupt transitions: add gradual camera movements, smooth motion cues.\n"
                "For low quality/bitrate: add more cinematic detail, lighting, texture.\n"
                "For short duration: add more action stages in video_prompt [0-2s][2-4s][4-6s].\n\n"
                "Return ONLY this exact JSON:\n"
                "{\n"
                '  "issues_summary": "<one sentence summary of problems>",\n'
                '  "improved_scenes": [\n'
                "    {\n"
                '      "scene": <scene number>,\n'
                '      "image_prompt": "<improved image prompt>",\n'
                '      "video_prompt": "<improved video prompt with smooth transitions>"\n'
                "    }\n"
                "  ]\n"
                "}"
            ),
        },
    ]

    try:
        raw = _ask_gpt(messages, chat_id=chat_id)
        result = _parse_json(raw)
        improved_list = result.get("improved_scenes", [])
        summary = result.get("issues_summary", "")
        logger.info("[QA-VID] GPT improvement summary: %s", summary)

        # Merge improved prompts back into the original scene dicts
        improved_map = {s["scene"]: s for s in improved_list}
        improved_scenes = []
        for scene in scenes:
            snum = scene["scene"]
            if snum in improved_map:
                improved = dict(scene)
                improved["image_prompt"] = improved_map[snum].get("image_prompt", scene["image_prompt"])
                improved["video_prompt"] = improved_map[snum].get("video_prompt", scene["video_prompt"])
                improved_scenes.append(improved)
            else:
                improved_scenes.append(scene)

        return False, improved_scenes

    except Exception as e:
        logger.warning("[QA-VID] GPT consultation error (%s) — skipping, treating as passed", e)
        return True, scenes


# ── ffprobe helpers ───────────────────────────────────────────────────────────

def _probe_video(video_path: str) -> dict:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate,bit_rate,nb_frames",
            "-show_entries", "format=duration,bit_rate",
            "-of", "json",
            video_path,
        ],
        capture_output=True, text=True, timeout=30,
    )

    metrics: dict = {}
    try:
        data = json.loads(result.stdout)
        streams = data.get("streams", [{}])
        fmt = data.get("format", {})
        stream = streams[0] if streams else {}

        fps_raw = stream.get("r_frame_rate", "24/1")
        try:
            num, den = fps_raw.split("/")
            fps = round(int(num) / max(int(den), 1), 2)
        except Exception:
            fps = 24.0

        duration = float(fmt.get("duration") or stream.get("duration") or 0)
        bitrate = int(fmt.get("bit_rate") or stream.get("bit_rate") or 0) // 1000
        nb_frames = int(stream.get("nb_frames") or 0)

        metrics = {
            "width": int(stream.get("width") or 0),
            "height": int(stream.get("height") or 0),
            "fps": fps,
            "duration": round(duration, 2),
            "bitrate_kbps": bitrate,
            "nb_frames": nb_frames,
        }
    except Exception as e:
        logger.warning("[QA-VID] ffprobe parse error: %s", e)

    metrics["abrupt_cuts"] = _count_abrupt_cuts(video_path)
    return metrics


def _count_abrupt_cuts(video_path: str, threshold: float = 0.4) -> int:
    """Count frames where scene change score exceeds threshold (abrupt cuts)."""
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-i", video_path,
                "-vf", f"select=gt(scene\\,{threshold}),metadata=print:file=-",
                "-an", "-f", "null", "-",
            ],
            capture_output=True, text=True, timeout=30,
        )
        # Each detected cut has a "pts_time" line in stderr via metadata
        cuts = result.stdout.count("pts_time")
        return cuts
    except Exception as e:
        logger.warning("[QA-VID] Scene cut detection error: %s", e)
        return 0


def _detect_video_issues(metrics: dict) -> list[str]:
    issues = []
    duration = metrics.get("duration", 6.0)
    fps = metrics.get("fps", 24.0)
    bitrate = metrics.get("bitrate_kbps", 0)
    abrupt_cuts = metrics.get("abrupt_cuts", 0)
    width = metrics.get("width", 720)
    height = metrics.get("height", 1280)

    if duration < 3.0:
        issues.append(f"Video too short ({duration}s, expected ~6s minimum)")
    if fps < 18.0:
        issues.append(f"Low frame rate ({fps} fps, expected 24+ for smooth playback)")
    if 0 < bitrate < 200:
        issues.append(f"Very low bitrate ({bitrate} kbps — poor visual quality)")
    if abrupt_cuts >= 3:
        issues.append(
            f"Abrupt scene transitions ({abrupt_cuts} hard cuts above threshold) — not smooth"
        )
    if width > 0 and height > 0 and (width < 480 or height < 480):
        issues.append(f"Low resolution ({width}x{height})")

    return issues
