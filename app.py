import os
import time
import uuid
import json
import logging
import threading
from flask import Flask, request, jsonify, render_template, send_from_directory, send_file, Response
from flask_cors import CORS
from dotenv import load_dotenv

from services.video_processor import (
    get_ffmpeg_path,
    get_video_info,
    extract_audio,
    extract_thumbnail,
    generate_all_chapter_videos,
    format_timestamp
)

# Ensure FFmpeg is on PATH for any subprocess or tool (including yt-dlp)
try:
    _ff_dir = os.path.dirname(get_ffmpeg_path())
    _venv_bin = os.path.abspath(os.path.join(os.path.dirname(__file__), ".venv", "bin"))
    os.environ["PATH"] = f"{_ff_dir}:{_venv_bin}:{os.environ.get('PATH', '')}"
except Exception:
    pass
from services.transcriber import transcribe_audio
from services.topic_detector import generate_chapters, generate_lecture_notes
from services.temporal_event_detector import detect_temporal_events
from services.anomaly_detector import detect_anomalies
from services.temporal_qa import answer_temporal_question, generate_temporal_mcqs
from services.search_engine import (
    search_video,
    answer_video_question,
    answer_followup_question,
    simplify_answer_explanation
)
from services.quiz_generator import generate_topic_quiz, generate_full_lecture_quiz, generate_temporal_events_quiz
import services.learning_db as learning_db

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("vidseek")

app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
PROCESSED_DIR = os.path.join(BASE_DIR, "processed")
SAMPLE_DIR = os.path.join(BASE_DIR, "sample_data")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)
os.makedirs(SAMPLE_DIR, exist_ok=True)

# In-memory jobs tracking
jobs = {}

def get_job_file(job_id):
    return os.path.join(PROCESSED_DIR, job_id, "job.json")

