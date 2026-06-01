import json
import logging
import requests

logger = logging.getLogger(__name__)

BASE = "http://217.77.8.115:7637"
CHAT_ID = "6a0ed373-826c-8324-bf45-f5882306bbdb"
AUTH_HEADER = "Bearer ranaji"

SYSTEM_PROMPT = (
    "You are a world-class creative director specializing in short-form animated video storytelling. "
    "You analyze video content and break it into scenes with highly detailed, cinematic prompts. "
    "You must return ONLY valid JSON. No markdown, no code blocks, no explanations, no extra text."
)

USER_PROMPT_TEMPLATE = """Analyze the following video description and break it into cinematic scenes.

━━━ IMAGE PROMPT RULES ━━━
- Show the scene FROZEN exactly one second BEFORE the main action.
- Characters must be MID-BUILDUP: muscles tensed, arm raised, eyes focused — poised and ready.
- Include: character details (fur, clothing, accessories), setting details (lighting, background, colors), emotional expressions.
- NO completed actions. NO results. NO aftermath.
- Style: ultra-detailed, cinematic lighting, vivid colors, professional 3D rendering quality.
- Example: cat gripping watermelon overhead with both arms, looking down at sleeping tiger — nothing dropped yet.

━━━ VIDEO PROMPT RULES (6-SECOND ANIMATION) ━━━
Break the animation into 3 stages:
  [0-2s] Setup/buildup — slight character movement, anticipation, tension
  [2-4s] Main action — the key action happens, impact, collision, explosion
  [4-6s] Reaction/punchline — characters react with exaggerated expressions, camera settles
- Camera: specify movements (slow push-in, dramatic zoom, camera shake on impact, pan to reaction)
- Motion: use cinematic language (slow motion, smear frames, exaggerated squash and stretch)
- Expressions: describe facial reactions in detail (eyes pop out, jaw drops, fur stands up)
- Every second must have something happening — no static moments.

━━━ SOUND EFFECT RULE ━━━
Choose ONE sound from this catalog that best matches the moment the action starts:
{sound_catalog}
Pick the most fitting and funny sound for the scene's impact moment.

{voiceover_instruction}
{max_scenes_instruction}
{language_instruction}

Return ONLY this exact JSON:
{{
  "title": "<punchy, funny title>",
  "total_scenes": <number>,
  "scenes": [
    {{
      "scene": 1,
      "image_prompt": "<ultra-detailed frozen moment one second before action, cinematic quality>",
      "video_prompt": "<[0-2s] ... [2-4s] ... [4-6s] ... with camera movements and reactions>",
      "sound_effect": "<exact_sound_name_from_catalog>"
    }}
  ]
}}

Video description:
{extracted_text}"""

VOICEOVER_INSTRUCTION = """━━━ VOICEOVER RULES (VERY IMPORTANT) ━━━
A voiceover/narration script is provided below. You MUST:
- Create EXACTLY one scene per voiceover line/sentence (split by newline or punctuation).
- Each scene's image_prompt and video_prompt must VISUALLY MATCH what that voiceover line is saying.
- The animation must illustrate the words being spoken — characters, actions, and setting must reflect the voiceover text precisely.
- Do NOT invent unrelated scenes. Stay 100% true to the voiceover content.
- Number of scenes = number of voiceover lines/sentences.

Voiceover script:
{voiceover_text}"""


def process_with_gpt(
    extracted_text: str,
    chat_id: str | None = None,
    max_scenes: int | None = None,
    language: str | None = None,
    sound_effects: bool = False,
    trending_sounds: bool = False,
    voiceover: str | None = None,
) -> dict:
    from sound_manager import get_catalog_for_gpt
    logger.info("[INFO] Sending prompt to GPT (sound_effects=%s, trending=%s)", sound_effects, trending_sounds)

    max_scenes_instruction = (
        f"IMPORTANT: Generate exactly {max_scenes} scenes only. No more."
        if max_scenes else ""
    )

    language_instruction = (
        f"Write ALL scene titles, image_prompt, and video_prompt text in {language} language."
        if language else ""
    )

    payload = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": USER_PROMPT_TEMPLATE.format(
                    extracted_text=extracted_text,
                    sound_catalog=(
                        get_catalog_for_gpt(include_trending=trending_sounds)
                        if sound_effects
                        else "Sound effects are disabled — set sound_effect to null for every scene."
                    ),
                    voiceover_instruction=(
                        VOICEOVER_INSTRUCTION.format(voiceover_text=voiceover.strip())
                        if voiceover and voiceover.strip()
                        else ""
                    ),
                    max_scenes_instruction=max_scenes_instruction,
                    language_instruction=language_instruction,
                ),
            },
        ],
        "temperature": 0.7,
        "chat_id": chat_id or CHAT_ID,
    }

    last_error = None
    for attempt in range(1, 4):
        try:
            response = requests.post(
                f"{BASE}/v1/chat/completions",
                json=payload,
                headers={"Authorization": AUTH_HEADER, "Content-Type": "application/json"},
                timeout=120,
            )
            response.raise_for_status()
            break
        except requests.exceptions.Timeout:
            last_error = RuntimeError("GPT timeout: VPS did not respond within 120 seconds")
            logger.warning("[RETRY %d/3] GPT timeout, retrying...", attempt)
        except requests.exceptions.ConnectionError:
            last_error = RuntimeError("VPS unavailable: could not connect to GPT endpoint")
            logger.warning("[RETRY %d/3] Connection error, retrying...", attempt)
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code
            text = e.response.text
            last_error = RuntimeError(f"GPT HTTP error: {status} {text}")
            if status == 502 and "HTTP/2" in text:
                logger.warning("[RETRY %d/3] HTTP/2 stream error (502), retrying...", attempt)
            else:
                raise last_error
    else:
        raise last_error

    logger.info("[INFO] GPT response received")

    data = response.json()
    content = (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )

    if not content:
        raise ValueError("GPT returned empty content")

    if content.startswith("```"):
        lines = content.splitlines()
        content = "\n".join(
            line for line in lines if not line.startswith("```")
        ).strip()

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as e:
        logger.error("GPT raw response: %s", content[:500])
        raise ValueError(f"Invalid GPT JSON response: {e}")

    logger.info("[INFO] JSON validated — %d scenes", len(parsed.get("scenes", [])))
    return parsed
