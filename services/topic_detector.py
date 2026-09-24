import os
import sys
import re
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Ensure root directory is on sys.path if run directly
if __package__ is None or __package__ == "":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.video_processor import format_timestamp

# Discourse cues indicating lecture topic transitions
TRANSITION_PATTERNS = [
    r"(?:now\s+let'?s\s+(?:talk\s+about|look\s+at|discuss|understand|see|explore|install|learn|move\s+to|cover))\s+([a-zA-Z0-9\s_#+-]{3,40})",
    r"(?:let'?s\s+(?:talk\s+about|look\s+at|discuss|understand|see|explore|install|learn|dive\s+into))\s+([a-zA-Z0-9\s_#+-]{3,40})",
    r"(?:moving\s+(?:on\s+)?to|next\s+(?:topic|concept|part|section|is))\s+([a-zA-Z0-9\s_#+-]{3,40})",
    r"(?:welcome\s+to|introduction\s+to)\s+([a-zA-Z0-9\s_#+-]{3,40})",
    r"(?:today\s+we\s+are\s+going\s+to\s+learn|in\s+this\s+video\s+we\s+will\s+cover)\s+([a-zA-Z0-9\s_#+-]{3,40})",
    r"(?:what\s+is|what\s+are|how\s+to\s+use|how\s+does|overview\s+of)\s+([a-zA-Z0-9\s_#+-]{3,40})",
    r"(?:first|second|third|fourth|finally|lastly)[,\s]+let'?s\s+([a-zA-Z0-9\s_#+-]{3,40})",
]

STOP_WORDS = {
    'a', 'about', 'above', 'after', 'again', 'against', 'all', 'am', 'an', 'and', 'any', 'are', 'aren', 'as', 'at',
    'be', 'because', 'been', 'before', 'being', 'below', 'between', 'both', 'but', 'by', 'can', 'could', 'did',
    'do', 'does', 'doing', 'down', 'during', 'each', 'few', 'for', 'from', 'further', 'had', 'has', 'have', 'having',
    'he', 'her', 'here', 'hers', 'herself', 'him', 'himself', 'his', 'how', 'i', 'if', 'in', 'into', 'is', 'it', 'its',
    'itself', 'just', 'me', 'more', 'most', 'my', 'myself', 'no', 'nor', 'not', 'now', 'of', 'off', 'on', 'once',
    'only', 'or', 'other', 'our', 'ours', 'ourselves', 'out', 'over', 'own', 'same', 'she', 'should', 'so', 'some',
    'such', 'than', 'that', 'the', 'their', 'theirs', 'them', 'themselves', 'then', 'there', 'these', 'they', 'this',
    'those', 'through', 'to', 'too', 'under', 'until', 'up', 'very', 'was', 'we', 'were', 'what', 'when', 'where',
    'which', 'while', 'who', 'whom', 'why', 'with', 'would', 'you', 'your', 'yours', 'yourself', 'yourselves',
    'like', 'going', 'also', 'see', 'okay', 'right', 'well', 'um', 'uh', 'know', 'thing', 'things', 'video'
}

TECHNICAL_PHRASES = {
    "order by", "group by", "inner join", "left join", "right join", "full join",
    "cross join", "outer join", "primary key", "foreign key", "where clause", "having clause",
    "select statement", "insert into", "delete from", "update set", "create table",
    "drop table", "alter table", "data types", "stored procedure", "window function"
}

def clean_title(title):
    """Clean extracted title string into a title-cased heading, preserving technical phrases."""
    clean_lower = title.lower().strip()
    # Check if a technical phrase matches directly
    for phrase in TECHNICAL_PHRASES:
        if phrase in clean_lower:
            # Preserve phrase
            return phrase.title()

    title_clean = re.sub(r'[^a-zA-Z0-9\s\+\#\.]', ' ', title)
    raw_words = title_clean.split()
    words = []
    for i, w in enumerate(raw_words):
        w_low = w.lower()
        # Preserve 'by' if preceded by 'order' or 'group'
        if w_low == 'by' and i > 0 and raw_words[i-1].lower() in {'order', 'group'}:
            words.append(w)
        elif w_low not in STOP_WORDS:
            words.append(w)

    if not words:
        return "Key Concept Overview"
    clean_str = " ".join(words[:5]).title()
    return clean_str

