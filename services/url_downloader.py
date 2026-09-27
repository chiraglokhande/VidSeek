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
    os.makedirs(output_dir, exist_ok=True)

    output_template = os.path.join(
        output_dir,
        f"{job_id}.%(ext)s"
    )

    print("=" * 70)
    print("YT-DLP DOWNLOAD START")
    print("URL:", url)
    print("DIRECTORY:", output_dir)
    print("OUTPUT TEMPLATE:", output_template)
    print("=" * 70)

    # Render Secret Cookie Setup (Direct Path for yt-dlp)
    cookie_path = "/etc/secrets/cookies.txt"
    
    ydl_opts = {
        "outtmpl": output_template,

        # robust fallback format: prefer mp4, allow merging if no single file is available
        "format": "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
        "merge_output_format": "mp4",

        "noplaylist": True,
        "quiet": False,
        "no_warnings": False,
        "retries": 3,
        "fragment_retries": 3,
        "continuedl": True,
        "nopart": False,
        
        # Pass the Render Secret file directly if it exists, or fallback to local
        "cookiefile": cookie_path if os.path.exists(cookie_path) else (
            "/tmp/vidseek_cookies.txt" if os.path.exists("/tmp/vidseek_cookies.txt") else None
        ),
        
        "cachedir": "/tmp/yt-dlp-cache",
        "ffmpeg_location": get_ffmpeg_path(),
        
        # YouTube client handling & PO-token-compatible setup
        # yt-dlp uses plugins like bgutil-ytdlp-pot-provider automatically when installed.
        "extractor_args": {
            "youtube": {
                # Use a mix of clients that bypass bot checks, combined with PO Tokens for the web client if the plugin provides them
                "player_client": ["ios", "android", "web"]
            }
        },
    }

    title = "Video"
    duration = 0

    # Clean up any partial files from previous attempts
    import glob
    for f in glob.glob(os.path.join(output_dir, f"{job_id}.*")):
        try:
            os.remove(f)
        except OSError:
            pass

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            title = info.get("title", title)
            duration = info.get("duration", duration)

            print("\nYT-DLP INFO")
            print("ID:", info.get("id"))
            print("TITLE:", title)
            print("EXT:", info.get("ext"))
            print("FORMAT:", info.get("format"))
            print("SIZE:", info.get("filesize"))
            print("REQUESTED DOWNLOADS:", info.get("requested_downloads"))
            
    except Exception as e:
        print("\nYT-DLP EXCEPTION:", str(e))
        raise RuntimeError(
            f"Unable to download YouTube video. Bot detection may be blocking the server.\n{str(e)}"
        )

    print("\nFILES AFTER DOWNLOAD:")

    all_files = []

    for root, dirs, files in os.walk(output_dir):
        for filename in files:
            full_path = os.path.join(root, filename)

            try:
                size = os.path.getsize(full_path)
            except OSError:
                size = 0

            print(
                f"FILE: {repr(full_path)} | "
                f"SIZE: {size / (1024 * 1024):.2f} MB"
            )

            all_files.append(full_path)

    print("=" * 70)

    # Ignore temporary files
    import glob
    media_files = [
        f for f in all_files
        if not f.endswith(".part")
        and not f.endswith(".ytdl")
        and not f.endswith(".json")
        and os.path.basename(f).startswith(job_id)
    ]

    if not media_files:
        raise RuntimeError(
            "yt-dlp completed, but no final media file exists. "
            "Check the Render logs above for the actual yt-dlp output."
        )

    downloaded_file = max(
        media_files,
        key=os.path.getsize
    )

    size_mb = os.path.getsize(downloaded_file) / (1024 * 1024)
    print("SELECTED FILE:", downloaded_file)
    print(f"Final file size: {size_mb:.2f} MB")
    
    if size_mb > 480:
        os.remove(downloaded_file)
        raise RuntimeError(
            f"Downloaded video is {size_mb:.1f} MB, "
            "which exceeds the 480 MB limit."
        )

    return {
        "title": title,
        "filepath": downloaded_file,
        "duration": duration,
        "filename": os.path.basename(downloaded_file)
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
