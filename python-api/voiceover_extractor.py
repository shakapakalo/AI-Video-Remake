import glob
import json
import logging
import os
import re
import subprocess
import tempfile
import time
import urllib.request

logger = logging.getLogger(__name__)

def _find_chromium() -> str:
    """Auto-detect chromium binary across Replit (Nix), Ubuntu/Debian, and other Linux."""
    import shutil, glob as _glob
    # 1. Standard system paths
    for candidate in ("chromium-browser", "chromium", "google-chrome", "google-chrome-stable"):
        found = shutil.which(candidate)
        if found:
            return found
    # 2. Nix store (Replit) — glob for any version
    for path in _glob.glob("/nix/store/*/bin/chromium"):
        if os.path.isfile(path):
            return path
    # 3. Playwright-installed chromium
    for path in _glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux/chrome")):
        if os.path.isfile(path):
            return path
    return "chromium-browser"   # last resort — let the OS resolve it

CHROMIUM_PATH = _find_chromium()

SUPPORTED_DOMAINS = (
    "youtube.com", "youtu.be",
    "facebook.com", "fb.watch",
    "instagram.com", "tiktok.com",
    "twitter.com", "x.com",
    "vimeo.com", "soundcloud.com",
    "reddit.com", "twitch.tv",
    "dailymotion.com", "bilibili.com",
)


def is_supported_url(url: str) -> bool:
    return any(d in url.lower() for d in SUPPORTED_DOMAINS)


def extract_voiceover(url: str) -> str | None:
    """
    Extract transcript/voiceover text from a social media or video URL.

    Strategy (in order):
      1. Evernote AI Transcribe via Playwright browser automation
      2. yt-dlp auto-generated / manual subtitles
      3. yt-dlp video description / metadata
      4. GPT-4o summary fallback via VPS
    """
    logger.info("extract_voiceover: starting for %s", url)

    # Strategy 1: Evernote AI Transcribe (Playwright)
    try:
        result = _evernote_playwright(url)
        if result and len(result.strip()) > 30:
            logger.info("extract_voiceover: Evernote success (%d chars)", len(result))
            return result.strip()
    except Exception as exc:
        logger.warning("extract_voiceover: Evernote failed: %s", exc)

    # Strategy 2: yt-dlp subtitles
    try:
        result = _ytdlp_subtitles(url)
        if result and len(result.strip()) > 30:
            logger.info("extract_voiceover: yt-dlp subtitles success (%d chars)", len(result))
            return result.strip()
    except Exception as exc:
        logger.warning("extract_voiceover: yt-dlp subtitles failed: %s", exc)

    # Strategy 3: yt-dlp description
    try:
        result = _ytdlp_description(url)
        if result and len(result.strip()) > 20:
            logger.info("extract_voiceover: yt-dlp description success (%d chars)", len(result))
            return result.strip()
    except Exception as exc:
        logger.warning("extract_voiceover: yt-dlp description failed: %s", exc)

    # Strategy 4: GPT-4o summary from URL
    try:
        result = _gpt_url_summary(url)
        if result and len(result.strip()) > 20:
            logger.info("extract_voiceover: GPT-4o summary success (%d chars)", len(result))
            return result.strip()
    except Exception as exc:
        logger.warning("extract_voiceover: GPT-4o summary failed: %s", exc)

    logger.warning("extract_voiceover: all strategies failed for %s", url)
    return None


# ---------------------------------------------------------------------------
# Strategy 1: Evernote AI Transcribe via Playwright
# ---------------------------------------------------------------------------