def save_job(job_id, data):
    job_dir = os.path.join(PROCESSED_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)
    with open(get_job_file(job_id), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    jobs[job_id] = data

def load_saved_jobs():
    """Load previously processed jobs from disk on startup."""
    if not os.path.exists(PROCESSED_DIR):
        return
    for jid in os.listdir(PROCESSED_DIR):
        jpath = os.path.join(PROCESSED_DIR, jid, "job.json")
        if os.path.isfile(jpath):
            try:
                with open(jpath, "r", encoding="utf-8") as f:
                    jobs[jid] = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load job {jid}: {e}")

load_saved_jobs()

def cleanup_job_data(jid):
    """Purges video and processed artifacts for a given job."""
    if not jid:
        return
    if jid in jobs:
        vpath = jobs[jid].get("video_path")
        if vpath and os.path.exists(vpath) and not vpath.startswith(SAMPLE_DIR):
            try:
                os.remove(vpath)
                logger.info(f"Deleted upload video: {vpath}")
            except Exception as e:
                logger.warning(f"Failed deleting {vpath}: {e}")
        del jobs[jid]

    jdir = os.path.join(PROCESSED_DIR, str(jid))
    if os.path.exists(jdir):
        try:
            import shutil
            shutil.rmtree(jdir)
            logger.info(f"Deleted processed directory: {jdir}")
        except Exception as e:
            logger.warning(f"Failed deleting dir {jdir}: {e}")

def cleanup_all_temporary_jobs():
    """Purges all non-sample temporary jobs and orphaned upload files."""
    for jid in list(jobs.keys()):
        if not str(jid).startswith("sample_"):
            cleanup_job_data(jid)
    if os.path.exists(UPLOAD_DIR):
        for f in os.listdir(UPLOAD_DIR):
            if not f.startswith("sample_"):
                fp = os.path.join(UPLOAD_DIR, f)
                try:
                    if os.path.isfile(fp):
                        os.remove(fp)
                except Exception:
                    pass


from services.url_downloader import download_video_from_url

# Helper to periodically save job during long transcription
_last_save_time = 0

def process_video_pipeline(job_id, video_path):
    """
    Background worker orchestrating the full 5-stage AI pipeline:
    1. Extract Video Metadata & Master Thumbnail
    2. Extract Audio with FFmpeg
    3. Whisper Speech-to-Text Transcription with Live Progress
    4. AI Topic Boundary Detection & Chapter Titling
    5. FFmpeg Video Segmentation using Ultra-Fast Stream Copy
    6. Lecture Notes Compilation & Search Indexing
    """
    global _last_save_time
    job_dir = os.path.join(PROCESSED_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    try:
        # Stage 1: Metadata
        jobs[job_id]["stage"] = "metadata"
        jobs[job_id]["progress"] = 10
        jobs[job_id]["message"] = "Analyzing video format, duration, and resolution..."
        save_job(job_id, jobs[job_id])

        video_info = get_video_info(video_path)
        master_thumb = os.path.join(job_dir, "thumbnail.jpg")
        extract_thumbnail(video_path, master_thumb, timestamp_sec=min(2.0, video_info["duration"] / 2))
        video_info["thumbnail_url"] = f"/api/video/{job_id}/thumbnail/thumbnail.jpg"
        jobs[job_id]["video_info"] = video_info

        # Stage 2: Audio Extraction
        jobs[job_id]["stage"] = "audio_extraction"
        jobs[job_id]["progress"] = 25
        jobs[job_id]["message"] = "Extracting high-fidelity audio stream via FFmpeg..."
        save_job(job_id, jobs[job_id])

        audio_path = os.path.join(job_dir, "audio.wav")
        extract_audio(video_path, audio_path)

        # Stage 3: Whisper Speech-to-Text with live progress streaming
        jobs[job_id]["stage"] = "transcription"
        jobs[job_id]["progress"] = 30
        jobs[job_id]["message"] = "Starting Whisper AI speech transcription..."
        save_job(job_id, jobs[job_id])

        def on_transcribe_progress(current_sec, total_sec):
            global _last_save_time
            now = time.time()
            # Calculate progress from 30% to 75%
            pct = min(75, int(30 + (current_sec / max(1.0, total_sec)) * 45))
            cur_fmt = format_timestamp(current_sec)
            tot_fmt = format_timestamp(total_sec)
            jobs[job_id]["progress"] = pct
            jobs[job_id]["message"] = f"Transcribing audio: {cur_fmt} / {tot_fmt} ({pct}%)"
            if now - _last_save_time > 1.5:
                save_job(job_id, jobs[job_id])
                _last_save_time = now

        transcribe_result = transcribe_audio(audio_path, model_size="tiny", progress_callback=on_transcribe_progress)
        segments = transcribe_result["segments"]
        full_transcript = transcribe_result["full_text"]
        jobs[job_id]["segments"] = segments
        jobs[job_id]["full_transcript"] = full_transcript

        # Immediately delete uncompressed audio.wav to free hundreds of MBs
        if os.path.exists(audio_path):
            try:
                os.remove(audio_path)
                logger.info(f"Cleaned up intermediate audio {audio_path}")
            except Exception as ex:
                logger.warning(f"Could not remove {audio_path}: {ex}")


        # Stage 4: AI Topic Boundary Detection
        jobs[job_id]["stage"] = "topic_detection"
        jobs[job_id]["progress"] = 80
        jobs[job_id]["message"] = "Detecting topic boundaries, semantic transitions, and naming chapters..."
        save_job(job_id, jobs[job_id])

        chapters_raw = generate_chapters(segments, video_info["duration"])
        notes_md = generate_lecture_notes(chapters_raw, video_info)
        jobs[job_id]["notes"] = notes_md

        # Stage 5: Video Splitting with FFmpeg Stream Copy (Super Fast)
        jobs[job_id]["stage"] = "video_splitting"
        jobs[job_id]["progress"] = 92
        jobs[job_id]["message"] = f"Slicing video into {len(chapters_raw)} standalone topic clips (stream copy)..."
        save_job(job_id, jobs[job_id])

        chapters_enriched = generate_all_chapter_videos(video_path, chapters_raw, job_dir, job_id)
        jobs[job_id]["chapters"] = chapters_enriched

        # Stage 6: BiLSTM Temporal Events & Autoencoder Anomaly Detection
        jobs[job_id]["stage"] = "temporal_analysis"
        jobs[job_id]["progress"] = 96
        jobs[job_id]["message"] = "Running BiLSTM sequence event detection & Autoencoder anomaly scoring..."
        save_job(job_id, jobs[job_id])

        t_events_res = detect_temporal_events(video_path, segments, video_info["duration"])
        anoms_res = detect_anomalies(video_path, segments, video_info["duration"])
        jobs[job_id]["temporal_events"] = t_events_res.get("events", [])
        jobs[job_id]["anomalies"] = anoms_res.get("anomalies", [])
        jobs[job_id]["anomaly_timeline"] = anoms_res.get("timeline", [])
        jobs[job_id]["anomaly_summary"] = anoms_res.get("summary", {})

        # Complete
        jobs[job_id]["stage"] = "completed"
        jobs[job_id]["progress"] = 100
        jobs[job_id]["message"] = "Processing complete! All topic videos, chapters, notes, and search ready."
        save_job(job_id, jobs[job_id])
        logger.info(f"Job {job_id} completed successfully with {len(chapters_enriched)} chapters and {len(jobs[job_id]['temporal_events'])} temporal events.")

    except Exception as e:
        logger.exception(f"Error processing job {job_id}: {e}")
        jobs[job_id]["stage"] = "error"
        jobs[job_id]["progress"] = 0
        jobs[job_id]["message"] = f"Processing error: {str(e)}"
        save_job(job_id, jobs[job_id])


# ----------------- ROUTES ----------------- #

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/upload", methods=["POST"])
def upload_video():
    if "video" not in request.files:
        return jsonify({"error": "No video file provided"}), 400

    file = request.files["video"]
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400

    job_id = str(uuid.uuid4())[:8]
    filename = f"{job_id}_{file.filename}"
    saved_path = os.path.join(UPLOAD_DIR, filename)
    file.save(saved_path)

    jobs[job_id] = {
        "job_id": job_id,
        "filename": file.filename,
        "source_type": "upload",
        "source_url": file.filename,
        "video_path": saved_path,
        "stage": "queued",
        "progress": 5,
        "message": "Video uploaded, starting processing queue...",
        "created_at": time.time(),
        "video_info": {},
        "chapters": [],
        "segments": [],
        "notes": ""
    }
    save_job(job_id, jobs[job_id])

    thread = threading.Thread(target=process_video_pipeline, args=(job_id, saved_path), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id, "status": "queued"})

@app.route("/api/load-sample", methods=["POST"])
def load_sample():
    """Load and process the pre-generated Java Lecture demonstration video."""
    sample_file = os.path.join(SAMPLE_DIR, "java_lecture_sample.mp4")
    if not os.path.exists(sample_file):
        from sample_data.create_sample import create_sample_lecture
        sample_file = create_sample_lecture(sample_file)

    job_id = f"sample_{str(uuid.uuid4())[:4]}"
    # Copy or reference sample video
    dest_path = os.path.join(UPLOAD_DIR, f"{job_id}_Java_Lecture_Masterclass.mp4")
    import shutil
    shutil.copyfile(sample_file, dest_path)

    jobs[job_id] = {
        "job_id": job_id,
        "filename": "Java_Programming_Masterclass.mp4",
        "source_type": "sample",
        "source_url": "Built-in Java Programming Masterclass",
        "video_path": dest_path,
        "stage": "queued",
        "progress": 5,
        "message": "Initializing sample lecture demonstration...",
        "created_at": time.time(),
        "video_info": {},
        "chapters": [],
        "segments": [],
        "notes": ""
    }
    save_job(job_id, jobs[job_id])

    thread = threading.Thread(target=process_video_pipeline, args=(job_id, dest_path), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id, "status": "queued"})

