import logging
import os
import shutil
import subprocess
import tempfile
import requests

logger = logging.getLogger(__name__)

STORAGE_DIR = os.path.join(os.path.dirname(__file__), "storage")


def ensure_dirs():
    for sub in ("images", "videos", "final"):
        os.makedirs(os.path.join(STORAGE_DIR, sub), exist_ok=True)


def download_file(url: str, dest_path: str) -> str:
    r = requests.get(url, timeout=120, stream=True)
    r.raise_for_status()
    with open(dest_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
    return dest_path


def save_image(url: str, job_id: str, scene_num: int) -> str:
    ensure_dirs()
    ext = url.split("?")[0].split(".")[-1] or "png"
    dest = os.path.join(STORAGE_DIR, "images", f"{job_id}_scene{scene_num}.{ext}")
    return download_file(url, dest)


def save_video(url: str, job_id: str, scene_num: int) -> str:
    ensure_dirs()
    dest = os.path.join(STORAGE_DIR, "videos", f"{job_id}_scene{scene_num}.mp4")
    return download_file(url, dest)


def combine_videos(
    video_paths: list[str],
    job_id: str,
    background_music_url: str | None = None,
    music_volume: float = 0.3,
    music_fade_in: float = 0.0,
    music_fade_out: float = 0.0,
    fade: bool = False,
    fade_duration: float = 0.5,
    video_speed: float = 1.0,
    transition: str = "none",
    fps: int = 24,
    watermark_text: str | None = None,
    mute_original_audio: bool = False,
    intro_text: str | None = None,
    outro_text: str | None = None,
    bg_color: str = "black",
) -> str:
    ensure_dirs()
    output_path = os.path.join(STORAGE_DIR, "final", f"{job_id}_final.mp4")

    with tempfile.TemporaryDirectory() as tmpdir:
        processed_clips = []

        for i, vpath in enumerate(video_paths):
            out = vpath
            # mute original audio if requested
            if mute_original_audio:
                muted = os.path.join(tmpdir, f"muted_{i:03d}.mp4")
                _mute_audio(out, muted)
                out = muted
            if video_speed != 1.0:
                sped = os.path.join(tmpdir, f"speed_{i:03d}.mp4")
                _apply_speed(out, sped, video_speed)
                out = sped
            if fade or transition == "fade":
                faded = os.path.join(tmpdir, f"faded_{i:03d}.mp4")
                _apply_fade(out, faded, fade_duration)
                out = faded
            processed_clips.append(out)

        # intro card
        if intro_text:
            intro_clip = os.path.join(tmpdir, "intro.mp4")
            _make_text_card(intro_text, intro_clip, fps=fps, bg_color=bg_color)
            processed_clips.insert(0, intro_clip)

        # outro card
        if outro_text:
            outro_clip = os.path.join(tmpdir, "outro.mp4")
            _make_text_card(outro_text, outro_clip, fps=fps, bg_color=bg_color)
            processed_clips.append(outro_clip)

        if len(processed_clips) == 1:
            merged = os.path.join(tmpdir, "merged.mp4")
            _reencode(processed_clips[0], merged, fps)
        elif transition == "crossfade" and len(processed_clips) > 1:
            merged = os.path.join(tmpdir, "merged.mp4")
            _crossfade_clips(processed_clips, merged, fade_duration, fps, tmpdir)
        else:
            list_file = os.path.join(tmpdir, "concat.txt")
            with open(list_file, "w") as f:
                for clip in processed_clips:
                    f.write(f"file '{os.path.abspath(clip)}'\n")
            merged = os.path.join(tmpdir, "merged.mp4")
            _run_ffmpeg([
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", list_file,
                "-r", str(fps),
                "-c:v", "libx264", "-c:a", "aac", "-preset", "fast",
                merged,
            ])

        pre_watermark = merged
        if watermark_text:
            pre_watermark = os.path.join(tmpdir, "watermarked.mp4")
            _apply_watermark(merged, pre_watermark, watermark_text)

        if background_music_url:
            music_path = os.path.join(tmpdir, "music.mp3")
            download_file(background_music_url, music_path)
            _mix_audio(
                pre_watermark, music_path, output_path,
                volume=music_volume,
                fade_in=music_fade_in,
                fade_out=music_fade_out,
            )
        else:
            shutil.copy(pre_watermark, output_path)

    size_kb = os.path.getsize(output_path) // 1024
    logger.info("Final video saved: %s (%d KB)", output_path, size_kb)
    return output_path


def _apply_speed(input_path: str, output_path: str, speed: float):
    audio_tempo = max(0.5, min(2.0, speed))
    video_pts = 1.0 / speed
    _run_ffmpeg([
        "ffmpeg", "-y", "-i", input_path,
        "-filter_complex",
        f"[0:v]setpts={video_pts:.4f}*PTS[v];[0:a]atempo={audio_tempo:.4f}[a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-c:a", "aac", "-preset", "fast",
        output_path,
    ])


def _apply_fade(input_path: str, output_path: str, duration: float):
    dur = _get_duration(input_path)
    fade_out_start = max(0, dur - duration)
    _run_ffmpeg([
        "ffmpeg", "-y", "-i", input_path,
        "-vf", f"fade=t=in:st=0:d={duration},fade=t=out:st={fade_out_start}:d={duration}",
        "-af", f"afade=t=in:st=0:d={duration},afade=t=out:st={fade_out_start}:d={duration}",
        "-c:v", "libx264", "-c:a", "aac", "-preset", "fast",
        output_path,
    ])


def _mix_audio(
    video_path: str,
    music_path: str,
    output_path: str,
    volume: float = 0.3,
    fade_in: float = 0.0,
    fade_out: float = 0.0,
):
    video_dur = _get_duration(video_path)

    # aloop=-1 repeats music infinitely, then trim to exact video duration
    music_filter = (
        "aloop=loop=-1:size=2147483647,"
        "asetpts=PTS-STARTPTS,"
        f"atrim=duration={video_dur:.3f},"
        "asetpts=PTS-STARTPTS,"
        f"volume={volume:.2f}"
    )
    if fade_in > 0:
        music_filter += f",afade=t=in:st=0:d={fade_in}"
    if fade_out > 0:
        fade_out_start = max(0.0, video_dur - fade_out)
        music_filter += f",afade=t=out:st={fade_out_start:.3f}:d={fade_out}"

    # Check if video has an audio stream
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=codec_type", "-of", "csv=p=0", video_path],
        capture_output=True, text=True,
    )
    has_video_audio = bool(probe.stdout.strip())

    if has_video_audio:
        fc = f"[1:a]{music_filter}[music];[0:a][music]amix=inputs=2:duration=first:normalize=0[aout]"
        audio_map = "[aout]"
    else:
        fc = f"[1:a]{music_filter}[aout]"
        audio_map = "[aout]"

    _run_ffmpeg([
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", music_path,
        "-filter_complex", fc,
        "-map", "0:v", "-map", audio_map,
        "-c:v", "copy", "-c:a", "aac",
        "-t", str(video_dur),
        output_path,
    ])


