import logging
import os
from flask import Flask, request, jsonify, send_from_directory

from utils import is_valid_youtube_shorts_url, error_response
from job_manager import create_job, get_job, start_job

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

STORAGE_DIR = os.path.join(os.path.dirname(__file__), "storage")


@app.route("/api/healthz", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/api/generate", methods=["POST"])
def generate():
    body = request.get_json(silent=True)
    if not body:
        return jsonify(error_response("Request body required")[0]), 400

    youtube_url = None
    details = None

    if "details" in body and str(body["details"]).strip():
        # Direct details mode — no YouTube URL needed
        details = str(body["details"]).strip()
        logger.info("[INFO] Direct details received (%d chars)", len(details))
    elif "url" in body and str(body["url"]).strip():
        youtube_url = str(body["url"]).strip()
        logger.info("[INFO] URL received: %s", youtube_url)
        if not is_valid_youtube_shorts_url(youtube_url):
            return jsonify(error_response("Invalid YouTube URL format")[0]), 400
    else:
        return jsonify(error_response("Provide either 'url' (YouTube Shorts) or 'details' (video description text)")[0]), 400

    params = {
        # ── Direct details (skips YouTube extraction) ──────────
        "details":              details,
        # ── GPT controls ──────────────────────────────────────
        "max_scenes":           body.get("max_scenes"),
        "language":             body.get("language"),
        "chat_id_gpt":          body.get("chat_id_gpt"),
        # ── Image controls ────────────────────────────────────
        "image_style":          body.get("image_style"),
        "negative_prompt":      body.get("negative_prompt"),
        "chat_id_image":        body.get("chat_id_image"),
        # ── Video generation controls (Grok API) ──────────────
        "chat_id_video":        body.get("chat_id_video"),
        "aspect_ratio":         body.get("aspect_ratio", "9:16"),
        "video_length":         body.get("video_length", 6),
        "resolution":           body.get("resolution", "720p"),
        "preset":               body.get("preset", "normal"),
        "motion_strength":      body.get("motion_strength"),
        "seed":                 body.get("seed"),
        "loop":                 body.get("loop", False),
        "negative_video_prompt": body.get("negative_video_prompt"),
        # ── Final video controls (ffmpeg) ─────────────────────
        "video_speed":          body.get("video_speed", 1.0),
        "transition":           body.get("transition", "none"),
        "fade_duration":        body.get("fade_duration", 0.5),
        "fps":                  body.get("fps", 24),
        "watermark_text":       body.get("watermark_text"),
        "mute_original_audio":  body.get("mute_original_audio", False),
        "intro_text":           body.get("intro_text"),
        "outro_text":           body.get("outro_text"),
        "bg_color":             body.get("bg_color", "black"),
        # ── Music controls ────────────────────────────────────
        "background_music":     body.get("background_music"),
        "music_volume":         body.get("music_volume", 0.3),
        "music_fade_in":        body.get("music_fade_in", 0.0),
        "music_fade_out":       body.get("music_fade_out", 0.0),
        "fade":                 body.get("fade", False),
        # ── Optional features ─────────────────────────────────
        "sound_effects":        bool(body.get("sound_effects", False)),
        "trim_silence":         bool(body.get("trim_silence", False)),
        "extract_voiceover":    bool(body.get("extract_voiceover", False)),
        "trending_sounds":      bool(body.get("trending_sounds", False)),
        # ── Voiceover text (user-provided) ────────────────────
        "voiceover":            body.get("voiceover"),
    }

    job_id = create_job(youtube_url, params)
    start_job(job_id)
    logger.info("[INFO] Job %s started", job_id)

    return jsonify({
        "success": True,
        "job_id": job_id,
        "status": "queued",
        "message": "Job started. Poll /api/job/<job_id> for progress.",
        "params_used": params,
    }), 202


@app.route("/api/job/<job_id>", methods=["GET"])
def job_status(job_id: str):
    job = get_job(job_id)
    if not job:
        return jsonify(error_response("Job not found")[0]), 404

    response = {
        "success": True,
        "job_id": job["job_id"],
        "status": job["status"],
        "step": job["step"],
        "total_scenes": job["total_scenes"],
        "completed_scenes": job["completed_scenes"],
        "created_at": job["created_at"],
        "finished_at": job["finished_at"],
        "scenes": job["scenes"],
    }

    if job["status"] == "completed":
        response["title"] = job.get("title", "Generated Story")
        response["final_video_url"] = job.get("final_video_url")

    elif job["status"] == "failed":
        response["success"] = False
        response["error"] = job["error"]

    return jsonify(response), 200


@app.route("/api/files/<path:filename>", methods=["GET"])
def serve_file(filename: str):
    return send_from_directory(STORAGE_DIR, filename)


@app.errorhandler(404)
def not_found(e):
    return jsonify({"success": False, "error": "Endpoint not found"}), 404


@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"success": False, "error": "Method not allowed"}), 405


@app.errorhandler(500)
def internal_error(e):
    logger.error("Unhandled exception: %s", e)
    return jsonify({"success": False, "error": "Internal server error"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info("Starting AI Video Remake API on port %d", port)
    app.run(host="0.0.0.0", port=port, debug=False)