@app.route("/api/status/<job_id>", methods=["GET"])
def get_status(job_id):
    if job_id not in jobs:
        # Check if saved on disk
        jfile = get_job_file(job_id)
        if os.path.exists(jfile):
            with open(jfile, "r", encoding="utf-8") as f:
                jobs[job_id] = json.load(f)
        else:
            return jsonify({"error": "Job not found"}), 404

    job = jobs[job_id]
    return jsonify({
        "job_id": job_id,
        "stage": job.get("stage", "unknown"),
        "progress": job.get("progress", 0),
        "message": job.get("message", ""),
        "completed": job.get("stage") == "completed",
        "error": job.get("message") if job.get("stage") == "error" else None
    })

@app.route("/api/job/<job_id>", methods=["GET"])
def get_job(job_id):
    if job_id not in jobs:
        jfile = get_job_file(job_id)
        if os.path.exists(jfile):
            with open(jfile, "r", encoding="utf-8") as f:
                jobs[job_id] = json.load(f)
        else:
            return jsonify({"error": "Job not found"}), 404

    job = jobs[job_id]

    # Lazily ensure temporal events and anomaly detection data exist for completed jobs
    if job.get("stage") == "completed" and "temporal_events" not in job:
        try:
            vpath = job.get("video_path")
            segs = job.get("segments", [])
            dur = job.get("video_info", {}).get("duration", 0.0)
            t_events_res = detect_temporal_events(vpath, segs, dur)
            anoms_res = detect_anomalies(vpath, segs, dur)
            job["temporal_events"] = t_events_res.get("events", [])
            job["anomalies"] = anoms_res.get("anomalies", [])
            job["anomaly_timeline"] = anoms_res.get("timeline", [])
            job["anomaly_summary"] = anoms_res.get("summary", {})
            save_job(job_id, job)
        except Exception as e:
            logger.warning(f"Lazy temporal analysis extraction error for job {job_id}: {e}")

    return jsonify({
        "job_id": job_id,
        "filename": job.get("filename", ""),
        "stage": job.get("stage"),
        "video_info": job.get("video_info", {}),
        "chapters": job.get("chapters", []),
        "segments": job.get("segments", []),
        "temporal_events": job.get("temporal_events", []),
        "anomalies": job.get("anomalies", []),
        "anomaly_timeline": job.get("anomaly_timeline", []),
        "anomaly_summary": job.get("anomaly_summary", {}),
        "full_transcript": job.get("full_transcript", ""),
        "notes": job.get("notes", ""),
        "master_video_url": f"/api/video/{job_id}/master"
    })

@app.route("/api/jobs", methods=["GET"])
def list_jobs():
    load_saved_jobs()
    recent = []
    for jid, data in jobs.items():
        if data.get("stage") == "completed":
            vinfo = data.get("video_info", {})
            title = data.get("filename", "Untitled Lecture")
            # Format clean title
            clean_title = title.replace("_", " ").replace(".mp4", "").replace(".webm", "").replace(".mkv", "").strip()
            # If title starts with jid, strip it
            if clean_title.lower().startswith(jid.lower()):
                clean_title = clean_title[len(jid):].strip()
            if not clean_title:
                clean_title = "Educational Lecture Video"

            c_time = data.get("created_at", time.time())
            stype = data.get("source_type")
            if not stype:
                if jid.startswith("sample_"):
                    stype = "sample"
                elif "youtube" in str(data.get("source_url", "")).lower() or "youtu.be" in str(data.get("source_url", "")).lower():
                    stype = "youtube"
                else:
                    stype = "upload"

            recent.append({
                "job_id": jid,
                "title": clean_title,
                "filename": data.get("filename", ""),
                "source_type": stype,
                "source_url": data.get("source_url", ""),
                "chapters_count": len(data.get("chapters", [])),
                "duration": vinfo.get("duration_formatted", "00:00"),
                "resolution": f"{vinfo.get('width', '')}x{vinfo.get('height', '')}" if vinfo.get("width") else "HD Video",
                "thumbnail_url": vinfo.get("thumbnail_url", f"/api/video/{jid}/thumbnail/thumbnail.jpg"),
                "created_at": c_time,
                "created_at_formatted": time.strftime("%b %d, %Y • %I:%M %p", time.localtime(c_time)),
                "master_video_url": f"/api/video/{jid}/master"
            })
    # Sort descending by created_at (newest first)
    recent.sort(key=lambda x: x.get("created_at", 0), reverse=True)
    return jsonify({"jobs": recent})

