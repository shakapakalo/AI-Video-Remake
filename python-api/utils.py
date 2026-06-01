import re
import logging

logger = logging.getLogger(__name__)


def is_valid_youtube_shorts_url(url: str) -> bool:
    patterns = [
        r"https?://(www\.)?youtube\.com/shorts/[\w-]+",
        r"https?://youtu\.be/[\w-]+",
        r"https?://(www\.)?youtube\.com/watch\?v=[\w-]+",
    ]
    return any(re.match(p, url) for p in patterns)


def validate_scenes(scenes: list) -> tuple[bool, str]:
    required_fields = {"scene", "image_prompt", "video_prompt"}
    for i, scene in enumerate(scenes):
        missing = required_fields - set(scene.keys())
        if missing:
            return False, f"Scene {i + 1} missing fields: {missing}"
        if not str(scene.get("image_prompt", "")).strip():
            return False, f"Scene {i + 1} has empty image_prompt"
        if not str(scene.get("video_prompt", "")).strip():
            return False, f"Scene {i + 1} has empty video_prompt"
    return True, ""


def error_response(message: str, status_code: int = 400) -> tuple[dict, int]:
    logger.error("Error response: %s", message)
    return {"success": False, "error": message}, status_code
