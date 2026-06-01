import glob
import logging
import os
import re
import subprocess
import tempfile

logger = logging.getLogger(__name__)

SUPPORTED_DOMAINS = (
    "youtube.com", "youtu.be",
    "facebook.com", "fb.watch",
    "instagram.com", "tiktok.com",
)


def is_supported_url(url: str) -> bool:
    return any(d in url.lower() for d in SUPPORTED_DOMAINS)


def extract_voiceover(url: str) -> str | None:
    """Extract transcript/voiceover from a social media URL using yt-dlp."""
    if not is_supported_url(url):
        logger.warning("extract_voiceover: unsupported URL domain: %s", url)
        return None

    with tempfile.TemporaryDirectory() as tmpdir:
        out_tmpl = os.path.join(tmpdir, "transcript")

        # Try auto-generated subtitles first
        subprocess.run(
            [
                "yt-dlp",
                "--skip-download",
                "--write-auto-sub",
                "--write-sub",
                "--sub-lang", "en,en-US,en-GB",
                "--convert-subs", "srt",
                "--no-playlist",
                "-o", out_tmpl,
                url,
            ],
            capture_output=True, text=True, timeout=60,
        )

        srt_files = glob.glob(os.path.join(tmpdir, "*.srt"))
        if srt_files:
            with open(srt_files[0], encoding="utf-8", errors="ignore") as f:
                raw = f.read()
            transcript = _parse_srt(raw)
            if transcript:
                logger.info("extract_voiceover: got %d chars from subtitles", len(transcript))
                return transcript

        # Fallback: try description / metadata
        desc_result = subprocess.run(
            [
                "yt-dlp", "--skip-download",
                "--print", "description",
                "--no-playlist",
                url,
            ],
            capture_output=True, text=True, timeout=30,
        )
        desc = desc_result.stdout.strip()
        if desc and len(desc) > 20:
            logger.info("extract_voiceover: using video description (%d chars)", len(desc))
            return f"[Video description]\n{desc}"

        logger.warning("extract_voiceover: no transcript found for %s", url)
        return None


def _parse_srt(raw: str) -> str:
    """Strip SRT timestamps and return plain text transcript."""
    lines = raw.splitlines()
    text_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if re.match(r"^\d+$", line):
            continue
        if re.match(r"^\d{2}:\d{2}:\d{2}", line):
            continue
        # Remove HTML tags like <i>, <b>, etc.
        line = re.sub(r"<[^>]+>", "", line)
        if line:
            text_lines.append(line)
    return " ".join(text_lines)