@app.route("/api/history/delete/<job_id>", methods=["POST", "DELETE"])
def delete_history_item(job_id):
    load_saved_jobs()
    if job_id in jobs or os.path.exists(os.path.join(PROCESSED_DIR, job_id)):
        cleanup_job_data(job_id)
        return jsonify({"status": "deleted", "job_id": job_id})
    return jsonify({"error": "Job not found"}), 404

@app.route("/api/history/clear", methods=["POST"])
def clear_all_history():
    cleanup_all_temporary_jobs()
    return jsonify({"status": "cleared"})

@app.route("/api/video/<job_id>/master")
def stream_master_video(job_id):
    if job_id not in jobs:
        return "Not found", 404
    video_path = jobs[job_id].get("video_path")
    if not video_path or not os.path.exists(video_path):
        return "Video file missing", 404
    return send_file(video_path, mimetype="video/mp4", conditional=True)

@app.route("/api/video/<job_id>/chapter/<filename>")
def stream_chapter_video(job_id, filename):
    job_dir = os.path.join(PROCESSED_DIR, job_id)
    file_path = os.path.join(job_dir, filename)
    if not os.path.exists(file_path):
        return "Chapter video not found", 404
    return send_file(file_path, mimetype="video/mp4", conditional=True)

@app.route("/api/video/<job_id>/thumbnail/<filename>")
def stream_thumbnail(job_id, filename):
    job_dir = os.path.join(PROCESSED_DIR, job_id)
    file_path = os.path.join(job_dir, filename)
    if not os.path.exists(file_path):
        return "Thumbnail not found", 404
    return send_file(file_path, mimetype="image/jpeg")

@app.route("/api/search", methods=["POST"])
def search_endpoint():
    data = request.get_json() or {}
    job_id = data.get("job_id")
    query = data.get("query", "").strip()

    if not job_id or job_id not in jobs:
        return jsonify({"error": "Valid job_id required"}), 400

    job = jobs[job_id]
    search_data = search_video(
        query,
        job.get("segments", []),
        job.get("chapters", []),
        temporal_events=job.get("temporal_events", [])
    )
    if isinstance(search_data, dict):
        return jsonify({
            "query": query,
            "results": search_data.get("results", []),
            "ai_best_match": search_data.get("ai_best_match"),
            "ai_intent": search_data.get("ai_intent"),
            "target_concept": search_data.get("target_concept")
        })
    return jsonify({"query": query, "results": search_data})

@app.route("/api/ask", methods=["POST"])
def ask_endpoint():
    data = request.get_json() or {}
    job_id = data.get("job_id")
    question = data.get("question", "").strip()

    if not job_id or job_id not in jobs:
        return jsonify({"error": "Valid job_id required"}), 400

    job = jobs[job_id]
    topic_id = data.get("topic_id", 0)
    answer_data = answer_video_question(
        question,
        job.get("segments", []),
        job.get("chapters", []),
        temporal_events=job.get("temporal_events", [])
    )

    qa_id = learning_db.save_qa_history(
        video_id=job_id,
        question=question,
        answer=answer_data.get("answer", ""),
        source_timestamp=answer_data.get("timestamp", 0),
        source_time_fmt=answer_data.get("timestamp_formatted", "00:00"),
        topic_id=topic_id
    )
    answer_data["qa_id"] = qa_id
    return jsonify(answer_data)

# ================= TEMPORAL DEEP LEARNING ROUTES ================= #

@app.route("/api/video/<job_id>/temporal-events", methods=["GET"])
def get_temporal_events_endpoint(job_id):
    if job_id not in jobs:
        jfile = get_job_file(job_id)
        if os.path.exists(jfile):
            with open(jfile, "r", encoding="utf-8") as f:
                jobs[job_id] = json.load(f)
        else:
            return jsonify({"error": "Video not found"}), 404

    job = jobs[job_id]
    if "temporal_events" not in job:
        vpath = job.get("video_path")
        segs = job.get("segments", [])
        dur = job.get("video_info", {}).get("duration", 0.0)
        t_res = detect_temporal_events(vpath, segs, dur)
        job["temporal_events"] = t_res.get("events", [])
        save_job(job_id, job)

    return jsonify({
        "success": True,
        "job_id": job_id,
        "events": job.get("temporal_events", []),
        "total_events": len(job.get("temporal_events", [])),
        "model_type": "Bidirectional LSTM (BiLSTM)"
    })

