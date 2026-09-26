import os
import re
import subprocess
import json
import imageio_ffmpeg

def get_ffmpeg_path():
    """Return path to ffmpeg binary."""
    return imageio_ffmpeg.get_ffmpeg_exe()

def format_timestamp(seconds):
    """Format seconds into HH:MM:SS or MM:SS."""
    seconds = max(0, float(seconds))
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"

def parse_timestamp(timestamp_str):
    """Parse MM:SS or HH:MM:SS string to seconds."""
    parts = list(map(float, timestamp_str.strip().split(":")))
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    elif len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return float(parts[0])

def get_video_info(video_path):
    """Extract metadata including duration, resolution, size using ffmpeg output."""
    ffmpeg_exe = get_ffmpeg_path()
    cmd = [ffmpeg_exe, "-hide_banner", "-i", video_path]
    process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    output = process.stderr
    
    if "Invalid data found when processing input" in output or "No such file or directory" in output:
        raise ValueError(f"FFmpeg probe failed. File may be corrupted, incomplete, or not a video:\n{output[-1000:]}")

    duration = 0.0
    dur_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", output)
    if dur_match:
        hrs, mins, secs = dur_match.groups()
        duration = float(hrs) * 3600 + float(mins) * 60 + float(secs)

    width, height = 1280, 720
    res_match = re.search(r"Stream.*Video:.*,\s*(\d{3,5})x(\d{3,5})", output)
    if res_match:
        width, height = int(res_match.group(1)), int(res_match.group(2))

    size_bytes = os.path.getsize(video_path) if os.path.exists(video_path) else 0
    size_mb = round(size_bytes / (1024 * 1024), 2)

    return {
        "duration": duration,
        "duration_formatted": format_timestamp(duration),
        "width": width,
        "height": height,
        "size_bytes": size_bytes,
        "size_mb": size_mb,
        "filename": os.path.basename(video_path)
    }

def extract_audio(video_path, output_audio_path):
    """Extract 16kHz mono WAV audio for Whisper transcription."""
    ffmpeg_exe = get_ffmpeg_path()
    os.makedirs(os.path.dirname(output_audio_path), exist_ok=True)
    
    cmd = [
        ffmpeg_exe, "-y",
        "-hide_banner",
        "-loglevel", "error",
        "-i", video_path,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        output_audio_path
    ]
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"Audio extraction failed with code {result.returncode}:\n{result.stderr[-2000:]}")
    return output_audio_path

def extract_thumbnail(video_path, output_image_path, timestamp_sec=2.0):
    """Extract a thumbnail frame from video at specified second."""
    ffmpeg_exe = get_ffmpeg_path()
    os.makedirs(os.path.dirname(output_image_path), exist_ok=True)
    
    cmd = [
        ffmpeg_exe, "-y",
        "-ss", str(max(0.1, timestamp_sec)),
        "-i", video_path,
        "-vframes", "1",
        "-q:v", "2",
        output_image_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return output_image_path

def split_video_chapter(video_path, start_sec, end_sec, output_chapter_path):
    """
    Slice the video accurately between start_sec and end_sec.
    Uses ultra-fast stream copy (-c copy) which completes in ~0.2 seconds without re-encoding.
    Falls back to fast re-encoding if stream copy fails.
    """
    ffmpeg_exe = get_ffmpeg_path()
    os.makedirs(os.path.dirname(output_chapter_path), exist_ok=True)
    duration = max(0.5, end_sec - start_sec)
    
    # Try ultra-fast stream copy first (sub-second per chapter)
    copy_cmd = [
        ffmpeg_exe, "-y",
        "-ss", str(max(0.0, start_sec)),
        "-i", video_path,
        "-t", str(duration),
        "-c", "copy",
        "-avoid_negative_ts", "make_zero",
        "-movflags", "+faststart",
        output_chapter_path
    ]
    
    res = subprocess.run(copy_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if res.returncode == 0 and os.path.exists(output_chapter_path) and os.path.getsize(output_chapter_path) > 1000:
        return output_chapter_path

    # Fallback to veryfast re-encode only if stream copy wasn't viable
    fallback_cmd = [
        ffmpeg_exe, "-y",
        "-hide_banner",
        "-ss", str(max(0.0, start_sec)),
        "-i", video_path,
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "24",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        output_chapter_path
    ]
    result = subprocess.run(
        fallback_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg split fallback failed with code {result.returncode}:\n{result.stderr[-2000:]}")
    return output_chapter_path

def generate_all_chapter_videos(video_path, chapters, output_dir, job_id):
    """
    Iterate over detected chapters and split the video into standalone chapter files.
    Returns the enriched list of chapters with video URLs and thumbnails.
    """
    os.makedirs(output_dir, exist_ok=True)
    enriched = []
    
    for idx, chap in enumerate(chapters, 1):
        slug = re.sub(r'[^a-zA-Z0-9_-]', '_', chap["title"].lower()).strip('_')[:30]
        chap_filename = f"chapter_{idx:02d}_{slug}.mp4"
        thumb_filename = f"chapter_{idx:02d}_{slug}.jpg"
        
        chap_filepath = os.path.join(output_dir, chap_filename)
        thumb_filepath = os.path.join(output_dir, thumb_filename)
        
        start_sec = chap["start_time"]
        end_sec = chap["end_time"]
        
        # Split video
        split_video_chapter(video_path, start_sec, end_sec, chap_filepath)
        
        # Extract thumbnail slightly inside the chapter
        thumb_time = start_sec + min(2.0, (end_sec - start_sec) / 2)
        extract_thumbnail(video_path, thumb_filepath, timestamp_sec=thumb_time)
        
        size_mb = round(os.path.getsize(chap_filepath) / (1024 * 1024), 2) if os.path.exists(chap_filepath) else 0
        
        chap_copy = dict(chap)
        chap_copy["chapter_number"] = idx
        chap_copy["video_filename"] = chap_filename
        chap_copy["video_url"] = f"/api/video/{job_id}/chapter/{chap_filename}"
        chap_copy["thumbnail_url"] = f"/api/video/{job_id}/thumbnail/{thumb_filename}"
        chap_copy["size_mb"] = size_mb
        chap_copy["duration_formatted"] = format_timestamp(end_sec - start_sec)
        chap_copy["start_formatted"] = format_timestamp(start_sec)
        chap_copy["end_formatted"] = format_timestamp(end_sec)
        
        enriched.append(chap_copy)
        
    return enriched
