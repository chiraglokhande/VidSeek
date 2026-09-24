import os
import sys
import logging

# Ensure root directory is on sys.path if run directly
if __package__ is None or __package__ == "":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.video_processor import format_timestamp

logger = logging.getLogger(__name__)

_whisper_model = None

def get_whisper_model(model_size="base"):
    """
    Lazy load faster-whisper model.
    Uses 'base' or 'tiny' with int8 quantization for ultra-fast CPU/Metal performance.
    """
    global _whisper_model
    if _whisper_model is None:
        try:
            from faster_whisper import WhisperModel
            logger.info(f"Loading faster-whisper model: {model_size}")
            # Use int8 compute and 6 cpu threads for high-throughput transcription
            _whisper_model = WhisperModel(model_size, device="cpu", compute_type="int8", cpu_threads=6)
        except Exception as e:
            logger.warning(f"Could not load faster-whisper: {e}. Fallback to simulated/rule-based transcriber.")
            _whisper_model = None
    return _whisper_model

def transcribe_audio(audio_path, model_size="base", progress_callback=None):
    """
    Transcribe audio file into timestamped segments with optional live progress callback.
    Returns:
        {
            "segments": [
                {"id": 0, "start": 0.0, "end": 4.5, "text": "...", "start_formatted": "00:00", ...},
                ...
            ],
            "full_text": "...",
            "duration": total_seconds,
            "language": "en"
        }
    """
    model = get_whisper_model(model_size)
    segments_data = []
    full_text_pieces = []
    language = "en"
    duration = 0.0

    if model is not None and os.path.exists(audio_path):
        try:
            logger.info(f"Starting Whisper transcription on {audio_path}")
            segments, info = model.transcribe(
                audio_path,
                beam_size=1,
                word_timestamps=False,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500)
            )
            language = info.language
            duration = info.duration

            idx = 0
            for segment in segments:
                text = segment.text.strip()
                if not text:
                    continue
                segments_data.append({
                    "id": idx,
                    "start": round(segment.start, 2),
                    "end": round(segment.end, 2),
                    "text": text,
                    "start_formatted": format_timestamp(segment.start),
                    "end_formatted": format_timestamp(segment.end)
                })
                full_text_pieces.append(text)
                idx += 1

                if progress_callback and duration > 0:
                    try:
                        progress_callback(segment.end, duration)
                    except Exception:
                        pass

        except Exception as e:
            logger.error(f"Whisper transcription failed: {e}")
            raise e

    full_text = " ".join(full_text_pieces)
    return {
        "segments": segments_data,
        "full_text": full_text,
        "duration": duration,
        "language": language
    }
