import logging
import json
import subprocess
import tempfile
import os
import re as _re

logger = logging.getLogger(__name__)


def extract_prompt(youtube_url: str) -> str:
    logger.info("[INFO] Starting VideoToPrompt extraction")

    info = _fetch_yt_info(youtube_url)

    parts = []

    title = info.get("title", "").strip()
    if title:
        parts.append(f"Title: {title}")

    description = info.get("description", "").strip()
    if description:
        parts.append(f"Description:\n{description[:2000]}")

    chapters = info.get("chapters") or []
    if chapters:
        chapter_lines = []
        for ch in chapters:
            chapter_lines.append(
                f"  [{_fmt_time(ch.get('start_time', 0))} - {_fmt_time(ch.get('end_time', 0))}] {ch.get('title', '')}"
            )
        parts.append("Chapters:\n" + "\n".join(chapter_lines))

    tags = info.get("tags") or []
    if tags:
        parts.append("Tags: " + ", ".join(tags[:20]))

    transcript = _extract_subtitles(info)
    if transcript:
        parts.append(f"Transcript:\n{transcript[:3000]}")

    if not parts:
        raise RuntimeError("VideoToPrompt extraction failed: no content extracted from YouTube")

    combined = "\n\n".join(parts)
    logger.info("[INFO] Prompt extraction completed (%d chars)", len(combined))
    return combined


def _fmt_time(seconds: float) -> str:
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m:02d}:{s:02d}"


def _fetch_yt_info(youtube_url: str) -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:
        sub_path = os.path.join(tmpdir, "subs")
        cmd = [
            "yt-dlp",
            "--dump-json",
            "--no-download",
            "--write-auto-sub",
            "--sub-langs", "en.*",
            "--output", sub_path,
            "--quiet",
            "--no-warnings",
            youtube_url,
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0 and not result.stdout.strip():
                logger.warning("yt-dlp stderr: %s", result.stderr[:500])
                raise RuntimeError(
                    f"yt-dlp failed: {result.stderr[:300] or 'unknown error'}"
                )
            info = json.loads(result.stdout.strip())
            info["_tmpdir"] = tmpdir
            return info
        except subprocess.TimeoutExpired:
            raise RuntimeError("YouTube extraction timed out after 60 seconds")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse yt-dlp output: {e}")


def _extract_subtitles(info: dict) -> str:
    try:
        tmpdir = info.get("_tmpdir")
        if not tmpdir:
            return ""

        for fname in sorted(os.listdir(tmpdir)):
            fpath = os.path.join(tmpdir, fname)
            if not os.path.isfile(fpath):
                continue

            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                raw = f.read()

            if fname.endswith(".vtt"):
                lines = []
                for line in raw.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    if "-->" in line or line.startswith("WEBVTT") or line.isdigit():
                        continue
                    line = _re.sub(r"<[^>]+>", "", line)
                    if line:
                        lines.append(line)
                if lines:
                    return " ".join(lines)

        return ""
    except Exception as e:
        logger.warning("Subtitle extraction failed: %s", e)
        return ""
