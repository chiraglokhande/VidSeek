import os
import unittest
import json
from app import app
from services import learning_db
from services.quiz_generator import generate_topic_quiz, generate_full_lecture_quiz
from services.search_engine import answer_followup_question, simplify_answer_explanation

class TestVidSeekLearningSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()
        learning_db.init_db()
        cls.job_id = "sample_808e"

    def test_01_study_mode_video_endpoint(self):
        """Verify AI Study Mode video endpoint returns enriched topics, progress, and times."""
        res = self.client.get(f"/api/study/video/{self.job_id}")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("topics", data)
        self.assertIn("total_topics", data)
        self.assertIn("progress_pct", data)
        self.assertGreaterEqual(len(data["topics"]), 1)
        first_topic = data["topics"][0]
        self.assertIn("title", first_topic)
        self.assertIn("start_formatted", first_topic)
        self.assertIn("summary", first_topic)
        print(f"✓ Study Mode endpoint verified: {data['total_topics']} topics, progress={data['progress_pct']}%")

    def test_02_topic_quiz_generation(self):
        """Verify MCQ quiz generation produces grounded questions with explanations and timestamps."""
        res = self.client.get(f"/api/quiz/topic/{self.job_id}/1")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("questions", data)
        self.assertGreaterEqual(len(data["questions"]), 3)
        q = data["questions"][0]
        self.assertIn("question", q)
        self.assertIn("options", q)
        self.assertIn("correct_answer", q)
        self.assertIn("explanation", q)
        self.assertIn("timestamp_formatted", q)
        self.assertIn(q["correct_answer"], ["A", "B", "C", "D"])
        print(f"✓ Topic Quiz generated: {len(data['questions'])} questions grounded in video transcript")

    def test_03_full_lecture_quiz_generation(self):
        """Verify full lecture mastery quiz generation."""
        res = self.client.get(f"/api/quiz/full/{self.job_id}")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("questions", data)
        self.assertGreaterEqual(len(data["questions"]), 4)
        print(f"✓ Full Lecture Quiz generated: {len(data['questions'])} questions across all chapters")

    def test_04_quiz_submission_and_scoring(self):
        """Verify quiz answer evaluation, scoring, and persistence."""
        quiz_res = self.client.get(f"/api/quiz/topic/{self.job_id}/1")
        quiz_data = quiz_res.get_json()
        quiz_id = quiz_data["quiz_id"]
        questions = quiz_data["questions"]

        # Submit all correct answers
        answers = []
        for q in questions:
            answers.append({
                "question_id": q["id"],
                "selected_option": q["correct_answer"],
                "is_correct": True
            })

        sub_res = self.client.post("/api/quiz/submit", json={
            "quiz_id": quiz_id,
            "job_id": self.job_id,
            "topic_id": 1,
            "answers": answers
        })
        self.assertEqual(sub_res.status_code, 200)
        sub_data = sub_res.get_json()
        self.assertEqual(sub_data["score"], len(questions))
        self.assertEqual(sub_data["accuracy"], 100.0)
        print(f"✓ Quiz submission scored: {sub_data['score']}/{sub_data['total_questions']} (100% accuracy)")

    def test_05_topic_completion_toggle(self):
        """Verify manual topic completion endpoint."""
        res = self.client.post("/api/study/topic/complete", json={
            "job_id": self.job_id,
            "topic_id": 1,
            "completed": True
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "completed")
        print("✓ Topic completion toggled successfully")

    def test_06_watch_event_and_continue_learning(self):
        """Verify video heartbeat tracking and Continue Learning updates."""
        res = self.client.post("/api/learning/watch-event", json={
            "job_id": self.job_id,
            "topic_id": 1,
            "topic_title": "Introduction & Java Programming",
            "current_time": 18.2,
            "duration_watched": 10
        })
        self.assertEqual(res.status_code, 200)

        # Check Continue Learning on dashboard
        dash_res = self.client.get("/api/analytics/dashboard")
        self.assertEqual(dash_res.status_code, 200)
        dash_data = dash_res.get_json()
        self.assertIsNotNone(dash_data.get("continue_learning"))
        cont = dash_data["continue_learning"]
        self.assertEqual(cont["video_id"], self.job_id)
        self.assertGreaterEqual(cont["timestamp"], 18.0)
        print(f"✓ Watch event recorded. Continue Learning set to: {cont['topic_title']} at {cont['timestamp_formatted']}")

    def test_07_analytics_dashboard_kpis(self):
        """Verify Learning Analytics 6 KPIs and progress overview."""
        res = self.client.get("/api/analytics/dashboard")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("total_videos", data)
        self.assertIn("total_topics_completed", data)
        self.assertIn("overall_accuracy", data)
        self.assertIn("video_progress", data)
        self.assertIn("weekly_activity", data)
        print(f"✓ Analytics Dashboard verified: {data['total_videos']} videos, {data['overall_accuracy']}% accuracy")

    def test_08_weak_topic_detection(self):
        """Verify weak topic detection when accuracy < 60%."""
        # Submit a low score on topic 2
        quiz_res = self.client.get(f"/api/quiz/topic/{self.job_id}/2")
        quiz_data = quiz_res.get_json()
        quiz_id = quiz_data["quiz_id"]
        questions = quiz_data["questions"]

        # Intentionally select wrong options
        answers = []
        for q in questions:
            wrong_opt = "B" if q["correct_answer"] == "A" else "A"
            answers.append({
                "question_id": q["id"],
                "selected_option": wrong_opt,
                "is_correct": False
            })

        self.client.post("/api/quiz/submit", json={
            "quiz_id": quiz_id,
            "job_id": self.job_id,
            "topic_id": 2,
            "answers": answers
        })

        dash_res = self.client.get("/api/analytics/dashboard")
        dash_data = dash_res.get_json()
        weak_topics = dash_data.get("weak_topics", [])
        self.assertGreater(len(weak_topics), 0)
        wt = next((w for w in weak_topics if w["topic_id"] == 2), None)
        self.assertIsNotNone(wt)
        self.assertLess(wt["accuracy"], 60.0)
        self.assertIn("start_formatted", wt)
        print(f"✓ Weak topic detected correctly: '{wt['topic_title']}' with {wt['accuracy']}% accuracy")

    def test_09_enhanced_qa_history_and_followup(self):
        """Verify Q&A history tracking, plain-English simplification, and conversational follow-ups."""
        # 1. Ask question
        ask_res = self.client.post("/api/ask", json={
            "job_id": self.job_id,
            "question": "What is polymorphism?"
        })
        self.assertEqual(ask_res.status_code, 200)
        ask_data = ask_res.get_json()
        qa_id = ask_data.get("qa_id")

        # 2. History
        hist_res = self.client.get(f"/api/qa/history/{self.job_id}")
        self.assertEqual(hist_res.status_code, 200)
        hist_data = hist_res.get_json()
        self.assertGreater(len(hist_data["history"]), 0)

        # 3. Simplify
        simp_res = self.client.post("/api/qa/simplify", json={
            "job_id": self.job_id,
            "history_id": qa_id,
            "original_question": "What is polymorphism?",
            "original_answer": ask_data.get("answer", "")
        })
        self.assertEqual(simp_res.status_code, 200)
        simp_data = simp_res.get_json()
        self.assertIn("simplified_answer", simp_data)

        # 4. Follow-up
        follow_res = self.client.post("/api/qa/followup", json={
            "job_id": self.job_id,
            "parent_history_id": qa_id,
            "parent_question": "What is polymorphism?",
            "parent_answer": ask_data.get("answer", ""),
            "followup_question": "Can you give an example?"
        })
        self.assertEqual(follow_res.status_code, 200)
        follow_data = follow_res.get_json()
        self.assertTrue(follow_data.get("is_followup"))
        print("✓ Enhanced Q&A verified: History logged, Explain Simply generated, Conversational follow-up resolved")

if __name__ == "__main__":
    unittest.main()
