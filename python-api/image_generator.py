import logging
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

BASE = "http://217.77.8.115:7637"
CHAT_ID = "6a0ed42f-ecb0-8324-a176-6954e97a9a44"
AUTH_HEADER = "Bearer ranaji"

# Short waits — 502/timeout means VPS already burned 120s, no point waiting long
RETRY_WAITS = [2, 4, 6, 10, 15]


def generate_image(
    image_prompt: str,
    chat_id: str | None = None,
    image_style: str | None = None,
    negative_prompt: str | None = None,
) -> str:
    base = image_prompt.strip()
    if image_style:
        base = f"{image_style} style. {base}"
    if negative_prompt:
        base = f"{base} Avoid: {negative_prompt}."
    prompt_with_ratio = base + " 9:16"

    last_err = None
    for attempt in range(1, 6):
        try:
            logger.info("Image generation attempt %d/5", attempt)
            url = _call_image_api(prompt_with_ratio, chat_id=chat_id or CHAT_ID)
            if url:
                return url
        except RuntimeError as e:
            last_err = e
            if attempt < 5:
                err_str = str(e)
                wait = 1 if "502" in err_str else RETRY_WAITS[attempt - 1]
                logger.warning("Image attempt %d failed: %s — retrying in %ds", attempt, e, wait)
                time.sleep(wait)
            else:
                logger.error("Image generation failed after 5 attempts: %s", e)

    raise RuntimeError(f"Image generation failed after 5 retries: {last_err}")


def _call_image_api(prompt: str, chat_id: str = CHAT_ID) -> str | None:
    payload = {
        "model": "gpt-image-2",
        "prompt": prompt,
        "n": 1,
        "response_format": "url",
        "chat_id": chat_id,
    }
    try:
        response = requests.post(
            f"{BASE}/v1/images/generations",
            json=payload,
            headers={"Authorization": AUTH_HEADER, "Content-Type": "application/json"},
            timeout=125,
        )
        response.raise_for_status()
    except requests.exceptions.Timeout:
        raise RuntimeError("Image generation timeout: VPS did not respond within 125 seconds")
    except requests.exceptions.ConnectionError:
        raise RuntimeError("VPS unavailable: could not connect to image generation endpoint")
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code
        body = e.response.text[:300]
        if status in (400, 422):
            logger.warning("Image prompt rejected (status %d): %s", status, body)
            return None
        if status == 502:
            raise RuntimeError(f"502: VPS image queue busy/timed out — will retry")
        raise RuntimeError(f"Image generation HTTP error: {status} {body}")

    data = response.json()

    url = (
        data.get("data", [{}])[0].get("url")
        or data.get("url")
        or data.get("image_url")
        or data.get("result")
    )

    if not url:
        raise RuntimeError(f"Image URL not found in response: {list(data.keys())}")

    return url


def generate_images_for_scenes(scenes: list) -> list:
    total = len(scenes)
    logger.info("[INFO] Generating %d images in parallel", total)

    results: dict[int, dict] = {}
    errors: dict[int, str] = {}

    def _generate_one(scene: dict) -> tuple[int, str]:
        scene_num = scene["scene"]
        logger.info("[INFO] Generating image %d/%d", scene_num, total)
        image_url = generate_image(scene["image_prompt"])
        return scene_num, image_url

    with ThreadPoolExecutor(max_workers=min(total, 4)) as executor:
        futures = {executor.submit(_generate_one, scene): scene for scene in scenes}

        for future in as_completed(futures):
            scene = futures[future]
            scene_num = scene["scene"]
            try:
                _, image_url = future.result()
                results[scene_num] = {
                    "scene": scene_num,
                    "image_prompt": scene["image_prompt"],
                    "video_prompt": scene["video_prompt"],
                    "image_url": image_url,
                }
            except Exception as e:
                errors[scene_num] = str(e)
                logger.error("Scene %d failed: %s", scene_num, e)

    if errors:
        failed = ", ".join(f"scene {n}" for n in sorted(errors))
        raise RuntimeError(f"Image generation failed for: {failed} — {list(errors.values())[0]}")

    logger.info("[INFO] Image generation completed")
    return [results[scene["scene"]] for scene in scenes]
