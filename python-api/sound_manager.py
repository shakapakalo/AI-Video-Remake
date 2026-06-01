import logging
import os
import subprocess

logger = logging.getLogger(__name__)

SOUNDS_DIR = os.path.join(os.path.dirname(__file__), "storage", "sounds")
TRENDING_DIR = os.path.join(SOUNDS_DIR, "trending")

TRENDING_CATALOG = [
    {
        "name": "vine_boom",
        "description": "Deep bass boom — viral punchline, dramatic reveal, meme impact moment",
        "cmd": ["ffmpeg","-y","-f","lavfi","-i",
                "aevalsrc=0.9*sin(2*PI*55*t)*exp(-t*2):s=44100:d=1.2",
                "-af","bass=g=20,volume=3", f"{TRENDING_DIR}/vine_boom.mp3"],
    },
    {
        "name": "tiktok_ding",
        "description": "Bright TikTok-style notification ding — quick reward, win, positive surprise",
        "cmd": ["ffmpeg","-y","-f","lavfi",
                "-i","aevalsrc=(sin(2*PI*1500*t)+sin(2*PI*2250*t))*exp(-t*5):s=44100:d=0.6",
                f"{TRENDING_DIR}/tiktok_ding.mp3"],
    },
    {
        "name": "oh_no",
        "description": "Sad descending slide — epic fail, disaster incoming, character doomed",
        "cmd": ["ffmpeg","-y","-f","lavfi",
                "-i","aevalsrc=0.7*sin(2*PI*(900-400*t)*t):s=44100:d=1.8",
                "-af","afade=t=out:st=1.3:d=0.5",
                f"{TRENDING_DIR}/oh_no.mp3"],
    },
    {
        "name": "rizz_whoosh",
        "description": "Smooth rising swoosh — cool entrance, level up, character arriving stylishly",
        "cmd": ["ffmpeg","-y","-f","lavfi",
                "-i","aevalsrc=0.6*sin(2*PI*(200+600*t)*t):s=44100:d=1.2",
                "-af","afade=t=out:st=0.9:d=0.3",
                f"{TRENDING_DIR}/rizz_whoosh.mp3"],
    },
    {
        "name": "brain_blast",
        "description": "Heavy low-frequency impact — mind blown, realization, massive explosion",
        "cmd": ["ffmpeg","-y","-f","lavfi",
                "-i","anoisesrc=r=44100:color=white:d=0.8",
                "-af","lowpass=f=80,volume=6,afade=t=out:st=0.2:d=0.6",
                f"{TRENDING_DIR}/brain_blast.mp3"],
    },
    {
        "name": "npc_bleep",
        "description": "Robotic bleep — NPC talking, glitch moment, game-style interaction",
        "cmd": ["ffmpeg","-y","-f","lavfi",
                "-i","aevalsrc=0.5*(sin(2*PI*440*t)+sin(2*PI*880*t))*sin(2*PI*12*t):s=44100:d=0.5",
                f"{TRENDING_DIR}/npc_bleep.mp3"],
    },
    {
        "name": "sigma_hit",
        "description": "Sharp punchy hit — motivational moment, grindset reveal, alpha move",
        "cmd": ["ffmpeg","-y","-f","lavfi",
                "-i","anoisesrc=r=44100:color=white:d=0.4",
                "-af","bandpass=f=200:w=100,volume=5,afade=t=out:st=0.05:d=0.35",
                f"{TRENDING_DIR}/sigma_hit.mp3"],
    },
    {
        "name": "airhorn",
        "description": "Party airhorn — celebration, hype moment, big win, crowd going wild",
        "cmd": ["ffmpeg","-y","-f","lavfi",
                "-i","aevalsrc=0.7*(sin(2*PI*233*t)+0.5*sin(2*PI*311*t)+0.3*sin(2*PI*466*t)):s=44100:d=1.5",
                "-af","afade=t=out:st=1.0:d=0.5",
                f"{TRENDING_DIR}/airhorn.mp3"],
    },
    {
        "name": "cash_register",
        "description": "Money cha-ching — making money, deal closed, greedy character scores",
        "cmd": ["ffmpeg","-y","-f","lavfi",
                "-i","aevalsrc=(sin(2*PI*1800*t)+sin(2*PI*2400*t))*exp(-t*3):s=44100:d=0.7",
                f"{TRENDING_DIR}/cash_register.mp3"],
    },
    {
        "name": "game_over",
        "description": "Descending game-over melody — character loses, fails mission, total defeat",
        "cmd": ["ffmpeg","-y","-f","lavfi",
                "-i","aevalsrc=0.5*(sin(2*PI*392*t)+sin(2*PI*330*t)+sin(2*PI*262*t))*exp(-t*1):s=44100:d=2.0",
                "-af","afade=t=out:st=1.5:d=0.5",
                f"{TRENDING_DIR}/game_over.mp3"],
    },
]

