import os
import sys
import re
import json
import logging
import shutil
import tempfile
import subprocess
import yt_dlp
import platform

# Ensure root directory is on sys.path if run directly as a script
if __package__ is None or __package__ == "":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.video_processor import get_ffmpeg_path

logger = logging.getLogger(__name__)

# Strict limit to guarantee video stays under 500 MB (target ~50MB to 350MB for low system load)
MAX_ALLOWED_SIZE_BYTES = 480 * 1024 * 1024

# Realistic User-Agent to avoid YouTube bot detection
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

def _get_cookie_file():
    """
    Finds and returns the path to a writable cookies.txt file.
    Priority:
      1. /etc/secrets/cookies.txt (Render native Secret File location -> copied to writable /tmp/cookies.txt)
      2. YOUTUBE_COOKIES environment variable (copied to /tmp/cookies.txt)
      3. cookies.txt in current directory or project root
      4. YOUTUBE_COOKIES_TEXT or YOUTUBE_COOKIES_BASE64 written to /tmp/cookies.txt
    """
    import base64

    writable_cookie = "/tmp/cookies.txt" if os.path.exists("/tmp") else os.path.join(tempfile.gettempdir(), "cookies.txt")

    # 1. Render native Secret File path (Render mounts /etc/secrets as read-only, copy to /tmp)
    render_secret_path = "/etc/secrets/cookies.txt"
    if os.path.exists(render_secret_path) and os.path.getsize(render_secret_path) > 0:
        try:
            shutil.copyfile(render_secret_path, writable_cookie)
            logger.info(f"Copied read-only Render secret {render_secret_path} -> writable {writable_cookie}")
            return writable_cookie
        except Exception as e:
            logger.warning(f"Could not copy {render_secret_path} to {writable_cookie}: {e}")
            return render_secret_path

    # 2. Check for a cookies.txt file via YOUTUBE_COOKIES env var
    cookie_file = os.environ.get("YOUTUBE_COOKIES", "").strip()
    if cookie_file and os.path.exists(cookie_file) and os.path.getsize(cookie_file) > 0:
        try:
            shutil.copyfile(cookie_file, writable_cookie)
            logger.info(f"Copied {cookie_file} -> writable {writable_cookie}")
            return writable_cookie
        except Exception:
            return cookie_file

    # 3. Check for cookies.txt in project root or current working directory
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        os.path.join(project_root, "cookies.txt"),
        os.path.abspath("cookies.txt"),
        "cookies.txt"
    ]
    for p in candidates:
        if os.path.exists(p) and os.path.getsize(p) > 0:
            logger.info(f"Using cookies file: {p}")
            return p

    # 4. Inline cookie content passed via environment variable (Render dashboard)
    cookie_text = os.environ.get("YOUTUBE_COOKIES_TEXT", "").strip()
    cookie_b64 = os.environ.get("YOUTUBE_COOKIES_BASE64", "").strip()
    if cookie_b64 and not cookie_text:
        try:
            cookie_text = base64.b64decode(cookie_b64).decode("utf-8", errors="replace")
        except Exception as e:
            logger.warning(f"Failed to decode YOUTUBE_COOKIES_BASE64: {e}")

    if cookie_text:
        try:
            with open(writable_cookie, "w", encoding="utf-8") as f:
                f.write(cookie_text)
            logger.info(f"Using cookies generated from environment variable at: {writable_cookie}")
            return writable_cookie
        except Exception as e:
            logger.warning(f"Failed to write cookies from env to {writable_cookie}: {e}")

    return None


