# VidSeek 🎥🔍

VidSeek is an intelligent video processing and learning platform that transcribes videos, generates automated chapters, enables semantic search across timestamps, produces quizzes, and offers interactive lecture study notes.
<img width="1440" height="900" alt="Screenshot 2026-09-27 at 1 03 02 AM" src="https://github.com/user-attachments/assets/bf752a54-1582-48cd-b16c-5b8f3f858689" />

## Features

- 🎬 **Video Processing & Chapters**: Automatic audio extraction, thumbnail generation, and chapter breakdown with FFmpeg.
- 🎙️ **Speech-to-Text**: Fast audio transcription powered by `faster-whisper`.
- 🔎 **Semantic Search & Video Q&A**: Search through video transcripts and ask questions with timestamped jump points.
- 📝 **Lecture Notes & Flashcards**: Automated synthesis of high-yield study notes.
- 🎯 **Quiz Generator**: Topic-level and lecture-wide interactive quiz generation.
- 🌐 **Modern Web UI**: Clean interface built with Flask, Vanilla CSS, and responsive JavaScript.

## Tech Stack

- **Backend**: Python 3.12, Flask, Flask-CORS
- **Audio/Video**: FFmpeg (`imageio-ffmpeg`), `yt-dlp`
- **Transcription**: `faster-whisper`
- **NLP / ML**: `scikit-learn`, `numpy`
- **Database**: SQLite (`learning.db`)
- **Frontend**: HTML5, Vanilla CSS, JavaScript

## Getting Started

### 1. Prerequisites
- Python 3.10+
- FFmpeg installed or configured via `imageio-ffmpeg`

### 2. Installation
```bash
git clone https://github.com/<your-username>/VidSeek.git
cd VidSeek

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Run the Application
```bash
python app.py
```
Open your browser at [http://127.0.0.1:5000](http://127.0.0.1:5000).

## Tests
```bash
pytest
```