def _evernote_playwright(url: str) -> str | None:
    """
    Use Playwright with the nix Chromium to automate Evernote AI Transcribe.
    Navigates to the link-to-text page, submits the URL, waits for the
    transcript to appear in the DOM, and extracts it.
    """
    if not os.path.exists(CHROMIUM_PATH):
        raise RuntimeError(f"Chromium not found at {CHROMIUM_PATH}")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError("playwright not installed")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROMIUM_PATH,
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-setuid-sandbox",
                "--disable-web-security",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/138.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="America/New_York",
        )

        # Inject stealth scripts to hide headless indicators
        ctx.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
        window.chrome = { runtime: {} };
        """)

        page = ctx.new_page()
        transcript_found = {"value": None}

        # Monitor responses for the transcription API
        def on_resp(resp):
            ru = resp.url
            if "public.evernote.com/transcription/v1" in ru:
                try:
                    body = resp.json()
                    logger.debug("Evernote API %s: %s", ru.split("/")[-1], str(body)[:200])
                except Exception:
                    pass

        ctx.on("response", on_resp)

        try:
            page.goto(
                "https://evernote.com/en-us/ai-transcribe/link-to-text",
                wait_until="domcontentloaded",
                timeout=30000,
            )
        except Exception:
            page.goto(
                "https://evernote.com/ai-transcribe/link-to-text",
                wait_until="domcontentloaded",
                timeout=30000,
            )

        page.wait_for_timeout(4000)

        # Click "From link" tab
        from_link = page.locator("button").filter(has_text="From link")
        if from_link.count() > 0:
            from_link.first.click()
            page.wait_for_timeout(2000)

        # Fill URL input
        url_input = page.locator("input[type='url']").first
        url_input.click()
        url_input.type(url, delay=20)
        page.wait_for_timeout(800)

        # Click Transcribe button
        transcribe_btn = page.locator("button[data-sentry-component='ObeButton']")
        if transcribe_btn.count() == 0:
            transcribe_btn = page.locator("button").filter(has_text="Transcribe")
        transcribe_btn.first.click()

        # Poll DOM for transcript content (up to 3 minutes)
        for _ in range(36):
            page.wait_for_timeout(5000)
            try:
                body_text = page.inner_text("body")

                # Check for "See transcription" success marker
                if "see transcription" in body_text.lower() or "transcription complete" in body_text.lower():
                    # Look for the transcript content area
                    transcript_el = page.locator("[class*='transcript'], [class*='result'], [class*='content']").first
                    if transcript_el.count() > 0:
                        txt = transcript_el.inner_text()
                        if len(txt) > 50:
                            transcript_found["value"] = txt
                            break

                # Check if transcript text appears (paragraphs of text)
                lines = [l.strip() for l in body_text.split("\n") if len(l.strip()) > 40]
                # Filter out known UI chrome lines
                ui_phrases = [
                    "retrieving video", "please don't close", "uploading",
                    "transcribing", "summarizing", "by using the product",
                    "terms of service", "privacy policy", "unlimited access",
                    "what types of files", "how does evernote", "can i",
                    "does evernote", "where can i", "how can", "what if",
                    "trusted by millions", "reviews on", "transcribe image",
                    "transcribe audio", "transcribe video", "meeting note",
                    "from link", "upload", "record", "ai for enterprises",
                    "about us", "english", "login",
                ]
                content_lines = [
                    l for l in lines
                    if not any(p in l.lower() for p in ui_phrases)
                ]

                if len(content_lines) >= 5:
                    # Looks like we have actual transcript content
                    transcript_found["value"] = "\n".join(content_lines)
                    break

                # Check for error state
                if "error occurred" in body_text.lower() or "an error occurred" in body_text.lower():
                    logger.warning("Evernote: error occurred in transcription")
                    break

                # Check for state: reset (transcription timed out or failed)
                if (
                    "upload" in body_text.lower()
                    and "record" in body_text.lower()
                    and "from link" in body_text.lower()
                    and "retrieving" not in body_text.lower()
                    and "transcribing" not in body_text.lower()
                ):
                    # Page reset to initial state without success
                    logger.warning("Evernote: page reset without transcript")
                    break

            except Exception:
                pass

        ctx.close()
        browser.close()
        return transcript_found["value"]


# ---------------------------------------------------------------------------
# Strategy 2: yt-dlp subtitles
# ---------------------------------------------------------------------------

def _ytdlp_subtitles(url: str) -> str | None:
    """Download auto-generated or manual subtitles via yt-dlp."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out_tmpl = os.path.join(tmpdir, "%(id)s")

        result = subprocess.run(
            [
                "yt-dlp",
                "--skip-download",
                "--write-auto-sub",
                "--write-sub",
                "--sub-lang", "en,en-US,en-GB",
                "--convert-subs", "srt",
                "--no-playlist",
                "--no-check-certificate",
                "-o", out_tmpl,
                url,
            ],
            capture_output=True, text=True, timeout=90,
        )

        srt_files = glob.glob(os.path.join(tmpdir, "*.srt"))
        if srt_files:
            with open(srt_files[0], encoding="utf-8", errors="ignore") as f:
                raw = f.read()
            transcript = _parse_srt(raw)
            if transcript:
                return transcript

        # Also try vtt
        vtt_files = glob.glob(os.path.join(tmpdir, "*.vtt"))
        if vtt_files:
            with open(vtt_files[0], encoding="utf-8", errors="ignore") as f:
                raw = f.read()
            transcript = _parse_vtt(raw)
            if transcript:
                return transcript

    return None