def _get_cookie_opts():
    """
    Build yt-dlp cookie options.
    If a cookies.txt file exists (e.g. /etc/secrets/cookies.txt -> /tmp/cookies.txt), uses it.
    Otherwise attempts local browser cookie extraction on dev machines.
    """
    cookie_file = _get_cookie_file()
    if cookie_file:
        return {'cookiefile': cookie_file}

    # Browser cookie extraction (local dev machines only)
    browser_map = {
        "chrome":   ["google-chrome", "google-chrome-stable", "chrome"],
        "firefox":  ["firefox"],
        "safari":   ["safari"],            # macOS only
        "edge":     ["microsoft-edge", "msedge"],
        "brave":    ["brave-browser", "brave"],
        "chromium": ["chromium", "chromium-browser"],
        "opera":    ["opera"],
    }

    if platform.system() == "Darwin":
        candidates = ["chrome", "firefox", "safari", "edge", "brave"]
    elif platform.system() == "Windows":
        candidates = ["chrome", "firefox", "edge", "brave", "opera"]
    else:
        candidates = ["chrome", "firefox", "chromium", "brave", "edge"]

    for browser in candidates:
        binaries = browser_map.get(browser, [browser])
        found = any(shutil.which(b) for b in binaries)

        if not found and platform.system() == "Darwin":
            mac_apps = {
                "chrome":  "/Applications/Google Chrome.app",
                "firefox": "/Applications/Firefox.app",
                "safari":  "/Applications/Safari.app",
                "edge":    "/Applications/Microsoft Edge.app",
                "brave":   "/Applications/Brave Browser.app",
            }
            found = os.path.isdir(mac_apps.get(browser, ""))

        if not found:
            continue

        try:
            test_opts = {
                'quiet': True,
                'no_warnings': True,
                'cookiesfrombrowser': (browser,),
                'skip_download': True,
            }
            with yt_dlp.YoutubeDL(test_opts) as ydl:
                ydl.extract_info("https://www.youtube.com/watch?v=BaW_jenozKc", download=False)
            logger.info(f"Using cookies from browser: {browser}")
            return {'cookiesfrombrowser': (browser,)}
        except Exception as e:
            logger.debug(f"Browser '{browser}' cookie extraction failed: {e}")
            continue

    logger.warning("No YouTube cookies available. Set /etc/secrets/cookies.txt in Render for best reliability.")
    return {}


