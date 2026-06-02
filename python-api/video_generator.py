import json
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

    # Use a fresh UUID per request — grok2api requires unique chat_id per video
    import uuid
    fresh_chat_id = str(uuid.uuid4())

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
        "video_config": {
            "aspect_ratio": aspect_ratio,
            "video_length": video_length,
            "resolution_name": resolution,
            "preset": preset,
        },
        "chat_id": fresh_chat_id,
        "stream": True,   # stream=True to avoid 60s idle timeout on server
    }

    last_error = None
    for attempt in range(1, 6):
        try:
            video_url = _stream_video(payload, attempt)
            if video_url:
                return video_url
            last_error = RuntimeError(f"No video URL in streamed response")

        except requests.exceptions.Timeout:
            last_error = RuntimeError("Video generation timeout")
        except requests.exceptions.ConnectionError:
            last_error = RuntimeError("VPS unavailable for video generation")
        except requests.exceptions.HTTPError as e:
            last_error = RuntimeError(
                f"Video generation HTTP error: {e.response.status_code} {e.response.text[:200]}"
            )

        if attempt < 5:
            # Refresh chat_id on each retry
            payload["chat_id"] = str(uuid.uuid4())
            wait = attempt * 5
            logger.warning(
                "Video generation attempt %d/5 failed: %s — retrying in %ds",
                attempt, last_error, wait,
            )
            time.sleep(wait)

    raise last_error


def _stream_video(payload: dict, attempt: int) -> str | None:
    """
    Send streaming request to grok2api VPS and parse SSE chunks.
    Returns the first video URL found in the stream, or None.
    The stream can run for up to 5 minutes (video generation takes ~2-3 min).
    """
    url_patterns = [
        r'https?://[^\s\)\]"\'>]+\.mp4[^\s\)\]"\'>]*',
        r'http://[^\s\)\]"\'>]+:8885/v1/files/video[^\s\)\]"\'>]*',
        r'https?://[^\s\)\]"\'>]+/v1/files/video[^\s\)\]"\'>]*',
        r'https?://assets\.grok\.com/[^\s\)\]"\'>]+',
    ]

    with requests.post(
        f"{VIDEO_BASE}/v1/chat/completions",
        headers={"Authorization": AUTH_HEADER, "Content-Type": "application/json"},
        json=payload,
        timeout=(15, 360),   # (connect timeout, read timeout) — 6 min read
        stream=True,
    ) as resp:
        resp.raise_for_status()

        accumulated = ""
        chunk_count = 0

        for raw_line in resp.iter_lines(decode_unicode=True):
            if not raw_line:
                continue

            # SSE lines: "data: {...}" or "data: [DONE]"
            line = raw_line.strip()
            if not line.startswith("data:"):
                continue

            data_str = line[5:].strip()
            if data_str == "[DONE]":
                break

            try:
                chunk = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            chunk_count += 1

            # Check for upstream error in SSE
            if "error" in chunk:
                err_msg = chunk["error"].get("message", str(chunk["error"]))
                logger.warning(
                    "Video attempt %d SSE error: %s", attempt, err_msg
                )
                return None

            # Extract delta content
            choices = chunk.get("choices", [])
            if not choices:
                continue

            delta = choices[0].get("delta", {})
            content_piece = delta.get("content", "")
            if content_piece:
                accumulated += content_piece

            finish = choices[0].get("finish_reason")

            # Log progress tokens (contain Chinese progress text or video URL)
            if content_piece:
                logger.info(
                    "Video attempt %d chunk #%d: %s",
                    attempt, chunk_count, content_piece[:120],
                )

            # Check accumulated content for video URL
            for pattern in url_patterns:
                urls = re.findall(pattern, accumulated)
                if urls:
                    video_url = urls[0]
                    logger.info(
                        "Video attempt %d: URL found after %d chunks: %s",
                        attempt, chunk_count, video_url,
                    )
                    return video_url

            if finish == "stop":
                break

        logger.info(
            "Video attempt %d stream ended — %d chunks, accumulated: %s",
            attempt, chunk_count, accumulated[:300],
        )

        # Final check on accumulated content
        for pattern in url_patterns:
            urls = re.findall(pattern, accumulated)
            if urls:
                return urls[0]

        return None