@app.route("/api/video/<job_id>/anomalies", methods=["GET"])
def get_anomalies_endpoint(job_id):
    if job_id not in jobs:
        jfile = get_job_file(job_id)
        if os.path.exists(jfile):
            with open(jfile, "r", encoding="utf-8") as f:
                jobs[job_id] = json.load(f)
        else:
            return jsonify({"error": "Video not found"}), 404

    job = jobs[job_id]
    if "anomalies" not in job:
        vpath = job.get("video_path")
        segs = job.get("segments", [])
        dur = job.get("video_info", {}).get("duration", 0.0)
        a_res = detect_anomalies(vpath, segs, dur)
        job["anomalies"] = a_res.get("anomalies", [])
        job["anomaly_timeline"] = a_res.get("timeline", [])
        job["anomaly_summary"] = a_res.get("summary", {})
        save_job(job_id, job)

    return jsonify({
        "success": True,
        "job_id": job_id,
        "anomalies": job.get("anomalies", []),
        "timeline": job.get("anomaly_timeline", []),
        "summary": job.get("anomaly_summary", {}),
        "model_type": "Dense Autoencoder (Bottleneck Latent Reconstructor)"
    })

@app.route("/api/video/<job_id>/temporal-qa", methods=["POST"])
def temporal_qa_endpoint(job_id):
    data = request.get_json() or {}
    question = data.get("question", "").strip()

    if not job_id:
        return jsonify({"error": "Valid job_id required"}), 400
    if job_id not in jobs:
        jfile = get_job_file(job_id)
        if os.path.exists(jfile):
            with open(jfile, "r", encoding="utf-8") as f:
                jobs[job_id] = json.load(f)
        else:
            return jsonify({"error": "Video not found"}), 404
    if not question:
        return jsonify({"error": "Question required"}), 400

    job = jobs[job_id]
    events = job.get("temporal_events", [])
    if not events:
        vpath = job.get("video_path")
        segs = job.get("segments", [])
        dur = job.get("video_info", {}).get("duration", 0.0)
        t_res = detect_temporal_events(vpath, segs, dur)
        events = t_res.get("events", [])
        job["temporal_events"] = events
        save_job(job_id, job)

    ans = answer_temporal_question(question, events, job.get("segments", []), job.get("chapters", []))
    qa_id = learning_db.save_qa_history(
        video_id=job_id,
        question=question,
        answer=ans.get("answer", ""),
        source_timestamp=ans.get("timestamp", 0),
        source_time_fmt=ans.get("timestamp_formatted", "00:00")
    )
    ans["qa_id"] = qa_id
    ans["success"] = True
    ans["job_id"] = job_id
    return jsonify(ans)

@app.route("/api/quiz/temporal/<job_id>", methods=["GET"])
def get_temporal_quiz_endpoint(job_id):
    if job_id not in jobs:
        jfile = get_job_file(job_id)
        if os.path.exists(jfile):
            with open(jfile, "r", encoding="utf-8") as f:
                jobs[job_id] = json.load(f)
        else:
            return jsonify({"error": "Video not found"}), 404

    job = jobs[job_id]
    events = job.get("temporal_events", [])
    if not events:
        vpath = job.get("video_path")
        segs = job.get("segments", [])
        dur = job.get("video_info", {}).get("duration", 0.0)
        t_res = detect_temporal_events(vpath, segs, dur)
        events = t_res.get("events", [])
        job["temporal_events"] = events
        save_job(job_id, job)

    quiz = generate_temporal_events_quiz(job_id, events, count=5)
    return jsonify({
        "success": True,
        "job_id": job_id,
        "quiz": quiz
    })

# ================= LEARNING SUITE: Q&A ENHANCEMENTS ================= #

@app.route("/api/qa/history/<job_id>", methods=["GET"])
def get_qa_history_endpoint(job_id):
    history = learning_db.get_video_qa_history(job_id)
    return jsonify({"job_id": job_id, "history": history})

@app.route("/api/qa/followup", methods=["POST"])
def qa_followup_endpoint():
    data = request.get_json() or {}
    job_id = data.get("job_id")
    followup_question = (data.get("followup_question") or data.get("question") or "").strip()
    parent_qa_id = data.get("parent_history_id") or data.get("parent_qa_id")
    parent_question = data.get("parent_question", "")
    parent_answer = data.get("parent_answer", "")
    topic_id = data.get("topic_id")

    if not job_id or job_id not in jobs:
        return jsonify({"error": "Valid job_id required"}), 400
    if not followup_question:
        return jsonify({"error": "Follow-up question required"}), 400

    job = jobs[job_id]
    ans = answer_followup_question(
        followup_question=followup_question,
        parent_question=parent_question,
        parent_answer=parent_answer,
        segments=job.get("segments", []),
        chapters=job.get("chapters", []),
        topic_id=topic_id
    )

    qa_id = learning_db.save_qa_history(
        video_id=job_id,
        question=followup_question,
        answer=ans.get("answer", ""),
        source_timestamp=ans.get("timestamp", 0),
        source_time_fmt=ans.get("timestamp_formatted", "00:00"),
        topic_id=topic_id or 0,
        parent_qa_id=parent_qa_id
    )
    ans["qa_id"] = qa_id
    return jsonify(ans)