def download_video_from_url(url, output_dir, job_id, progress_callback=None):
    """
    Downloads video from YouTube, Vimeo, or direct video URL using yt-dlp.
    Guarantees the downloaded video is strictly under 500 MB and uses
    efficient formats (360p/480p/720p) to keep RAM, disk, and CPU load minimal.
    """
    os.makedirs(output_dir, exist_ok=True)
    out_template = os.path.join(output_dir, f"{job_id}_%(id)s.%(ext)s")
    
    # Ensure FFmpeg and Deno are in PATH
    ffmpeg_exe = get_ffmpeg_path()
    ffmpeg_dir = os.path.dirname(ffmpeg_exe)
    deno_dirs = [
        os.path.expanduser("~/.deno/bin"),
        os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".deno", "bin")),
        "/root/.deno/bin",
        "/opt/render/.deno/bin"
    ]
    curr_path = os.environ.get("PATH", "")
    new_paths = [d for d in [ffmpeg_dir] + deno_dirs if os.path.exists(d) and d not in curr_path]
    if new_paths:
        os.environ["PATH"] = f"{':'.join(new_paths)}:{curr_path}"

    def yt_hook(d):
        if progress_callback and d.get('status') == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes') or 0
            pct = round((downloaded / total) * 100, 1) if total > 0 else 0
            speed = d.get('speed') or 0
            speed_mb = round(speed / (1024 * 1024), 1) if speed else 0
            progress_callback(pct, speed_mb)

    # 1. Verify cookies file and copy to writable /tmp location
    # Render mounts /etc/secrets/* as READ-ONLY — yt-dlp must not write back to it
    SOURCE_COOKIES = "/etc/secrets/cookies.txt"
    WRITABLE_COOKIES = "/tmp/vidseek_cookies.txt"

    if os.path.exists(SOURCE_COOKIES):
        shutil.copyfile(SOURCE_COOKIES, WRITABLE_COOKIES)
        logger.info("Copied Render secret cookies -> %s", WRITABLE_COOKIES)
    else:
        # Fallback: try dynamic cookie resolution (local dev / env var)
        fallback = _get_cookie_file()
        if fallback:
            shutil.copyfile(fallback, WRITABLE_COOKIES)
            logger.info("Copied fallback cookies %s -> %s", fallback, WRITABLE_COOKIES)
        else:
            raise RuntimeError(
                "YouTube cookies file not found at /etc/secrets/cookies.txt. "
                "Please add it as a Secret File in your Render dashboard."
            )

    logger.info("YouTube cookies ready at: %s", WRITABLE_COOKIES)

    # Extended player client list — tv_embedded bypasses consent/reload gate on server IPs
    _EXTRACTOR_ARGS = {
        'youtube': {
            'player_client': ['tv_embedded', 'android', 'ios', 'mweb', 'web'],
        }
    }

    # 2. Quick probe of video duration
    duration = 0
    title = 'Downloaded Lecture'
    try:
        probe_opts = {
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'cookiefile': WRITABLE_COOKIES,
            'cachedir': '/tmp/yt-dlp-cache',
            'http_headers': {'User-Agent': _USER_AGENT},
            'extractor_args': _EXTRACTOR_ARGS,
        }
        with yt_dlp.YoutubeDL(probe_opts) as probe_ydl:
            meta = probe_ydl.extract_info(url, download=False)
            if meta:
                duration = meta.get('duration', 0) or 0
                title = meta.get('title', 'Downloaded Lecture')
    # 3. Dynamic format selector to stay under 480MB limit
    if duration > 3600:  # > 1 hour -> 360p max
        format_spec = 'bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360][ext=mp4]/best[height<=360]'
    elif duration > 1800:  # > 30 mins -> 480p max
        format_spec = 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best[height<=480]'
    else:
        format_spec = 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]'

    ydl_opts = {
        'cookiefile': WRITABLE_COOKIES,
        'cachedir': '/tmp/yt-dlp-cache',
        'format': format_spec,
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'quiet': False,
        'no_warnings': False,
        'verbose': True,
        'listformats': True,
        'retries': 5,
        'fragment_retries': 5,
        'continuedl': True,
        'ffmpeg_location': ffmpeg_exe,
        'outtmpl': out_template,
        'progress_hooks': [yt_hook],
        'max_filesize': MAX_ALLOWED_SIZE_BYTES,
        'http_headers': {'User-Agent': _USER_AGENT},
        'extractor_args': _EXTRACTOR_ARGS,
        'sleep_interval': 2,
        'max_sleep_interval': 5,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"Downloading video from URL: {url} (cookiefile: {WRITABLE_COOKIES})")

            info = ydl.extract_info(url, download=True)
            title = info.get('title', title)
            duration = info.get('duration', duration)
            
            # Robust file discovery using glob
            import glob
            files = []
            for pattern in [os.path.join(output_dir, f"{job_id}_*")]:
                files.extend(glob.glob(pattern))

            # Ignore temporary/partial files
            files = [
                f for f in files
                if not f.endswith((".part", ".ytdl")) and os.path.isfile(f)
            ]

            if not files:
                raise RuntimeError(
                    "yt-dlp finished but no downloaded video file was found. "
                    "This usually means the download was aborted (e.g. file size exceeded 480MB limit)."
                )

            # Select the largest media file
            filepath = max(files, key=os.path.getsize)


    except Exception as e:
        err_msg = str(e)
        if "Sign in to confirm you’re not a bot" in err_msg or "Sign in to confirm you're not a bot" in err_msg:
            raise RuntimeError(
                "YouTube bot detection triggered on server. "
                "Please configure YouTube cookies on Render by uploading /etc/secrets/cookies.txt "
                "or setting the 'YOUTUBE_COOKIES_TEXT' environment variable."
            ) from e
        elif "The page needs to be reloaded" in err_msg or "needs to be reloaded" in err_msg:
            raise RuntimeError(
                "YouTube returned a consent/reload page — the server IP may be temporarily flagged. "
                "Providing fresh YouTube cookies via the 'YOUTUBE_COOKIES_TEXT' environment variable "
                "will resolve this. Export cookies using the 'Get cookies.txt LOCALLY' browser extension."
            ) from e
        elif "Requested format is not available" in err_msg:
            raise RuntimeError(
                "YouTube format extraction failed. Make sure valid YouTube cookies are provided "
                "under /etc/secrets/cookies.txt in the Render dashboard."
            ) from e
        raise

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
