import re
import logging

logger = logging.getLogger(__name__)

# Social / video platforms supported by yt-dlp
_SOCIAL_DOMAINS = (
    "youtube.com", "youtu.be",
    "facebook.com", "fb.watch", "web.facebook.com",
    "instagram.com",
    "tiktok.com", "vm.tiktok.com",
    "twitter.com", "x.com",
    "reddit.com",
    "twitch.tv",
    "vimeo.com",
    "dailymotion.com",
)


def is_valid_youtube_shorts_url(url: str) -> bool:
    """Legacy name kept for backward compat — now accepts any supported social URL."""
    return is_valid_social_url(url)


def is_valid_social_url(url: str) -> bool:
    """Return True if the URL belongs to a yt-dlp-supported platform."""
    lower = url.lower()
    return lower.startswith("http") and any(d in lower for d in _SOCIAL_DOMAINS)


def is_url(value: str) -> bool:
    """Return True if the string looks like an HTTP(S) URL."""
    return bool(re.match(r"https?://\S+", value.strip()))


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