def _get_duration(video_path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", video_path],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except Exception:
        return 10.0


def _mute_audio(input_path: str, output_path: str):
    _run_ffmpeg([
        "ffmpeg", "-y", "-i", input_path,
        "-an",
        "-c:v", "copy",
        output_path,
    ])


def _make_text_card(text: str, output_path: str, fps: int = 24, duration: float = 2.0, bg_color: str = "black"):
    safe_text = text.replace("'", "\\'").replace(":", "\\:")
    _run_ffmpeg([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c={bg_color}:size=720x1280:rate={fps}:duration={duration}",
        "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo",
        "-vf",
        f"drawtext=text='{safe_text}':fontsize=48:fontcolor=white"
        f":x=(w-text_w)/2:y=(h-text_h)/2:shadowcolor=black:shadowx=2:shadowy=2",
        "-c:v", "libx264", "-c:a", "aac", "-preset", "fast",
        "-t", str(duration),
        output_path,
    ])


def _get_resolution(video_path: str) -> tuple[int, int]:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height",
         "-of", "csv=p=0", video_path],
        capture_output=True, text=True,
    )
    try:
        w, h = result.stdout.strip().split(",")
        return int(w), int(h)
    except Exception:
        return 720, 1280


def _reencode(input_path: str, output_path: str, fps: int, width: int | None = None, height: int | None = None):
    vf = f"fps={fps},format=yuv420p"
    if width and height:
        vf = f"scale={width}:{height}:force_original_aspect_ratio=disable,{vf}"
    _run_ffmpeg([
        "ffmpeg", "-y", "-i", input_path,
        "-vf", vf,
        "-c:v", "libx264", "-c:a", "aac", "-preset", "fast",
        "-ar", "44100", "-ac", "2",
        output_path,
    ])


def _ensure_audio(input_path: str, output_path: str):
    """Add silent audio track if clip has no audio stream."""
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=codec_type", "-of", "csv=p=0", input_path],
        capture_output=True, text=True,
    )
    if probe.stdout.strip():
        shutil.copy(input_path, output_path)
        return
    _run_ffmpeg([
        "ffmpeg", "-y", "-i", input_path,
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-c:v", "copy", "-c:a", "aac",
        "-shortest", output_path,
    ])


def _crossfade_clips(clips: list[str], output_path: str, duration: float, fps: int, tmpdir: str):
    if len(clips) == 1:
        _reencode(clips[0], output_path, fps)
        return

    # Use first real clip's resolution as target for all clips
    w, h = _get_resolution(clips[0])
    # Re-encode all clips to same fps/resolution/codec + ensure audio stream exists
    normed = []
    for i, c in enumerate(clips):
        n = os.path.join(tmpdir, f"norm_{i:03d}.mp4")
        _reencode(c, n, fps, width=w, height=h)
        with_audio = os.path.join(tmpdir, f"norma_{i:03d}.mp4")
        _ensure_audio(n, with_audio)
        normed.append(with_audio)

    # Accumulate xfade pairs left-to-right
    current = normed[0]
    for i in range(1, len(normed)):
        dur = _get_duration(current)
        offset = max(0.0, dur - duration)
        nxt = normed[i]
        out = os.path.join(tmpdir, f"xfade_{i:03d}.mp4")
        _run_ffmpeg([
            "ffmpeg", "-y", "-i", current, "-i", nxt,
            "-filter_complex",
            f"[0:v][1:v]xfade=transition=fade:duration={duration:.2f}:offset={offset:.2f}[v];"
            f"[0:a][1:a]acrossfade=d={duration:.2f}[a]",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-c:a", "aac", "-preset", "fast",
            out,
        ])
        current = out

    shutil.copy(current, output_path)


def _apply_watermark(input_path: str, output_path: str, text: str):
    safe_text = text.replace("'", "\\'").replace(":", "\\:")
    _run_ffmpeg([
        "ffmpeg", "-y", "-i", input_path,
        "-vf",
        f"drawtext=text='{safe_text}':fontsize=28:fontcolor=white:x=20:y=20"
        f":shadowcolor=black:shadowx=2:shadowy=2",
        "-c:v", "libx264", "-c:a", "copy", "-preset", "fast",
        output_path,
    ])


def _run_ffmpeg(cmd: list):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr[-300:]}")
