import os
import subprocess
import shutil
from services.video_processor import get_ffmpeg_path

def create_sample_lecture(output_video_path="sample_data/java_lecture_sample.mp4"):
    """
    Creates a real educational video lecture sample with real spoken voiceover
    covering 4 chapters:
    1. Introduction to Java (0 - 15s)
    2. Java Variables and Data Types (15 - 30s)
    3. Loops in Java (30 - 45s)
    4. OOP Concepts and Polymorphism (45 - 60s)
    """
    os.makedirs(os.path.dirname(output_video_path), exist_ok=True)
    ffmpeg_exe = get_ffmpeg_path()

    topics = [
        {
            "num": 1,
            "title": "Introduction to Java Programming",
            "bg_color": "#1e293b",
            "accent": "#38bdf8",
            "text": "Welcome to Java programming. In this masterclass we will learn the essential core fundamentals of Java including syntax, compiler execution, and building robust enterprise applications."
        },
        {
            "num": 2,
            "title": "Variables and Data Types",
            "bg_color": "#0f172a",
            "accent": "#818cf8",
            "text": "Now let's talk about variables and data types. In Java, variables hold memory values. We have primitives like integer, float, boolean, and non-primitives like strings and arrays."
        },
        {
            "num": 3,
            "title": "Loops and Iterations",
            "bg_color": "#111827",
            "accent": "#34d399",
            "text": "Moving on to loops in Java. Loops allow us to execute a block of statements repeatedly. We use for loops, while loops, and do while loops for traversing data."
        },
        {
            "num": 4,
            "title": "OOP Concepts and Polymorphism",
            "bg_color": "#18181b",
            "accent": "#fbbf24",
            "text": "Next topic is OOP concepts and polymorphism. Polymorphism allows an object to take many forms. We achieve runtime polymorphism through method overriding and inheritance."
        }
    ]

    temp_dir = "sample_data/temp_clips"
    os.makedirs(temp_dir, exist_ok=True)
    clip_files = []

    for idx, t in enumerate(topics):
        audio_file = os.path.join(temp_dir, f"audio_{idx}.aiff")
        wav_file = os.path.join(temp_dir, f"audio_{idx}.wav")
        clip_file = os.path.join(temp_dir, f"clip_{idx}.mp4")

        # Generate audio using macOS say
        subprocess.run(["/usr/bin/say", "-v", "Samantha", "-o", audio_file, t["text"]], check=True)
        # Convert to standard wav
        subprocess.run([ffmpeg_exe, "-y", "-i", audio_file, "-ar", "16000", "-ac", "1", wav_file], check=True)

        # Get audio duration
        dur_cmd = [ffmpeg_exe, "-i", wav_file]
        res = subprocess.run(dur_cmd, stderr=subprocess.PIPE, text=True)
        import re
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", res.stderr)
        if m:
            dur = float(m.group(1))*3600 + float(m.group(2))*60 + float(m.group(3))
        else:
            dur = 12.0
        dur += 1.0 # 1s buffer

        # Generate video clip with color background and rendered title text
        # Using lavfi color source and drawtext
        title_text = t["title"].replace("'", "")
        sub_text = f"Chapter {t['num']} - VidSeek Lecture"
        
        # Simple aesthetic slide rendering with ffmpeg
        vf_filter = (
            f"drawbox=y=0:color={t['accent']}@0.2:width=iw:height=8:t=fill,"
            f"drawtext=text='{sub_text}':fontcolor=white@0.6:fontsize=24:x=60:y=120,"
            f"drawtext=text='{title_text}':fontcolor=white:fontsize=48:x=60:y=170,"
            f"drawtext=text='VidSeek AI Educational Masterclass':fontcolor=white@0.4:fontsize=20:x=60:y=h-80"
        )

        video_gen_cmd = [
            ffmpeg_exe, "-y",
            "-f", "lavfi",
            "-i", f"color=c={t['bg_color']}:s=1280x720:d={dur}:r=25",
            "-i", wav_file,
            "-vf", vf_filter,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-shortest",
            clip_file
        ]
        
        # If font / drawtext is available in ffmpeg, use it, else fallback to clean solid color slide
        try:
            subprocess.run(video_gen_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError:
            # Fallback without drawtext if fontconfig isn't linked
            fallback_cmd = [
                ffmpeg_exe, "-y",
                "-f", "lavfi",
                "-i", f"color=c={t['bg_color']}:s=1280x720:d={dur}:r=25",
                "-i", wav_file,
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-shortest",
                clip_file
            ]
            subprocess.run(fallback_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

        clip_files.append(clip_file)

    # Concat all clips into one master video
    concat_list_file = os.path.join(temp_dir, "concat.txt")
    with open(concat_list_file, "w") as f:
        for cf in clip_files:
            abs_p = os.path.abspath(cf)
            f.write(f"file '{abs_p}'\n")

    concat_cmd = [
        ffmpeg_exe, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_list_file,
        "-c", "copy",
        output_video_path
    ]
    subprocess.run(concat_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    # Clean up temp
    shutil.rmtree(temp_dir, ignore_errors=True)
    print(f"Sample video created successfully at: {output_video_path}")
    return output_video_path

if __name__ == "__main__":
    create_sample_lecture()