# ---------------------------------------------------------------------------
# Strategy 3: yt-dlp description / metadata
# ---------------------------------------------------------------------------

def _ytdlp_description(url: str) -> str | None:
    """Extract video title + description using yt-dlp."""
    result = subprocess.run(
        [
            "yt-dlp", "--skip-download",
            "--print", "%(title)s\n%(description)s",
            "--no-playlist",
            "--no-check-certificate",
            url,
        ],
        capture_output=True, text=True, timeout=45,
    )
    text = result.stdout.strip()
    if text and len(text) > 20:
        return f"[Video content]\n{text}"
    return None


# ---------------------------------------------------------------------------
# Strategy 4: GPT-4o summary from URL
# ---------------------------------------------------------------------------

_VPS_URL = "http://217.77.8.115:7637"
_VPS_AUTH = "Bearer ranaji"


def _gpt_url_summary(url: str) -> str | None:
    """Ask GPT-4o to describe/summarize the content at the given social URL."""
    payload = json.dumps({
        "model": "gpt-4o",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an assistant that creates a voiceover script from video URLs. "
                    "Given a social media URL, write the likely spoken transcript/voiceover "
                    "text for that video based on what you know about it. "
                    "Return ONLY the spoken text, no commentary."
                ),
            },
            {
                "role": "user",
                "content": f"Please transcribe or describe the spoken content of this video: {url}",
            },
        ],
        "max_tokens": 1000,
        "chat_id": "voiceover-extract",
    }).encode()

    req = urllib.request.Request(
        f"{_VPS_URL}/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": _VPS_AUTH,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=60)
    data = json.loads(resp.read())
    content = data["choices"][0]["message"]["content"].strip()
    return content if len(content) > 20 else None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
        line = re.sub(r"<[^>]+>", "", line)
        if line:
            text_lines.append(line)
    # Deduplicate consecutive identical lines
    deduped = []
    for l in text_lines:
        if not deduped or deduped[-1] != l:
            deduped.append(l)
    return " ".join(deduped)


def _parse_vtt(raw: str) -> str:
    """Strip WebVTT format and return plain text."""
    lines = raw.splitlines()
    text_lines = []
    skip_header = True
    for line in lines:
        if skip_header and line.strip() == "":
            skip_header = False
            continue
        if skip_header:
            continue
        line = line.strip()
        if not line or line.startswith("WEBVTT") or line.startswith("NOTE"):
            continue
        if re.match(r"^\d{2}:\d{2}", line) and "-->" in line:
            continue
        if re.match(r"^\d+$", line):
            continue
        line = re.sub(r"<[^>]+>", "", line)
        if line:
            text_lines.append(line)
    deduped = []
    for l in text_lines:
        if not deduped or deduped[-1] != l:
            deduped.append(l)
    return " ".join(deduped)
