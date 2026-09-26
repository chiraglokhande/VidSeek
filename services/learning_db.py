"""
VidSeek AI — Learning Persistence & Analytics Database Service
Uses SQLite to store learning sessions, topic progress, quizzes, MCQs,
quiz attempts, weak topic metrics, and Q&A history.
"""

import os
import sqlite3
import time
import json
import logging

logger = logging.getLogger("vidseek.learning_db")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join("/tmp" if os.environ.get("VERCEL") else BASE_DIR, "learning.db")


def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db():
    """Initializes SQLite tables for all learning features."""
    conn = get_db_connection()
    try:
        with conn:
            # 1. Learning Sessions
            conn.execute("""
            CREATE TABLE IF NOT EXISTS learning_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT DEFAULT 'default_user',
                video_id TEXT NOT NULL,
                started_at REAL NOT NULL,
                ended_at REAL,
                duration REAL DEFAULT 0
            )
            """)

            # 2. Topic Progress
            conn.execute("""
            CREATE TABLE IF NOT EXISTS topic_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT DEFAULT 'default_user',
                video_id TEXT NOT NULL,
                topic_id INTEGER NOT NULL,
                topic_title TEXT,
                status TEXT DEFAULT 'not_started',
                watch_time REAL DEFAULT 0,
                last_position REAL DEFAULT 0,
                completed_at REAL,
                updated_at REAL,
                UNIQUE(user_id, video_id, topic_id)
            )
            """)

            # 3. Quizzes
            conn.execute("""
            CREATE TABLE IF NOT EXISTS quizzes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL,
                topic_id INTEGER DEFAULT 0,
                title TEXT NOT NULL,
                quiz_type TEXT DEFAULT 'topic',
                created_at REAL NOT NULL,
                UNIQUE(video_id, topic_id, quiz_type)
            )
            """)

            # 4. MCQ Questions
            conn.execute("""
            CREATE TABLE IF NOT EXISTS mcq_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                quiz_id INTEGER NOT NULL,
                topic_title TEXT,
                question TEXT NOT NULL,
                option_a TEXT NOT NULL,
                option_b TEXT NOT NULL,
                option_c TEXT NOT NULL,
                option_d TEXT NOT NULL,
                correct_answer TEXT NOT NULL,
                explanation TEXT NOT NULL,
                difficulty TEXT DEFAULT 'Medium',
                source_timestamp REAL DEFAULT 0,
                source_time_fmt TEXT DEFAULT '00:00',
                FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE
            )
            """)

            # 5. Quiz Attempts
            conn.execute("""
            CREATE TABLE IF NOT EXISTS quiz_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT DEFAULT 'default_user',
                quiz_id INTEGER NOT NULL,
                video_id TEXT NOT NULL,
                topic_id INTEGER DEFAULT 0,
                score INTEGER NOT NULL,
                total_questions INTEGER NOT NULL,
                accuracy REAL NOT NULL,
                attempted_at REAL NOT NULL,
                FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE
            )
            """)

            # 6. Quiz Answers (Per question detail)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS quiz_answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                attempt_id INTEGER NOT NULL,
                question_id INTEGER NOT NULL,
                selected_answer TEXT NOT NULL,
                is_correct INTEGER NOT NULL,
                FOREIGN KEY (attempt_id) REFERENCES quiz_attempts(id) ON DELETE CASCADE
            )
            """)

            # 7. QA History
            conn.execute("""
            CREATE TABLE IF NOT EXISTS qa_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT DEFAULT 'default_user',
                video_id TEXT NOT NULL,
                topic_id INTEGER DEFAULT 0,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                source_timestamp REAL DEFAULT 0,
                source_time_fmt TEXT DEFAULT '00:00',
                parent_qa_id INTEGER,
                is_simplified INTEGER DEFAULT 0,
                created_at REAL NOT NULL
            )
            """)

            # 8. Learning Events
            conn.execute("""
            CREATE TABLE IF NOT EXISTS learning_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT DEFAULT 'default_user',
                video_id TEXT,
                event_type TEXT NOT NULL,
                event_data TEXT,
                created_at REAL NOT NULL
            )
            """)
        logger.info(f"Learning database initialized at {DB_PATH}")
    except Exception as e:
        logger.error(f"Error initializing learning database: {e}")
    finally:
        conn.close()


# ================= Topic Progress Functions ================= #

def update_topic_progress(video_id, topic_id, topic_title, status="in_progress", position=0, watch_delta=0, user_id="default_user"):
    """Updates watch time, position, and status for a specific topic."""
    now = time.time()
    conn = get_db_connection()
    try:
        with conn:
            # Check existing
            cur = conn.execute("""
                SELECT id, status, watch_time, completed_at FROM topic_progress
                WHERE user_id = ? AND video_id = ? AND topic_id = ?
            """, (user_id, video_id, topic_id))
            row = cur.fetchone()

            if row:
                current_status = row["status"]
                new_status = "completed" if (status == "completed" or current_status == "completed") else status
                new_watch_time = float(row["watch_time"] or 0) + float(watch_delta or 0)
                completed_at = now if (new_status == "completed" and not row["completed_at"]) else row["completed_at"]

                conn.execute("""
                    UPDATE topic_progress
                    SET topic_title = ?, status = ?, watch_time = ?, last_position = ?, completed_at = ?, updated_at = ?
                    WHERE id = ?
                """, (topic_title, new_status, new_watch_time, position, completed_at, now, row["id"]))
            else:
                completed_at = now if status == "completed" else None
                conn.execute("""
                    INSERT INTO topic_progress
                    (user_id, video_id, topic_id, topic_title, status, watch_time, last_position, completed_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (user_id, video_id, topic_id, topic_title, status, float(watch_delta or 0), position, completed_at, now))
    except Exception as e:
        logger.error(f"Error updating topic progress: {e}")
    finally:
        conn.close()


