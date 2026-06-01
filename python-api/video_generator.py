import logging
import re
import time
import requests

logger = logging.getLogger(__name__)

VIDEO_BASE = "http://217.77.8.115:8885"
DEFAULT_CHAT_ID = "6a0ed42f-ecb0-8324-a176-6954e97a9a44"
AUTH_HEADER = "Bearer ranaji"


def generate_video(
    image_url: str,
    video_prompt: str,
    chat_id: str = DEFAULT_CHAT_ID,
    aspect_ratio: str = "9:16",
    video_length: int = 6,
    resolution: str = "720p",
    preset: str = "normal",
    motion_strength: float | None = None,
    seed: int | None = None,
    loop: bool = False,
    negative_video_prompt: str | None = None,
) -> str:
    prompt_text = video_prompt or "animate this image smoothly"
    if negative_video_prompt:
        prompt_text += f". Avoid: {negative_video_prompt}"

    video_config: dict = {
        "aspect_ratio": aspect_ratio,
        "video_length": video_length,
        "resolution_name": resolution,
        "preset": preset,
    }
    if motion_strength is not None:
        video_config["motion_strength"] = float(motion_strength)
    if seed is not None:
        video_config["seed"] = int(seed)
    if loop:
        video_config["loop"] = True

    payload = {
        "model": "grok-imagine-1.0-video",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": prompt_text},
                ],
            }
        ],
        "video_config": video_config,
        "chat_id": chat_id,
        "stream": False,
    }

    last_error = None
    for attempt in range(1, 6):
        try:
            response = requests.post(
                f"{VIDEO_BASE}/v1/chat/completions",
                headers={"Authorization": AUTH_HEADER, "Content-Type": "application/json"},
                json=payload,
                timeout=600,
            )
            response.raise_for_status()

            data = response.json()
            content = data["choices"][0]["message"]["content"]
            logger.info("Video API response (attempt %d): %s", attempt, content[:200])

            patterns = [
                r'https?://[^\s\)\]"\'>]+\.mp4[^\s\)\]"\'>]*',
                r'http://[^\s\)\]"\'>]+:8885/v1/files/video[^\s\)\]"\'>]*',
                r'https?://[^\s\)\]"\'>]+/v1/files/video[^\s\)\]"\'>]*',
            ]
            for pattern in patterns:
                urls = re.findall(pattern, content)
                if urls:
                    return urls[0]

            last_error = RuntimeError(f"No video URL found in response: {content[:300]}")

        except requests.exceptions.Timeout:
            last_error = RuntimeError("Video generation timeout after 600 seconds")
        except requests.exceptions.ConnectionError:
            last_error = RuntimeError("VPS unavailable for video generation")
        except requests.exceptions.HTTPError as e:
            last_error = RuntimeError(f"Video generation HTTP error: {e.response.status_code} {e.response.text[:200]}")

        if attempt < 5:
            wait = attempt * 5
            logger.warning("Video generation attempt %d/5 failed: %s — retrying in %ds", attempt, last_error, wait)
            time.sleep(wait)

    raise last_error
