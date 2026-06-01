import logging
import os
import re
import subprocess
import tempfile

logger = logging.getLogger(__name__)


def trim_silence(
    input_path: str,
    output_path: str,
    noise_db: int = -50,
    min_silence_sec: float = 1.5,
) -> str:
    """Remove silent sections from a video file using ffmpeg silencedetect."""

    # Step 1: detect silence boundaries
    detect = subprocess.run(
        [
            "ffmpeg", "-i", input_path,
            "-af", f"silencedetect=noise={noise_db}dB:d={min_silence_sec}",
            "-f", "null", "-",
        ],
        capture_output=True, text=True,
    )
    stderr = detect.stderr

    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", stderr)]
    ends   = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", stderr)]

    # Get total duration
    dur_match = re.search(r"Duration: (\d+):(\d+):([\d.]+)", stderr)
    if not dur_match:
        logger.warning("trim_silence: could not read duration, copying as-is")
        return _copy(input_path, output_path)

    h, m, s = dur_match.groups()
    total_dur = int(h) * 3600 + int(m) * 60 + float(s)

    if not starts:
        logger.info("trim_silence: no silence found, copying as-is")
        return _copy(input_path, output_path)

    # Build non-silent intervals
    intervals = []
    prev = 0.0
    for start, end in zip(starts, ends):
        if start > prev + 0.05:
            intervals.append((prev, start))
        prev = end
    if prev < total_dur - 0.05:
        intervals.append((prev, total_dur))

    if not intervals:
        logger.info("trim_silence: entire video is silent, copying as-is")
        return _copy(input_path, output_path)

    logger.info("trim_silence: keeping %d non-silent segment(s)", len(intervals))

    # Step 2: extract each segment to a temp file, then concat
    with tempfile.TemporaryDirectory() as tmpdir:
        seg_files = []
        for idx, (t_start, t_end) in enumerate(intervals):
            seg = os.path.join(tmpdir, f"seg{idx:04d}.mp4")
            dur = t_end - t_start
            if dur < 0.1:
                continue
            r = subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-ss", f"{t_start:.3f}", "-i", input_path,
                    "-t", f"{dur:.3f}",
                    "-c:v", "libx264", "-c:a", "aac",
                    "-avoid_negative_ts", "make_zero",
                    seg,
                ],
                capture_output=True, text=True,
            )
            if r.returncode == 0:
                seg_files.append(seg)

        if not seg_files:
            return _copy(input_path, output_path)

        # Write concat list
        concat_txt = os.path.join(tmpdir, "concat.txt")
        with open(concat_txt, "w") as f:
            for seg in seg_files:
                f.write(f"file '{seg}'\n")

        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", concat_txt,
                "-c", "copy",
                output_path,
            ],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            logger.error("trim_silence concat failed: %s", result.stderr[-200:])
            return _copy(input_path, output_path)

    logger.info("trim_silence: done → %s", os.path.basename(output_path))
    return output_path


def _copy(src: str, dst: str) -> str:
    import shutil
    shutil.copy2(src, dst)
    return dst