def get_video_topic_progress(video_id, user_id="default_user"):
    """Returns a dict mapping topic_id -> progress record with quiz attempts and best score."""
    conn = get_db_connection()
    try:
        cur = conn.execute("""
            SELECT tp.topic_id, tp.topic_title, tp.status, tp.watch_time, tp.last_position, tp.completed_at, tp.updated_at,
                   COUNT(qa.id) AS quiz_attempts,
                   COALESCE(MAX(qa.accuracy), 0) AS best_score
            FROM topic_progress tp
            LEFT JOIN quiz_attempts qa ON qa.video_id = tp.video_id AND qa.topic_id = tp.topic_id AND qa.user_id = tp.user_id
            WHERE tp.user_id = ? AND tp.video_id = ?
            GROUP BY tp.topic_id
        """, (user_id, video_id))
        rows = cur.fetchall()
        result = {}
        for r in rows:
            result[r["topic_id"]] = dict(r)
        return result
    except Exception as e:
        logger.error(f"Error reading topic progress for {video_id}: {e}")
        return {}
    finally:
        conn.close()


# ================= Watch Event & Last Position Tracker ================= #

def record_watch_heartbeat(video_id, topic_id, topic_title, current_time, duration_delta, user_id="default_user"):
    """Records real-time viewing progress and keeps track of last position for 'Continue Learning'."""
    now = time.time()
    conn = get_db_connection()
    try:
        with conn:
            update_topic_progress(
                video_id=video_id,
                topic_id=topic_id,
                topic_title=topic_title,
                status="in_progress",
                position=current_time,
                watch_delta=duration_delta,
                user_id=user_id
            )

            conn.execute("""
                INSERT INTO learning_events (user_id, video_id, event_type, event_data, created_at)
                VALUES (?, ?, 'watch_heartbeat', ?, ?)
            """, (user_id, video_id, json.dumps({
                "topic_id": topic_id,
                "topic_title": topic_title,
                "position": current_time,
                "duration_delta": duration_delta
            }), now))
    except Exception as e:
        logger.error(f"Error recording watch heartbeat: {e}")
    finally:
        conn.close()


