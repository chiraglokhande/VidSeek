import os
import unittest
from services.video_processor import (
    get_video_info,
    extract_audio,
    extract_thumbnail,
    generate_all_chapter_videos
)
from services.transcriber import transcribe_audio
from services.topic_detector import generate_chapters, generate_lecture_notes
from services.search_engine import search_video, answer_video_question

class TestVidSeekPipeline(unittest.TestCase):
    def test_end_to_end(self):
        video_path = "sample_data/java_lecture_sample.mp4"
        self.assertTrue(os.path.exists(video_path), "Sample video should exist")

        # 1. Video Info
        info = get_video_info(video_path)
        self.assertGreater(info["duration"], 10.0)
        print(f"✓ Video info: duration={info['duration_formatted']}, res={info['width']}x{info['height']}")

        # 2. Audio Extraction
        test_dir = "sample_data/test_run"
        os.makedirs(test_dir, exist_ok=True)
        audio_p = os.path.join(test_dir, "test_audio.wav")
        extract_audio(video_path, audio_p)
        self.assertTrue(os.path.exists(audio_p))
        print("✓ Audio extracted via FFmpeg")

        # 3. Transcribe
        res = transcribe_audio(audio_p, model_size="tiny")
        self.assertGreater(len(res["segments"]), 0)
        print(f"✓ Transcribed {len(res['segments'])} segments via Whisper AI")

        # 4. Topic Detection
        chapters = generate_chapters(res["segments"], info["duration"])
        self.assertGreater(len(chapters), 0)
        print(f"✓ Detected {len(chapters)} chapters automatically:")
        for c in chapters:
            print(f"   - Chapter {c['id']}: {c['title']} ({c['start_formatted']} - {c['end_formatted']})")

        # 5. Video Splitting
        sliced_chaps = generate_all_chapter_videos(video_path, chapters, test_dir, "test_job")
        self.assertEqual(len(sliced_chaps), len(chapters))
        for sc in sliced_chaps:
            vid_file = os.path.join(test_dir, sc["video_filename"])
            self.assertTrue(os.path.exists(vid_file), f"Sliced file {vid_file} should exist")
        print(f"✓ Sliced {len(sliced_chaps)} standalone topic video files via FFmpeg")

        # 6. Search
        search_res = search_video("loops", res["segments"], chapters)
        results = search_res["results"] if isinstance(search_res, dict) else search_res
        self.assertGreater(len(results), 0)
        print(f"✓ Search query 'loops' found hit at: {results[0]['timestamp_formatted']}")

        # 7. Q&A
        ans = answer_video_question("What is polymorphism?", res["segments"], chapters)
        self.assertIn("polymorphism", ans["answer"].lower())
        print(f"✓ Q&A answered with timestamp citation: {ans['timestamp_formatted']}")

if __name__ == "__main__":
    unittest.main()