def extract_keyphrases(text, top_n=3):
    """Extract prominent key terms from text using TF-IDF."""
    if not text or len(text.split()) < 4:
        return ["Overview", "Concepts"]
    
    try:
        vec = TfidfVectorizer(ngram_range=(1, 2), stop_words='english', max_features=25)
        tfidf = vec.fit_transform([text])
        feature_names = vec.get_feature_names_out()
        scores = tfidf.toarray()[0]
        top_indices = np.argsort(scores)[::-1]
        
        keywords = []
        for idx in top_indices:
            word = feature_names[idx]
            if len(word) > 2 and word not in keywords:
                keywords.append(word.title())
            if len(keywords) >= top_n:
                break
        return keywords if keywords else ["Key Concepts"]
    except Exception:
        words = [w.title() for w in text.split() if w.lower() not in STOP_WORDS and len(w) > 3]
        return list(dict.fromkeys(words))[:top_n] or ["Overview"]

def detect_topic_boundaries(segments, total_duration, min_chapter_duration=30.0):
    """
    Detects topic change timestamps using a combination of discourse cues
    and semantic vocabulary shift dips.
    """
    if not segments:
        return [0.0]

    # If the video is very short, fewer chapters
    if total_duration < 60:
        min_chapter_duration = 15.0
    elif total_duration > 1800: # > 30 mins
        min_chapter_duration = 120.0
    elif total_duration > 600: # > 10 mins
        min_chapter_duration = 60.0

    boundaries = [0.0]
    candidate_cues = []

    # Pass 1: Spot discourse transition cues
    for seg in segments:
        text = seg["text"]
        start = seg["start"]
        for pattern in TRANSITION_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                candidate_cues.append((start, match.group(1).strip()))
                break

    # Pass 2: Semantic sliding-window similarity dips
    # Group segments into ~20-30s temporal windows
    window_size = 25.0
    windows = []
    current_win_text = []
    win_start = 0.0

    for seg in segments:
        current_win_text.append(seg["text"])
        if seg["end"] - win_start >= window_size:
            windows.append({
                "start": win_start,
                "end": seg["end"],
                "text": " ".join(current_win_text)
            })
            win_start = seg["end"]
            current_win_text = []
    
    if current_win_text:
        windows.append({
            "start": win_start,
            "end": total_duration,
            "text": " ".join(current_win_text)
        })

    # Compute cosine similarity between consecutive windows
    sim_dips = []
    if len(windows) > 2:
        texts = [w["text"] for w in windows]
        try:
            vec = TfidfVectorizer(stop_words='english')
            matrix = vec.fit_transform(texts)
            for i in range(len(windows) - 1):
                sim = cosine_similarity(matrix[i], matrix[i+1])[0][0]
                if sim < 0.25:  # Significant vocabulary drop indicates topic boundary
                    sim_dips.append(windows[i+1]["start"])
        except Exception:
            pass

    # Combine cue points and similarity dips, respecting minimum duration
    all_candidates = sorted(list(set([c[0] for c in candidate_cues] + sim_dips)))

    last_b = 0.0
    for cand in all_candidates:
        if (cand - last_b) >= min_chapter_duration and (total_duration - cand) >= (min_chapter_duration * 0.7):
            boundaries.append(cand)
            last_b = cand

    # If no boundaries detected or too few for long video, create evenly spaced semantic split
    if len(boundaries) == 1 and total_duration > min_chapter_duration * 2:
        target_num_chapters = max(2, min(8, int(total_duration // min_chapter_duration)))
        step = total_duration / target_num_chapters
        for k in range(1, target_num_chapters):
            time_k = k * step
            # snap to nearest segment start
            nearest_seg = min(segments, key=lambda s: abs(s["start"] - time_k))
            if nearest_seg["start"] > boundaries[-1] + min_chapter_duration:
                boundaries.append(nearest_seg["start"])

    return sorted(list(set(boundaries)))

def generate_chapters(segments, total_duration):
    """
    Produce structured chapters with title, start/end timestamps, summary, and keypoints.
    """
    if not segments:
        return [{
            "id": 1,
            "title": "Full Video",
            "start_time": 0.0,
            "end_time": max(1.0, total_duration),
            "start_formatted": "00:00",
            "end_formatted": format_timestamp(total_duration),
            "summary": "Full video content.",
            "key_points": ["Complete video overview"],
            "segments": []
        }]

    boundaries = detect_topic_boundaries(segments, total_duration)
    chapters = []
    num_b = len(boundaries)

    for i in range(num_b):
        b_start = boundaries[i]
        b_end = boundaries[i+1] if (i + 1 < num_b) else total_duration
        
        # Collect segments belonging to this chapter
        chap_segs = [s for s in segments if s["start"] >= b_start and s["start"] < b_end]
        if not chap_segs:
            # Fallback if no exact match
            chap_segs = [s for s in segments if s["start"] >= b_start]

        chap_text = " ".join([s["text"] for s in chap_segs])

        # Derive Chapter Title:
        # 1. Check if first segment in chapter has transition cue
        detected_title = None
        for seg in chap_segs[:3]:
            for pat in TRANSITION_PATTERNS:
                m = re.search(pat, seg["text"], re.IGNORECASE)
                if m:
                    candidate = m.group(1).strip()
                    if len(candidate) > 2:
                        detected_title = clean_title(candidate)
                        break
            if detected_title:
                break

        # 2. If no cue title, derive from keyphrases
        if not detected_title or len(detected_title) < 3:
            keyphrases = extract_keyphrases(chap_text, top_n=2)
            detected_title = " & ".join(keyphrases)

        # 3. Handle opening chapter
        if i == 0 and ("Intro" not in detected_title and "Welcome" not in detected_title):
            detected_title = f"Introduction & {detected_title}"

        # Summary and bullet points
        key_points = extract_keyphrases(chap_text, top_n=4)
        sentences = [s.strip() for s in re.split(r'[.!?]+', chap_text) if len(s.strip().split()) >= 4]
        summary = " ".join(sentences[:2]) if sentences else "Chapter covering " + detected_title
        if not summary.endswith('.'):
            summary += "."

        chapters.append({
            "id": i + 1,
            "title": detected_title,
            "start_time": round(b_start, 2),
            "end_time": round(b_end, 2),
            "start_formatted": format_timestamp(b_start),
            "end_formatted": format_timestamp(b_end),
            "summary": summary,
            "key_points": key_points,
            "segments_count": len(chap_segs),
            "text": chap_text
        })

    return chapters

def generate_lecture_notes(chapters, video_info):
    """
    Generate clean, comprehensive Markdown notes for the entire lecture.
    """
    lines = [
        f"# 📚 Lecture Notes: {video_info.get('filename', 'Video Lecture')}",
        f"- **Total Duration**: {video_info.get('duration_formatted', '00:00')}",
        f"- **Total Chapters**: {len(chapters)}",
        f"- **Generated by**: VidSeek AI",
        "",
        "---",
        "## 📑 Table of Contents",
        ""
    ]

    for chap in chapters:
        lines.append(f"- [{chap['title']}](#chapter-{chap['id']}) ({chap['start_formatted']} – {chap['end_formatted']})")

    lines.append("\n---")
    for chap in chapters:
        lines.append(f"\n### <a id='chapter-{chap['id']}'></a>Chapter {chap['id']}: {chap['title']}")
        lines.append(f"⏱️ **Timestamp**: `{chap['start_formatted']}` – `{chap['end_formatted']}`")
        lines.append(f"\n**Summary:**\n{chap['summary']}")
        lines.append("\n**Key Concepts & Topics Covered:**")
        for pt in chap.get('key_points', []):
            lines.append(f"- {pt}")
        lines.append("\n**Transcript Excerpt:**")
        preview = chap.get('text', '')[:300]
        if len(chap.get('text', '')) > 300:
            preview += "..."
        lines.append(f"> *\"{preview}\"*")
        lines.append("\n---")

    return "\n".join(lines)
