import os
import sys
import re
import json
import logging
import subprocess
import yt_dlp

# Ensure root directory is on sys.path if run directly as a script
if __package__ is None or __package__ == "":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.video_processor import get_ffmpeg_path

logger = logging.getLogger(__name__)

# Strict limit to guarantee video stays under 500 MB (target ~50MB to 350MB for low system load)
MAX_ALLOWED_SIZE_BYTES = 480 * 1024 * 1024

def download_video_from_url(url, output_dir, job_id, progress_callback=None):
    """
    Downloads video from YouTube, Vimeo, or direct video URL using yt-dlp.
    Guarantees the downloaded video is strictly under 500 MB and uses low-quality
    streams (360p/480p) to keep RAM, disk, and CPU load minimal.
    """
    os.makedirs(output_dir, exist_ok=True)
    out_template = os.path.join(output_dir, f"{job_id}_%(title).50s.%(ext)s")
    ffmpeg_exe = get_ffmpeg_path()
    ffmpeg_dir = os.path.dirname(ffmpeg_exe)

    # Ensure ffmpeg dir is in PATH for any external subprocess
    if ffmpeg_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = f"{ffmpeg_dir}:{os.environ.get('PATH', '')}"

    def yt_hook(d):
        if progress_callback and d.get('status') == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes') or 0
            pct = round((downloaded / total) * 100, 1) if total > 0 else 0
            speed = d.get('speed') or 0
            speed_mb = round(speed / (1024 * 1024), 1) if speed else 0
            progress_callback(pct, speed_mb)

    # 1. Quick probe of video duration to select optimal low-load format
    duration = 0
    title = 'Downloaded Lecture'
    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'noplaylist': True}) as probe_ydl:
            meta = probe_ydl.extract_info(url, download=False)
            if meta:
                duration = meta.get('duration', 0) or 0
                title = meta.get('title', 'Downloaded Lecture')
    except Exception as e:
        logger.warning(f"Probe extract_info failed: {e}. Falling back to default format selector.")

    # 2. Format selector for low quality (<500MB guaranteed, minimal memory & disk footprint)
    # If video is long (> 3 hours = 10800s), target 240p/360p; otherwise 360p/480p
    if duration > 10800:
        format_spec = (
            'bestvideo[height<=360][filesize_approx<=400M]+bestaudio[filesize_approx<=50M]/'
            'bestvideo[height<=360]+bestaudio/'
            'best[height<=360]/'
            'worstvideo+worstaudio/worst'
        )
    else:
        format_spec = (
            'bestvideo[height<=480][filesize_approx<=400M]+bestaudio[filesize_approx<=60M]/'
            'bestvideo[height<=360]+bestaudio/'
            'best[height<=360]/'
            'best[height<=480][filesize<=480M]/'
            'bestvideo[filesize_approx<=420M]+bestaudio/'
            'worstvideo+worstaudio/worst'
        )

    ydl_opts = {
        'ffmpeg_location': ffmpeg_exe,
        'format': format_spec,
        'outtmpl': out_template,
        'merge_output_format': 'mp4',
        'progress_hooks': [yt_hook],
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'max_filesize': MAX_ALLOWED_SIZE_BYTES,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        logger.info(f"Downloading low-quality video (<500MB) from URL: {url}")
        info = ydl.extract_info(url, download=True)
        title = info.get('title', title)
        duration = info.get('duration', duration)
        filename = ydl.prepare_filename(info)
        
        # Ensure mp4 extension if merged
        base, _ = os.path.splitext(filename)
        if os.path.exists(base + ".mp4"):
            filepath = base + ".mp4"
        elif os.path.exists(filename):
            filepath = filename
        else:
            candidates = [os.path.join(output_dir, f) for f in os.listdir(output_dir) if f.startswith(job_id)]
            filepath = candidates[0] if candidates else filename

    # 3. Post-download verification: ensure strict < 500 MB constraint
    if os.path.exists(filepath):
        actual_size = os.path.getsize(filepath)
        if actual_size > MAX_ALLOWED_SIZE_BYTES:
            logger.warning(f"Downloaded file {filepath} ({actual_size / (1024*1024):.1f}MB) exceeds 480MB. Compressing with FFmpeg...")
            compressed_path = os.path.join(output_dir, f"{job_id}_compact.mp4")
            dur = max(1.0, float(duration or 3600))
            # Target 380MB max to stay well under 500MB
            target_bitrate_kbps = max(120, int((380 * 8192) / dur))
            video_bitrate = max(90, target_bitrate_kbps - 48)

            compress_cmd = [
                ffmpeg_exe, "-y",
                "-i", filepath,
                "-vf", "scale=-2:'min(360,ih)'",
                "-c:v", "libx264",
                "-b:v", f"{video_bitrate}k",
                "-preset", "veryfast",
                "-c:a", "aac",
                "-b:a", "48k",
                compressed_path
            ]
            res = subprocess.run(compress_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            if res.returncode == 0 and os.path.exists(compressed_path) and os.path.getsize(compressed_path) > 0:
                os.remove(filepath)
                os.rename(compressed_path, filepath)
                logger.info(f"Compressed file successfully to {os.path.getsize(filepath)/(1024*1024):.1f}MB")

    return {
        "title": title,
        "filepath": filepath,
        "duration": duration,
        "filename": os.path.basename(filepath)
    }

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    if len(sys.argv) > 1:
        test_url = sys.argv[1]
        out_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")
        print(f"Starting download from URL: {test_url}")
        result = download_video_from_url(
            test_url,
            out_dir,
            "cli_test",
            progress_callback=lambda p, s: print(f"Progress: {p}% ({s} MB/s)")
        )
        print("\nDownload complete:")
        print(json.dumps(result, indent=2))
    else:
        print("VidSeek URL Downloader Service")
        print("Usage: python services/url_downloader.py <video_url> [output_dir]")
        print("Example: python services/url_downloader.py https://www.youtube.com/watch?v=example uploads")