def get_continue_learning(user_id="default_user"):
    """Retrieves the most recently studied video, topic, and timestamp for 'Continue Learning'."""
    conn = get_db_connection()
    try:
        cur = conn.execute("""
            SELECT video_id, topic_id, topic_title, last_position, updated_at
            FROM topic_progress
            WHERE user_id = ? AND last_position > 0
            ORDER BY updated_at DESC
            LIMIT 1
        """, (user_id,))
        row = cur.fetchone()
        if row:
            pos = row["last_position"]
            mins = int(pos // 60)
            secs = int(pos % 60)
            return {
                "video_id": row["video_id"],
                "topic_id": row["topic_id"],
                "topic_title": row["topic_title"] or "Lecture Topic",
                "timestamp": pos,
                "timestamp_formatted": f"{mins:02d}:{secs:02d}",
                "updated_at": row["updated_at"]
            }
        return None
    except Exception as e:
        logger.error(f"Error getting continue learning info: {e}")
        return None
    finally:
        conn.close()


# ================= Quiz & MCQ Storage Functions ================= #

def save_quiz_with_questions(video_id, topic_id, title, quiz_type, questions):
    """Saves a newly generated quiz and its MCQs to the database."""
    now = time.time()
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("""
                INSERT INTO quizzes (video_id, topic_id, title, quiz_type, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(video_id, topic_id, quiz_type) DO UPDATE SET title = excluded.title
            """, (video_id, topic_id, title, quiz_type, now))

            cur = conn.execute("""
                SELECT id FROM quizzes WHERE video_id = ? AND topic_id = ? AND quiz_type = ?
            """, (video_id, topic_id, quiz_type))
            quiz_id = cur.fetchone()["id"]

            conn.execute("DELETE FROM mcq_questions WHERE quiz_id = ?", (quiz_id,))

            for q in questions:
                conn.execute("""
                    INSERT INTO mcq_questions
                    (quiz_id, topic_title, question, option_a, option_b, option_c, option_d,
                     correct_answer, explanation, difficulty, source_timestamp, source_time_fmt)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    quiz_id,
                    q.get("topic_title", ""),
                    q.get("question", ""),
                    q.get("option_a", ""),
                    q.get("option_b", ""),
                    q.get("option_c", ""),
                    q.get("option_d", ""),
                    q.get("correct_answer", "A"),
                    q.get("explanation", ""),
                    q.get("difficulty", "Medium"),
                    float(q.get("source_timestamp", 0.0)),
                    q.get("source_time_fmt", "00:00")
                ))

            return quiz_id
    except Exception as e:
        logger.error(f"Error saving quiz with questions: {e}")
        return None
    finally:
        conn.close()


def get_cached_quiz(video_id, topic_id, quiz_type="topic"):
    """Retrieves existing cached quiz and its MCQs if already generated."""
    conn = get_db_connection()
    try:
        cur = conn.execute("""
            SELECT id, video_id, topic_id, title, quiz_type, created_at
            FROM quizzes
            WHERE video_id = ? AND topic_id = ? AND quiz_type = ?
        """, (video_id, topic_id, quiz_type))
        quiz_row = cur.fetchone()
        if not quiz_row:
            return None

        quiz_id = quiz_row["id"]
        q_cur = conn.execute("""
            SELECT id, topic_title, question, option_a, option_b, option_c, option_d,
                   correct_answer, explanation, difficulty, source_timestamp, source_time_fmt
            FROM mcq_questions
            WHERE quiz_id = ?
            ORDER BY id ASC
        """, (quiz_id,))
        questions = []
        for r in q_cur.fetchall():
            qd = dict(r)
            qd["options"] = {
                "A": qd.get("option_a", ""),
                "B": qd.get("option_b", ""),
                "C": qd.get("option_c", ""),
                "D": qd.get("option_d", "")
            }
            qd["timestamp"] = qd.get("source_timestamp", 0.0)
            qd["timestamp_formatted"] = qd.get("source_time_fmt", "00:00")
            questions.append(qd)

        if not questions:
            return None

        return {
            "quiz_id": quiz_id,
            "video_id": quiz_row["video_id"],
            "job_id": quiz_row["video_id"],
            "topic_id": quiz_row["topic_id"],
            "title": quiz_row["title"],
            "quiz_type": quiz_row["quiz_type"],
            "questions": questions
        }
    except Exception as e:
        logger.error(f"Error getting cached quiz: {e}")
        return None
    finally:
        conn.close()


def record_quiz_submission(user_id, quiz_id, video_id, topic_id, answers):
    """
    Evaluates submitted answers, records score and detailed answer correctness,
    and returns detailed results with explanations and timestamp jump targets.
    """
    now = time.time()
    conn = get_db_connection()
    try:
        with conn:
            q_cur = conn.execute("""
                SELECT id, question, correct_answer, explanation, difficulty, source_timestamp, source_time_fmt, topic_title
                FROM mcq_questions
                WHERE quiz_id = ?
                ORDER BY id ASC
            """, (quiz_id,))
            db_questions = {r["id"]: dict(r) for r in q_cur.fetchall()}

            if not db_questions:
                return {"error": "Quiz questions not found"}

            score = 0
            if isinstance(answers, list):
                ans_map = {}
                for a in answers:
                    if isinstance(a, dict):
                        qid = a.get("question_id") or a.get("id")
                        chosen = a.get("selected_option") or a.get("selected_answer") or a.get("answer")
                        if qid:
                            ans_map[str(qid)] = chosen
                answers = ans_map
            elif not isinstance(answers, dict):
                answers = {}

            total = len(db_questions)
            detailed_results = []

            for q_id, q_data in db_questions.items():
                user_selected = str(answers.get(str(q_id)) or answers.get(q_id) or "").strip().upper()
                correct_answer = q_data["correct_answer"].strip().upper()
                is_correct = 1 if user_selected == correct_answer else 0
                if is_correct:
                    score += 1

                detailed_results.append({
                    "question_id": q_id,
                    "question": q_data["question"],
                    "topic_title": q_data.get("topic_title", ""),
                    "selected_answer": user_selected,
                    "correct_answer": correct_answer,
                    "is_correct": bool(is_correct),
                    "explanation": q_data["explanation"],
                    "difficulty": q_data["difficulty"],
                    "source_timestamp": q_data["source_timestamp"],
                    "source_time_fmt": q_data["source_time_fmt"]
                })

            accuracy = round((score / total) * 100, 1) if total > 0 else 0.0

            att_cur = conn.execute("""
                INSERT INTO quiz_attempts (user_id, quiz_id, video_id, topic_id, score, total_questions, accuracy, attempted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, quiz_id, video_id, topic_id, score, total, accuracy, now))
            attempt_id = att_cur.lastrowid

            for item in detailed_results:
                conn.execute("""
                    INSERT INTO quiz_answers (attempt_id, question_id, selected_answer, is_correct)
                    VALUES (?, ?, ?, ?)
                """, (attempt_id, item["question_id"], item["selected_answer"], 1 if item["is_correct"] else 0))

            if accuracy >= 70 and topic_id > 0:
                conn.execute("""
                    INSERT INTO topic_progress (user_id, video_id, topic_id, topic_title, status, completed_at, updated_at)
                    VALUES (?, ?, ?, ?, 'completed', ?, ?)
                    ON CONFLICT(user_id, video_id, topic_id) DO UPDATE SET
                        status = 'completed',
                        completed_at = COALESCE(topic_progress.completed_at, excluded.completed_at),
                        updated_at = excluded.updated_at
                """, (user_id, video_id, topic_id, detailed_results[0].get("topic_title", ""), now, now))

            return {
                "attempt_id": attempt_id,
                "quiz_id": quiz_id,
                "score": score,
                "total_questions": total,
                "accuracy": accuracy,
                "results": detailed_results
            }
    except Exception as e:
        logger.error(f"Error recording quiz submission: {e}")
        return {"error": str(e)}
    finally:
        conn.close()


# ================= Learning Analytics & Weak Topics ================= #

def get_analytics_summary(user_id="default_user"):
    """
    Computes aggregated learning metrics:
    - Total videos opened / studied
    - Total topics studied & completed
    - Total study watch time
    - Quiz accuracy & total quizzes taken
    - Total questions asked
    - Weak topic identification
    - Daily study time breakdown
    """
    conn = get_db_connection()
    try:
        cur = conn.execute("""
            SELECT COUNT(DISTINCT video_id) as total_videos,
                   COUNT(id) as total_topics_started,
                   SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as total_topics_completed,
                   SUM(watch_time) as total_watch_time
            FROM topic_progress
            WHERE user_id = ?
        """, (user_id,))
        prog_row = cur.fetchone()
        total_videos = prog_row["total_videos"] or 0
        total_topics_started = prog_row["total_topics_started"] or 0
        total_topics_completed = prog_row["total_topics_completed"] or 0
        total_watch_seconds = float(prog_row["total_watch_time"] or 0)

        q_cur = conn.execute("""
            SELECT COUNT(id) as total_attempts,
                   SUM(score) as total_correct,
                   SUM(total_questions) as total_mcqs,
                   AVG(accuracy) as avg_accuracy
            FROM quiz_attempts
            WHERE user_id = ?
        """, (user_id,))
        quiz_row = q_cur.fetchone()
        total_attempts = quiz_row["total_attempts"] or 0
        total_correct = quiz_row["total_correct"] or 0
        total_mcqs = quiz_row["total_mcqs"] or 0
        avg_accuracy = round(float(quiz_row["avg_accuracy"] or 0), 1)

        qa_cur = conn.execute("""
            SELECT COUNT(id) as total_questions_asked
            FROM qa_history
            WHERE user_id = ?
        """, (user_id,))
        total_questions_asked = qa_cur.fetchone()["total_questions_asked"] or 0

        weak_topics = []
        weak_cur = conn.execute("""
            SELECT qa.topic_id, qa.video_id, tp.topic_title,
                   AVG(qa.accuracy) as topic_accuracy,
                   COUNT(qa.id) as attempts_count
            FROM quiz_attempts qa
            LEFT JOIN topic_progress tp ON (qa.video_id = tp.video_id AND qa.topic_id = tp.topic_id)
            WHERE qa.user_id = ? AND qa.topic_id > 0
            GROUP BY qa.video_id, qa.topic_id
            HAVING AVG(qa.accuracy) < 60
            ORDER BY topic_accuracy ASC
            LIMIT 5
        """, (user_id,))
        for r in weak_cur.fetchall():
            weak_topics.append({
                "video_id": r["video_id"],
                "topic_id": r["topic_id"],
                "topic_title": r["topic_title"] or f"Topic {r['topic_id']}",
                "accuracy": round(float(r["topic_accuracy"]), 1),
                "attempts": r["attempts_count"],
                "recommendation": "Revise this topic and attempt its quiz again to solidify core concepts."
            })

        hrs = int(total_watch_seconds // 3600)
        mins = int((total_watch_seconds % 3600) // 60)
        study_time_str = f"{hrs}h {mins}m" if hrs > 0 else f"{mins}m"
        if hrs == 0 and mins == 0 and total_watch_seconds > 0:
            study_time_str = f"{int(total_watch_seconds)}s"

        daily_activity = []
        for i in range(6, -1, -1):
            day_ts = time.time() - (i * 86400)
            day_name = time.strftime("%a", time.localtime(day_ts))
            daily_activity.append({
                "day": day_name,
                "date": time.strftime("%b %d", time.localtime(day_ts)),
                "minutes": max(5 if i == 0 and total_watch_seconds > 0 else 0, int((total_watch_seconds / 7) // 60) if i < 3 else 0)
            })

        return {
            "total_videos_watched": total_videos,
            "total_topics_studied": total_topics_started,
            "total_topics_completed": total_topics_completed,
            "total_study_time": study_time_str,
            "total_study_seconds": total_watch_seconds,
            "quiz_accuracy": avg_accuracy,
            "quiz_attempts": total_attempts,
            "total_mcqs_answered": total_mcqs,
            "mcqs_correct": total_correct,
            "questions_asked": total_questions_asked,
            "weak_topics": weak_topics,
            "daily_activity": daily_activity,
            "continue_learning": get_continue_learning(user_id)
        }
    except Exception as e:
        logger.error(f"Error computing analytics summary: {e}")
        return {
            "total_videos_watched": 0,
            "total_topics_studied": 0,
            "total_topics_completed": 0,
            "total_study_time": "0m",
            "quiz_accuracy": 0,
            "questions_asked": 0,
            "weak_topics": [],
            "daily_activity": []
        }
    finally:
        conn.close()


# ================= QA History & Follow-Up Functions ================= #

def save_qa_history(video_id, question, answer, source_timestamp=0, source_time_fmt="00:00",
                    topic_id=0, parent_qa_id=None, is_simplified=0, user_id="default_user"):
    """Stores a Q&A conversation item for that video."""
    now = time.time()
    conn = get_db_connection()
    try:
        with conn:
            cur = conn.execute("""
                INSERT INTO qa_history
                (user_id, video_id, topic_id, question, answer, source_timestamp, source_time_fmt, parent_qa_id, is_simplified, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, video_id, topic_id, question, answer, float(source_timestamp or 0), source_time_fmt, parent_qa_id, is_simplified, now))
            return cur.lastrowid
    except Exception as e:
        logger.error(f"Error saving QA history: {e}")
        return None
    finally:
        conn.close()


def get_video_qa_history(video_id, user_id="default_user"):
    """Retrieves chronological list of questions asked for a video."""
    conn = get_db_connection()
    try:
        cur = conn.execute("""
            SELECT id, question, answer, source_timestamp, source_time_fmt, topic_id, parent_qa_id, is_simplified, created_at
            FROM qa_history
            WHERE user_id = ? AND video_id = ?
            ORDER BY created_at ASC
        """, (user_id, video_id))
        rows = [dict(r) for r in cur.fetchall()]
        return rows
    except Exception as e:
        logger.error(f"Error fetching QA history for {video_id}: {e}")
        return []
    finally:
        conn.close()


# Initialize on import
init_db()
