import unittest
import os
import json
from app import app
from services.temporal_event_detector import BiLSTMEventDetector, detect_temporal_events
from services.anomaly_detector import AutoencoderAnomalyModel, detect_anomalies
from services.temporal_qa import answer_temporal_question, generate_temporal_mcqs, parse_time_from_text, parse_time_range_from_text
import numpy as np

class TestTemporalFeatures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()
        cls.sample_job_id = "sample_808e"
        cls.sample_video_path = os.path.abspath("sample_data/java_lecture_sample.mp4")

    def test_bilstm_architecture(self):
        """Verify BiLSTM event detector model initialization and forward pass"""
        model = BiLSTMEventDetector(input_dim=16, hidden_dim=32, num_classes=5)
        # Random batch of 20 timesteps
        x = np.random.randn(20, 16).astype(np.float32)
        class_probs, boundary_probs, hidden_states = model.forward(x)
        self.assertEqual(class_probs.shape, (20, 5))
        self.assertEqual(boundary_probs.shape, (20,))
        self.assertEqual(hidden_states.shape, (20, 64))
        # Probabilities should sum to 1.0 along class dimension
        np.testing.assert_allclose(np.sum(class_probs, axis=1), np.ones(20), atol=1e-5)

    def test_detect_temporal_events(self):
        """Verify detect_temporal_events pipeline with sample segments"""
        segments = [
            {"id": 0, "start": 0.0, "end": 10.0, "text": "Welcome to Java programming and object oriented fundamentals."},
            {"id": 1, "start": 10.0, "end": 22.0, "text": "Let us examine class declarations and method signatures."},
            {"id": 2, "start": 22.0, "end": 35.0, "text": "Now moving to for loops, while loops, and conditional branching."},
            {"id": 3, "start": 35.0, "end": 41.5, "text": "That concludes our introduction to syntax and iteration."}
        ]
        result = detect_temporal_events(self.sample_video_path, segments, total_duration=41.5)
        self.assertIsInstance(result, dict)
        self.assertIn("events", result)
        self.assertIn("model_type", result)
        events = result["events"]
        self.assertGreater(len(events), 0)
        for ev in events:
            self.assertIn("start", ev)
            self.assertIn("end", ev)
            self.assertIn("start_formatted", ev)
            self.assertIn("end_formatted", ev)
            self.assertIn("description", ev)
            self.assertIn("confidence", ev)
            self.assertIn("category", ev)
            self.assertGreaterEqual(ev["end"], ev["start"])
            self.assertGreaterEqual(ev["confidence"], 0.0)
            self.assertLessEqual(ev["confidence"], 1.0)

    def test_autoencoder_architecture(self):
        """Verify Autoencoder anomaly model initialization, forward pass, and reconstruction error"""
        model = AutoencoderAnomalyModel(input_dim=32, latent_dim=8)
        x = np.random.randn(15, 32).astype(np.float32)
        x_hat, errors, diff = model.forward(x)
        self.assertEqual(x_hat.shape, (15, 32))
        self.assertEqual(errors.shape, (15,))
        self.assertEqual(diff.shape, (15, 32))
        self.assertTrue(np.all(errors >= 0))

    def test_detect_anomalies(self):
        """Verify detect_anomalies pipeline output structure and objective terminology"""
        segments = [
            {"id": 0, "start": 0.0, "end": 20.0, "text": "Standard intro topic."},
            {"id": 1, "start": 20.0, "end": 41.0, "text": "Syntax and looping demonstration."}
        ]
        res = detect_anomalies(self.sample_video_path, segments, total_duration=41.5)
        self.assertIn("anomalies", res)
        self.assertIn("timeline", res)
        self.assertIn("summary", res)
        self.assertIn("baseline_error", res["summary"])
        self.assertIn("threshold", res["summary"])
        self.assertIn("total_segments_analyzed", res["summary"])

        for anom in res["anomalies"]:
            self.assertIn("timestamp", anom)
            self.assertIn("score", anom)
            self.assertIn("severity", anom)
            self.assertIn("explanation", anom)
            # Must not use alarmist/danger terminology
            lower_desc = anom["explanation"].lower()
            self.assertNotIn("dangerous", lower_desc)
            self.assertNotIn("malicious", lower_desc)

    def test_temporal_qa_resolution(self):
        """Verify temporal QA handles direct timestamp, before, after, and range questions"""
        events = [
            {"start": 0.0, "end": 10.0, "start_time": "00:00", "end_time": "00:10", "description": "Introduction to Java concepts", "confidence": 0.92},
            {"start": 10.0, "end": 22.0, "start_time": "00:10", "end_time": "00:22", "description": "Class declaration and method signature analysis", "confidence": 0.88},
            {"start": 22.0, "end": 35.0, "start_time": "00:22", "end_time": "00:35", "description": "Loop syntax and conditional branching demonstration", "confidence": 0.95},
            {"start": 35.0, "end": 41.5, "start_time": "00:35", "end_time": "00:41", "description": "Wrap up and conclusion of basic syntax", "confidence": 0.85}
        ]
        
        # Direct timestamp query
        ans1 = answer_temporal_question("What happened around 00:15?", events)
        self.assertIsNotNone(ans1)
        self.assertIn("00:10", ans1["answer"])
        self.assertIn("Class declaration", ans1["answer"])

        # "Before" temporal relative query
        ans2 = answer_temporal_question("What happened before the loop syntax demonstration?", events)
        self.assertIsNotNone(ans2)
        self.assertIn("Class declaration", ans2["answer"])

        # "After" temporal relative query
        ans3 = answer_temporal_question("What occurred after the class declaration?", events)
        self.assertIsNotNone(ans3)
        self.assertIn("Loop syntax", ans3["answer"])

    def test_generate_temporal_mcqs(self):
        """Verify MCQ generation grounded in detected temporal events"""
        events = [
            {"start": 0.0, "end": 12.0, "start_time": "00:00", "end_time": "00:12", "description": "Intro to Java", "category": "speech_lecture"},
            {"start": 12.0, "end": 24.0, "start_time": "00:12", "end_time": "00:24", "description": "Defining variables", "category": "screen_presentation"},
            {"start": 24.0, "end": 36.0, "start_time": "00:24", "end_time": "00:36", "description": "Running loops", "category": "screen_presentation"},
            {"start": 36.0, "end": 41.0, "start_time": "00:36", "end_time": "00:41", "description": "Summary", "category": "conclusion"}
        ]
        mcqs = generate_temporal_mcqs(events, count=3)
        self.assertGreaterEqual(len(mcqs), 1)
        for q in mcqs:
            self.assertEqual(len(q["options"]), 4)
            self.assertIn(q["correct_answer"], ["A", "B", "C", "D"])
            self.assertIn("explanation", q)
            self.assertIn("timestamp", q)
            self.assertIn("time_seconds", q)

    def test_api_temporal_endpoints(self):
        """Verify API endpoints return correct status codes and JSON contracts"""
        # 1. Temporal Events API
        res_ev = self.client.get(f"/api/video/{self.sample_job_id}/temporal-events")
        self.assertEqual(res_ev.status_code, 200)
        data_ev = res_ev.get_json()
        self.assertTrue(data_ev.get("success"))
        self.assertIn("events", data_ev)
        self.assertIsInstance(data_ev["events"], list)

        # 2. Anomalies API
        res_anom = self.client.get(f"/api/video/{self.sample_job_id}/anomalies")
        self.assertEqual(res_anom.status_code, 200)
        data_anom = res_anom.get_json()
        self.assertTrue(data_anom.get("success"))
        self.assertIn("anomalies", data_anom)
        self.assertIn("timeline", data_anom)

        # 3. Temporal QA API
        res_qa = self.client.post(
            f"/api/video/{self.sample_job_id}/temporal-qa",
            data=json.dumps({"question": "What happens around 00:25?"}),
            content_type="application/json"
        )
        self.assertEqual(res_qa.status_code, 200)
        data_qa = res_qa.get_json()
        self.assertTrue(data_qa.get("success"))
        self.assertIn("answer", data_qa)

        # 4. Temporal Quiz API
        res_quiz = self.client.get(f"/api/quiz/temporal/{self.sample_job_id}")
        self.assertEqual(res_quiz.status_code, 200)
        data_quiz = res_quiz.get_json()
        self.assertTrue(data_quiz.get("success"))
        self.assertIn("quiz", data_quiz)
        self.assertIn("questions", data_quiz["quiz"])

        # 5. Existing Search API with temporal enhancement
        res_search = self.client.post(
            "/api/search",
            data=json.dumps({"job_id": self.sample_job_id, "query": "loops"}),
            content_type="application/json"
        )
        data_search = res_search.get_json()
        self.assertIn("results", data_search)
        self.assertIsInstance(data_search["results"], list)

if __name__ == "__main__":
    unittest.main()