@app.route("/api/qa/simplify", methods=["POST"])
def qa_simplify_endpoint():
    data = request.get_json() or {}
    job_id = data.get("job_id")
    original_answer = data.get("original_answer", "").strip()
    topic_title = data.get("topic_title", "the lecture")
    timestamp_fmt = data.get("timestamp_formatted", "00:00")
    parent_qa_id = data.get("parent_qa_id")

    if not original_answer:
        return jsonify({"error": "Original explanation required"}), 400

    simplified = simplify_answer_explanation(original_answer, topic_title, timestamp_fmt)
    if job_id:
        learning_db.save_qa_history(
            video_id=job_id,
            question=f"💡 Explain Simply: {topic_title}",
            answer=simplified.get("simplified_answer", ""),
            source_timestamp=0,
            source_time_fmt=timestamp_fmt,
            parent_qa_id=parent_qa_id,
            is_simplified=1
        )
    return jsonify(simplified)

# ================= LEARNING SUITE: AI STUDY MODE ================= #

@app.route("/api/study/video/<job_id>", methods=["GET"])
def get_study_video_endpoint(job_id):
    if job_id not in jobs:
        jfile = get_job_file(job_id)
        if os.path.exists(jfile):
            with open(jfile, "r", encoding="utf-8") as f:
                jobs[job_id] = json.load(f)
        else:
            return jsonify({"error": "Video not found"}), 404

    job = jobs[job_id]
    chapters = job.get("chapters", [])
    topic_prog_map = learning_db.get_video_topic_progress(job_id)

    enriched_topics = []
    completed_count = 0
    total_watch_time = 0

    for ch in chapters:
        tid = int(ch.get("id", 1))
        prog = topic_prog_map.get(tid, {})
        status = prog.get("status", "not_started")
        wtime = float(prog.get("watch_time", 0.0))
        last_pos = float(prog.get("last_position", 0.0))

        if status == "completed":
            completed_count += 1
        total_watch_time += wtime

        enriched_topics.append({
            "id": tid,
            "topic_id": tid,
            "title": ch.get("title", f"Topic {tid}"),
            "start_time": ch.get("start_time", 0.0),
            "end_time": ch.get("end_time", 0.0),
            "start_formatted": ch.get("start_formatted", "00:00"),
            "end_formatted": ch.get("end_formatted", "00:00"),
            "duration_formatted": ch.get("duration_formatted", "00:00"),
            "summary": ch.get("summary", ""),
            "key_points": ch.get("key_points", []),
            "text": ch.get("text", ""),
            "video_url": ch.get("video_url", ""),
            "thumbnail_url": ch.get("thumbnail_url", ""),
            "status": status,
            "watch_time": wtime,
            "last_position": last_pos,
            "quiz_attempts": int(prog.get("quiz_attempts", 0)),
            "best_score": round(float(prog.get("best_score", 0.0)), 1)
        })

    total_topics = len(chapters)
    remaining_count = max(0, total_topics - completed_count)
    progress_pct = round((completed_count / total_topics) * 100, 1) if total_topics > 0 else 0.0

    hrs = int(total_watch_time // 3600)
    mins = int((total_watch_time % 3600) // 60)
    study_time_str = f"{hrs}h {mins}m" if hrs > 0 else f"{mins}m"

    vinfo = job.get("video_info", {})
    clean_title = job.get("filename", "Lecture").replace("_", " ").replace(".mp4", "").replace(".webm", "").strip()
    if clean_title.lower().startswith(job_id.lower()):
        clean_title = clean_title[len(job_id):].strip()

    return jsonify({
        "video_id": job_id,
        "job_id": job_id,
        "title": clean_title,
        "duration_formatted": vinfo.get("duration_formatted", "00:00"),
        "total_topics": total_topics,
        "completed_count": completed_count,
        "completed_topics": completed_count,
        "remaining_count": remaining_count,
        "progress_percentage": progress_pct,
        "progress_pct": progress_pct,
        "watch_time_seconds": total_watch_time,
        "total_study_time": study_time_str,
        "topics": enriched_topics
    })

@app.route("/api/study/topic/complete", methods=["POST"])
def complete_study_topic_endpoint():
    data = request.get_json() or {}
    job_id = data.get("job_id")
    topic_id = int(data.get("topic_id", 0))
    topic_title = data.get("topic_title", f"Topic {topic_id}")

    if not job_id:
        return jsonify({"error": "job_id required"}), 400

    learning_db.update_topic_progress(
        video_id=job_id,
        topic_id=topic_id,
        topic_title=topic_title,
        status="completed"
    )
    return jsonify({"status": "completed", "video_id": job_id, "topic_id": topic_id})

# ================= LEARNING SUITE: MCQ / QUIZ SYSTEM ================= #

@app.route("/api/quiz/topic/<job_id>/<int:topic_id>", methods=["GET"])
def get_topic_quiz_endpoint(job_id, topic_id):
    if job_id not in jobs:
        jfile = get_job_file(job_id)
        if os.path.exists(jfile):
            with open(jfile, "r", encoding="utf-8") as f:
                jobs[job_id] = json.load(f)
        else:
            return jsonify({"error": "Video not found"}), 404

    job = jobs[job_id]
    chapters = job.get("chapters", [])
    target_ch = None
    for c in chapters:
        if int(c.get("id", 0)) == topic_id or int(c.get("chapter_number", 0)) == topic_id:
            target_ch = c
            break

    if not target_ch and chapters:
        target_ch = chapters[0]

    if not target_ch:
        return jsonify({"error": "Topic not found"}), 404

    quiz = generate_topic_quiz(job_id, target_ch, job.get("segments", []))
    return jsonify(quiz)

@app.route("/api/quiz/full/<job_id>", methods=["GET"])
def get_full_quiz_endpoint(job_id):
    if job_id not in jobs:
        jfile = get_job_file(job_id)
        if os.path.exists(jfile):
            with open(jfile, "r", encoding="utf-8") as f:
                jobs[job_id] = json.load(f)
        else:
            return jsonify({"error": "Video not found"}), 404

    job = jobs[job_id]
    chapters = job.get("chapters", [])
    if not chapters:
        return jsonify({"error": "No chapters available for quiz"}), 400

    quiz = generate_full_lecture_quiz(job_id, chapters, job.get("segments", []))
    return jsonify(quiz)

@app.route("/api/quiz/submit", methods=["POST"])
def submit_quiz_endpoint():
    data = request.get_json() or {}
    job_id = data.get("video_id") or data.get("job_id")
    quiz_id = int(data.get("quiz_id", 0))
    topic_id = int(data.get("topic_id", 0))
    answers = data.get("answers", {})

    if not quiz_id:
        return jsonify({"error": "quiz_id required"}), 400

    res = learning_db.record_quiz_submission(
        user_id="default_user",
        quiz_id=quiz_id,
        video_id=job_id,
        topic_id=topic_id,
        answers=answers
    )
    return jsonify(res)

# ================= LEARNING SUITE: LEARNING ANALYTICS ================= #

@app.route("/api/analytics/dashboard", methods=["GET"])
def analytics_dashboard_endpoint():
    load_saved_jobs()
    summary = learning_db.get_analytics_summary(user_id="default_user")

    # Enrich continue learning with video metadata
    cont = summary.get("continue_learning")
    if cont and cont.get("video_id") in jobs:
        target_job = jobs[cont["video_id"]]
        vinfo = target_job.get("video_info", {})
        title = target_job.get("filename", "Lecture Video").replace("_", " ").replace(".mp4", "").replace(".webm", "").strip()
        if title.lower().startswith(cont["video_id"].lower()):
            title = title[len(cont["video_id"]):].strip()
        cont["video_title"] = title
        cont["thumbnail_url"] = vinfo.get("thumbnail_url", f"/api/video/{cont['video_id']}/thumbnail/thumbnail.jpg")

    # Enrich weak topics with video title, chapter title, and start timestamp
    for wt in summary.get("weak_topics", []):
        vid = wt.get("video_id")
        tid = wt.get("topic_id")
        if vid in jobs:
            title = jobs[vid].get("filename", "Lecture").replace("_", " ").replace(".mp4", "").replace(".webm", "").strip()
            if title.lower().startswith(vid.lower()):
                title = title[len(vid):].strip()
            wt["video_title"] = title

            chaps = jobs[vid].get("chapters", [])
            matched = next((c for c in chaps if int(c.get("id", 0)) == int(tid)), None)
            if matched:
                wt["topic_title"] = matched.get("title", wt.get("topic_title"))
                wt["start_time"] = matched.get("start_time", 0.0)
                wt["start_formatted"] = matched.get("start_formatted", "00:00")
            else:
                wt["start_time"] = 0.0
                wt["start_formatted"] = "00:00"

    # Build per-video topic overview list for analytics
    video_overviews = []
    for jid, jdata in jobs.items():
        if jdata.get("stage") == "completed":
            v_title = jdata.get("filename", "Lecture").replace("_", " ").replace(".mp4", "").replace(".webm", "").strip()
            if v_title.lower().startswith(jid.lower()):
                v_title = v_title[len(jid):].strip()
            chaps = jdata.get("chapters", [])
            t_map = learning_db.get_video_topic_progress(jid)

            topics_stat = []
            c_cnt = 0
            for c in chaps:
                tid = int(c.get("id", 1))
                st = t_map.get(tid, {}).get("status", "not_started")
                if st == "completed":
                    c_cnt += 1
                topics_stat.append({
                    "id": tid,
                    "title": c.get("title", f"Topic {tid}"),
                    "status": st,
                    "start_formatted": c.get("start_formatted", "00:00"),
                    "duration_formatted": c.get("duration_formatted", "00:00")
                })

            pct = round((c_cnt / len(chaps)) * 100) if chaps else 0
            video_overviews.append({
                "job_id": jid,
                "title": v_title,
                "video_title": v_title,
                "chapters_count": len(chaps),
                "total_topics": len(chaps),
                "completed_count": c_cnt,
                "completed_topics": c_cnt,
                "progress_pct": pct,
                "topics": topics_stat
            })

    summary["video_overviews"] = video_overviews
    summary["video_progress"] = video_overviews
    summary["total_videos"] = len([j for j in jobs.values() if j.get("stage") == "completed"])
    summary["overall_accuracy"] = round(float(summary.get("quiz_accuracy", 0.0)), 1)
    summary["total_study_time_seconds"] = float(summary.get("total_study_seconds", 0.0))
    summary["total_quiz_attempts"] = int(summary.get("quiz_attempts", 0))
    summary["total_questions_asked"] = int(summary.get("questions_asked", 0))

    weekly_act = []
    for d in summary.get("daily_activity", []):
        weekly_act.append({
            "day_name": d.get("day", ""),
            "minutes": d.get("minutes", 0),
            "date": d.get("date", "")
        })
    summary["weekly_activity"] = weekly_act

    return jsonify(summary)

@app.route("/api/analytics/video/<job_id>", methods=["GET"])
def analytics_video_endpoint(job_id):
    prog = learning_db.get_video_topic_progress(job_id)
    return jsonify({"video_id": job_id, "topics_progress": prog})

@app.route("/api/learning/watch-event", methods=["POST"])
def watch_event_endpoint():
    data = request.get_json() or {}
    job_id = data.get("job_id")
    topic_id = int(data.get("topic_id", 0))
    topic_title = data.get("topic_title", "Topic")
    current_time = float(data.get("current_time", 0.0))
    duration_delta = float(data.get("duration_delta", 0.0))

    if not job_id:
        return jsonify({"error": "job_id required"}), 400

    learning_db.record_watch_heartbeat(
        video_id=job_id,
        topic_id=topic_id,
        topic_title=topic_title,
        current_time=current_time,
        duration_delta=duration_delta
    )
    return jsonify({"status": "recorded"})

@app.route("/api/download/chapter/<job_id>/<filename>")
def download_chapter(job_id, filename):
    job_dir = os.path.join(PROCESSED_DIR, job_id)
    return send_from_directory(job_dir, filename, as_attachment=True)

@app.route("/api/download/notes/<job_id>")
def download_notes(job_id):
    if job_id not in jobs:
        return "Not found", 404
    notes = jobs[job_id].get("notes", "")
    filename = f"{jobs[job_id].get('filename', 'lecture')}_notes.md"
    return Response(
        notes,
        mimetype="text/markdown",
        headers={"Content-Disposition": f"attachment;filename={filename}"}
    )

@app.route("/api/process-url", methods=["POST"])
def process_url_endpoint():
    data = request.get_json() or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "No video URL provided"}), 400

    job_id = str(uuid.uuid4())[:8]
    source_type = "youtube" if ("youtube.com" in url or "youtu.be" in url) else "web"
    jobs[job_id] = {
        "job_id": job_id,
        "filename": "Loading video link...",
        "source_type": source_type,
        "source_url": url,
        "video_path": "",
        "stage": "downloading",
        "progress": 5,
        "message": "Connecting to video link and extracting stream...",
        "created_at": time.time(),
        "video_info": {},
        "chapters": [],
        "segments": [],
        "notes": ""
    }
    save_job(job_id, jobs[job_id])

    def url_download_worker(jid, target_url):
        def dl_progress(pct, speed_mb):
            jobs[jid]["progress"] = max(5, int(pct * 0.15))
            jobs[jid]["message"] = f"Downloading video from link: {pct}% ({speed_mb} MB/s)..."
            save_job(jid, jobs[jid])

        try:
            dl_res = download_video_from_url(target_url, UPLOAD_DIR, jid, progress_callback=dl_progress)
            jobs[jid]["filename"] = dl_res["title"]
            jobs[jid]["video_path"] = dl_res["filepath"]
            save_job(jid, jobs[jid])

            # Now continue with full pipeline
            process_video_pipeline(jid, dl_res["filepath"])
        except Exception as e:
            logger.exception(f"URL download failed for {jid}: {e}")
            jobs[jid]["stage"] = "error"
            jobs[jid]["progress"] = 0
            jobs[jid]["message"] = f"Failed to download video from URL: {str(e)}"
            save_job(jid, jobs[jid])

    thread = threading.Thread(target=url_download_worker, args=(job_id, url), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id, "status": "downloading"})

@app.route("/api/cleanup", methods=["GET", "POST"])
def cleanup_endpoint():
    """
    Called on browser refresh, page exit (beforeunload), or manual reset.
    Removes temporary videos and processed directories to keep server storage clean.
    """
    data = request.get_json(silent=True) or {}
    target_job = request.args.get("job_id") or data.get("job_id")
    if target_job and target_job != "all":
        cleanup_job_data(target_job)
        return jsonify({"status": "cleaned", "job_id": target_job})
    else:
        cleanup_all_temporary_jobs()
        return jsonify({"status": "cleaned_all"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    logger.info(f"Starting VidSeek AI on http://127.0.0.1:{port}")
    # Disable auto-reloader so background video processing threads are not interrupted
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)