CATALOG = [
    {
        "name": "cartoon_boing",
        "description": "Springy boing — character bounces, jumps, spring launches, silly fall landing",
    },
    {
        "name": "whoosh",
        "description": "Fast whoosh — something flies past, quick dash, object thrown through air",
    },
    {
        "name": "pop",
        "description": "Bubble pop — balloon pops, bubble bursts, small magic effect, cork pops",
    },
    {
        "name": "cartoon_punch",
        "description": "Cartoon punch — hit, smack, slap, impact between characters",
    },
    {
        "name": "slide_whistle_down",
        "description": "Slide whistle falling — character or object falls down, fails, deflates, shrinks",
    },
    {
        "name": "slide_whistle_up",
        "description": "Slide whistle rising — character zooms up, levitates, something grows or inflates",
    },
    {
        "name": "glass_break",
        "description": "Glass shattering — anything breaks, crashes, smashes into pieces",
    },
    {
        "name": "sad_trombone",
        "description": "Wah wah sad trombone — epic fail, loss, disappointment, defeat",
    },
    {
        "name": "coin",
        "description": "Coin ding — reward, achievement, something good/shiny appears, success",
    },
    {
        "name": "rubber_squeak",
        "description": "Rubber squeak — silly toy sound, cute moment, accidental bump, small creature",
    },
    {
        "name": "cartoon_explosion",
        "description": "Cartoon explosion — big boom, dramatic impact, something explodes or blows up",
    },
    {
        "name": "laugh_track",
        "description": "Audience laughter — very funny moment, punchline, ridiculous situation",
    },
    {
        "name": "splat",
        "description": "Wet splat — falls into mud/water/food, messy collision, fruit smashing",
    },
    {
        "name": "surprise",
        "description": "Surprise sting — sudden reveal, unexpected appearance, shocking discovery",
    },
    {
        "name": "sneaky",
        "description": "Sneaky pluck — character tiptoeing, secret plan, hiding, mischievous setup",
    },
]


def ensure_trending_sounds() -> bool:
    """Generate trending sounds if not already on disk. Returns True if any are available."""
    os.makedirs(TRENDING_DIR, exist_ok=True)
    generated = 0
    for s in TRENDING_CATALOG:
        path = os.path.join(TRENDING_DIR, f"{s['name']}.mp3")
        if not os.path.exists(path):
            result = subprocess.run(s["cmd"], capture_output=True, text=True)
            if result.returncode == 0:
                generated += 1
                logger.info("Generated trending sound: %s", s["name"])
            else:
                logger.warning("Failed to generate %s: %s", s["name"], result.stderr[-100:])
    available = len([s for s in TRENDING_CATALOG
                     if os.path.exists(os.path.join(TRENDING_DIR, f"{s['name']}.mp3"))])
    logger.info("Trending sounds available: %d/%d", available, len(TRENDING_CATALOG))
    return available > 0


def get_catalog_for_gpt(include_trending: bool = False) -> str:
    lines = ["Available sound effects (use exact name in sound_effect field):"]
    for s in CATALOG:
        lines.append(f'  "{s["name"]}" — {s["description"]}')
    if include_trending:
        lines.append("\n  [TRENDING SOUNDS — use these for viral/meme moments]:")
        for s in TRENDING_CATALOG:
            path = os.path.join(TRENDING_DIR, f"{s['name']}.mp3")
            if os.path.exists(path):
                lines.append(f'  "{s["name"]}" — {s["description"]}')
    return "\n".join(lines)


def apply_sound_to_clip(
    clip_path: str,
    sound_name: str,
    output_path: str,
    sound_volume: float = 1.2,
) -> str:
    sound_path = os.path.join(SOUNDS_DIR, f"{sound_name}.mp3")
    if not os.path.exists(sound_path):
        sound_path = os.path.join(TRENDING_DIR, f"{sound_name}.mp3")
    if not os.path.exists(sound_path):
        logger.warning("Sound '%s' not found — skipping", sound_name)
        return clip_path

    # Check if clip has audio stream
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=codec_type", "-of", "csv=p=0", clip_path],
        capture_output=True, text=True,
    )
    has_audio = bool(probe.stdout.strip())

    sound_filter = f"[1:a]volume={sound_volume:.2f},apad[sfx]"

    if has_audio:
        # Mix sound effect with existing audio at clip start
        fc = (
            f"{sound_filter};"
            f"[0:a][sfx]amix=inputs=2:duration=first:normalize=0[aout]"
        )
        audio_map = "[aout]"
    else:
        # No original audio — just use sound effect alone
        fc = f"[1:a]volume={sound_volume:.2f},apad,atrim=end={_get_duration(clip_path):.3f},asetpts=PTS-STARTPTS[aout]"
        audio_map = "[aout]"

    cmd = [
        "ffmpeg", "-y",
        "-i", clip_path,
        "-i", sound_path,
        "-filter_complex", fc,
        "-map", "0:v", "-map", audio_map,
        "-c:v", "copy", "-c:a", "aac",
        "-t", str(_get_duration(clip_path)),
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("apply_sound failed: %s", result.stderr[-200:])
        return clip_path

    logger.info("Applied sound '%s' to clip %s", sound_name, os.path.basename(clip_path))
    return output_path


def _get_duration(path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except Exception:
        return 6.0
