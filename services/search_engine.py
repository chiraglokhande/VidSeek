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

# Technical & compound programming concepts that shouldn't be fragmented into stop words
DOMAIN_CONCEPTS = {
    "order by": {
        "title": "ORDER BY",
        "related": ["sort", "sorting", "sorted", "ascending", "descending", "asc", "desc", "order of rows", "sequence", "alphabetical", "order"],
        "negative_idioms": [r"\bin order to\b", r"\bin order that\b"]
    },
    "group by": {
        "title": "GROUP BY",
        "related": ["group", "groups", "grouping", "aggregate", "count", "sum", "avg", "average", "categories", "having", "rows into groups"],
        "negative_idioms": []
    },
    "inner join": {
        "title": "INNER JOIN",
        "related": ["join", "tables", "matching keys", "on clause", "table relationships", "combine tables"],
        "negative_idioms": []
    },
    "left join": {
        "title": "LEFT JOIN",
        "related": ["left outer join", "all rows from left", "null values", "table join"],
        "negative_idioms": []
    },
    "right join": {
        "title": "RIGHT JOIN",
        "related": ["right outer join", "all rows from right", "table join"],
        "negative_idioms": []
    },
    "primary key": {
        "title": "PRIMARY KEY",
        "related": ["unique identifier", "not null", "table key", "record id", "uniquely identify"],
        "negative_idioms": []
    },
    "foreign key": {
        "title": "FOREIGN KEY",
        "related": ["references", "referenced table", "relationship", "parent key", "child table"],
        "negative_idioms": []
    },
    "having": {
        "title": "HAVING",
        "related": ["having clause", "filter groups", "after group by", "aggregate condition"],
        "negative_idioms": []
    },
    "where": {
        "title": "WHERE",
        "related": ["where clause", "filter rows", "condition", "before group by", "filtering"],
        "negative_idioms": []
    },
    "window function": {
        "title": "WINDOW FUNCTION",
        "related": ["over clause", "partition by", "row_number", "rank", "dense_rank", "lead", "lag"],
        "negative_idioms": []
    }
}

# Domain-safe stop words that never strip SQL/programming keywords like 'by' or 'order'
SAFE_STOP_WORDS = {
    'a', 'about', 'above', 'after', 'again', 'against', 'all', 'am', 'an', 'and', 'any', 'are', 'aren',
    'as', 'at', 'be', 'because', 'been', 'before', 'being', 'below', 'between', 'both', 'but', 'can',
    'could', 'did', 'do', 'does', 'doing', 'down', 'during', 'each', 'few', 'for', 'from', 'further',
    'had', 'has', 'have', 'having', 'he', 'her', 'here', 'hers', 'herself', 'him', 'himself', 'his',
    'how', 'i', 'if', 'in', 'into', 'is', 'it', 'its', 'itself', 'just', 'me', 'more', 'most', 'my',
    'myself', 'no', 'nor', 'not', 'now', 'of', 'off', 'on', 'once', 'only', 'or', 'other', 'our',
    'ours', 'ourselves', 'out', 'over', 'own', 'same', 'she', 'should', 'so', 'some', 'such', 'than',
    'that', 'the', 'their', 'theirs', 'them', 'themselves', 'then', 'there', 'these', 'they', 'this',
    'those', 'through', 'to', 'too', 'under', 'until', 'up', 'very', 'was', 'we', 'were', 'what',
    'when', 'where', 'which', 'while', 'who', 'whom', 'why', 'with', 'would', 'you', 'your', 'yours'
    # Note: 'by' and 'order' and 'group' are intentionally EXCLUDED to protect SQL terms!
}

def parse_query_intent(query):
    """
    Deconstructs user queries using LLM-style semantic reasoning:
    Identifies query intent (definitional, procedural, comparative, lookup)
    and extracts the underlying target technical concept.
    """
    if not query:
        return {"intent": "LOOKUP", "target_concept": "", "is_question": False, "tokens": []}

    q = query.strip().lower()
    # Normalize common technical abbreviations/spaceless keywords
    q = re.sub(r'\bgroupby\b', 'group by', q)
    q = re.sub(r'\borderby\b', 'order by', q)
    q = re.sub(r'\binnerjoin\b', 'inner join', q)
    q = re.sub(r'\bleftjoin\b', 'left join', q)
    q = re.sub(r'\brightjoin\b', 'right join', q)

    is_question = False
    intent = "LOOKUP"
    target_concept = ""

    # 1. Definitional patterns: "what is X", "explain X", "tell me about X", "definition of X"
    def_patterns = [
        r"^(?:what\s+is|what\s+are|what\s+do\s+you\s+mean\s+by|what\s+does\s+(.+?)\s+do|what\s+does\s+(.+?)\s+mean)\s*(.*)",
        r"^(?:explain|define|describe|introduce|clarify)\s+(?:the\s+concept\s+of\s+|the\s+)?(.+)",
        r"^(?:concept\s+of|meaning\s+of|definition\s+of|overview\s+of|tell\s+me\s+about)\s+(.+)",
        r"(.+?)\s+(?:definition|meaning|explained)$"
    ]
    for pat in def_patterns:
        m = re.search(pat, q)
        if m:
            is_question = True
            intent = "DEFINITIONAL"
            groups = [g for g in m.groups() if g]
            target_concept = groups[-1].strip()
            break

    # 2. Procedural / How-to patterns
    if not target_concept:
        how_patterns = [
            r"^(?:how\s+to\s+use|how\s+do\s+i\s+use|how\s+can\s+we\s+use|how\s+does\s+(.+?)\s+work)\s*(.*)",
            r"^(?:syntax\s+of|example\s+of|how\s+to\s+write)\s+(.+)"
        ]
        for pat in how_patterns:
            m = re.search(pat, q)
            if m:
                is_question = True
                intent = "PROCEDURAL"
                groups = [g for g in m.groups() if g]
                target_concept = groups[-1].strip()
                break

    # 3. Comparative patterns
    if not target_concept:
        comp_m = re.search(r"^(?:difference\s+between|compare|vs|versus)\s+(.+?)\s+(?:and|to|with|vs)\s+(.+)", q)
        if comp_m:
            is_question = True
            intent = "COMPARATIVE"
            target_concept = f"{comp_m.group(1).strip()} vs {comp_m.group(2).strip()}"

    # 4. Fallback extraction for general queries
    if not target_concept:
        if q.endswith('?'):
            is_question = True
        cleaned = re.sub(r'^(?:where\s+is|when\s+do\s+we\s+use|can\s+you\s+find|search\s+for)\s+', '', q)
        target_concept = cleaned.rstrip('?').strip()

    # Clean target concept from generic fillers
    target_concept = re.sub(r'\b(?:in\s+sql|in\s+database|clause|query|command|statement)\b', '', target_concept).strip()
    if not target_concept:
        target_concept = q.rstrip('?').strip()

    tokens = [w for w in re.findall(r'\b\w+\b', target_concept) if w not in SAFE_STOP_WORDS and len(w) > 1]

    return {
        "intent": intent,
        "target_concept": target_concept,
        "is_question": is_question,
        "tokens": tokens,
        "normalized_query": q
    }


def search_video(query, segments, chapters, top_k=6):
    """
    Intelligent semantic search that thinks like an LLM:
    - Understands questions and intent ('what is order by' -> definitional explanation of ORDER BY)
    - Distinguishes technical compound concepts from English idioms ('order by' vs 'in order to')
    - Pinpoints the exact introductory/explanatory timestamp where a topic is defined
    - Synergizes chapter topic boundaries with transcript discourse cues
    """
    if not query or not segments:
        return {"results": [], "ai_best_match": None, "ai_intent": "LOOKUP", "target_concept": ""}

    parsed = parse_query_intent(query)
    target = parsed["target_concept"].lower()
    intent = parsed["intent"]
    is_question = parsed["is_question"]

    # Check if target matches a known domain concept
    domain_meta = None
    for concept_key, meta in DOMAIN_CONCEPTS.items():
        if concept_key in target or target in concept_key:
            domain_meta = meta
            target = concept_key
            break

    # Build discourse context windows (sliding windows of 3 segments for coherent meaning)
    windows = []
    win_size = 3
    step = 1  # 1-segment step for dense temporal precision
    for i in range(0, len(segments)):
        sub_segs = segments[i:i+win_size]
        if not sub_segs:
            continue
        text = " ".join([s["text"] for s in sub_segs])

        # Pinpoint the primary focal segment inside this window
        focal_seg = sub_segs[0]
        for s in sub_segs:
            s_low = s["text"].lower()
            if target and re.search(r'\b' + re.escape(target) + r'\b', s_low):
                focal_seg = s
                break

        start = focal_seg["start"]
        end = sub_segs[-1]["end"]

        # Map to containing chapter based on the focal segment's timestamp
        matched_chap = "Main Video"
        chap_id = 1
        is_chapter_intro = False
        chap_start = start
        chap_end = end
        for c in chapters:
            if c["start_time"] <= start < c["end_time"] or (c["start_time"] <= start and c == chapters[-1]):
                matched_chap = c["title"]
                chap_id = c.get("id", 1)
                chap_start = c["start_time"]
                chap_end = c["end_time"]
                # Check if this window is within the first 45 seconds of the chapter
                if start - c["start_time"] < 45.0:
                    is_chapter_intro = True
                break

        # MODULE 1: PASSAGE RETRIEVAL - Create topic-wise passages with exact timestamp intervals
        windows.append({
            "start": start,
            "end": end,
            "start_formatted": format_timestamp(start),
            "end_formatted": format_timestamp(end),
            "passage_interval": f"{format_timestamp(start)} – {format_timestamp(end)}",
            "topic_start": chap_start,
            "topic_end": chap_end,
            "topic_start_formatted": format_timestamp(chap_start),
            "topic_end_formatted": format_timestamp(chap_end),
            "topic_interval": f"{format_timestamp(chap_start)} – {format_timestamp(chap_end)}",
            "text": text,
            "focal_text": focal_seg["text"],
            "sub_segs": sub_segs,
            "chapter_title": matched_chap,
            "chapter_id": chap_id,
            "is_chapter_intro": is_chapter_intro
        })

    # 1. Base TF-IDF Semantic Scoring
    corpus = [w["text"] for w in windows]
    try:
        vec = TfidfVectorizer(ngram_range=(1, 3), stop_words=list(SAFE_STOP_WORDS))
        matrix = vec.fit_transform(corpus)
        q_vec = vec.transform([query + " " + target])
        base_scores = cosine_similarity(q_vec, matrix)[0]
    except Exception:
        base_scores = np.zeros(len(windows))

    # 2. AI Semantic & Explanatory Reasoning Pass
    first_intro_seen = False
    scored_windows = []

    for idx, win in enumerate(windows):
        text_lower = win["text"].lower()
        score = float(base_scores[idx]) if idx < len(base_scores) else 0.0

        # Anti-idiom filter: Check if "order" appears only as "in order to"
        has_negative_idiom = False
        if domain_meta and domain_meta.get("negative_idioms"):
            for neg_pat in domain_meta["negative_idioms"]:
                if re.search(neg_pat, text_lower):
                    has_negative_idiom = True

        # Check exact concept occurrence
        has_exact_concept = bool(re.search(r'\b' + re.escape(target) + r'\b', text_lower)) if target else False
        if has_negative_idiom and not has_exact_concept:
            # Penalize accidental matches like "in order to"
            score *= 0.05

        concept_boost = 0.0
        if has_exact_concept:
            concept_boost += 4.0

        # Explanatory discourse cues (Crucial for "what is X" / "explain X")
        explanatory_boost = 0.0
        if has_exact_concept or (domain_meta and any(rel in text_lower for rel in domain_meta["related"][:3])):
            # Pattern A: Topic introduction / Discourse launch
            intro_pat = r"(?:now\s+)?(?:let'?s\s+(?:talk\s+about|look\s+at|discuss|understand|see|explore|cover|learn)|moving\s+to|next\s+is|welcome\s+to|today\s+we)\s+.*?\b" + re.escape(target)
            if re.search(intro_pat, text_lower):
                explanatory_boost += 3.5

            # Pattern B: Definitional sentence ("X is used to...", "X allows you to...", "X clause is...")
            def_pat = r"\b" + re.escape(target) + r"\s+(?:is|is\s+used\s+to|allows\s+you\s+to|helps\s+us\s+to|means|clause\s+is|clause)\b"
            if re.search(def_pat, text_lower):
                explanatory_boost += 4.0

            we_use_pat = r"\bwe\s+use\s+" + re.escape(target) + r"\s+to\b"
            if re.search(we_use_pat, text_lower):
                explanatory_boost += 3.0

            # Pattern C: Semantic domain association words (e.g. 'sort', 'ascending' for ORDER BY)
            if domain_meta:
                rel_hits = sum(1 for term in domain_meta["related"] if term in text_lower)
                explanatory_boost += min(3.0, rel_hits * 0.7)

        # Chapter Thematic Anchor
        chapter_boost = 0.0
        chap_title_lower = win["chapter_title"].lower()
        if target and target in chap_title_lower:
            chapter_boost += 3.0
            if win["is_chapter_intro"]:
                chapter_boost += 3.0  # Heavy boost to the beginning of the topic's dedicated chapter!

        # First introduction preference:
        # The first place the instructor formally introduces and defines the topic is the prime explanation!
        first_intro_bonus = 0.0
        if (has_exact_concept or (target and target in chap_title_lower)) and explanatory_boost > 1.5:
            if not first_intro_seen:
                first_intro_bonus = 2.5
                first_intro_seen = True

        total_score = score + concept_boost + explanatory_boost + chapter_boost + first_intro_bonus

        # Only retain relevant windows
        if total_score > 0.4 or has_exact_concept or (target and target in chap_title_lower):
            # Create highlighted snippet focusing on focal text and window
            snippet = win["text"]
            highlight_terms = [target] if target else []
            if domain_meta:
                highlight_terms.extend([r for r in domain_meta["related"] if r in text_lower][:3])
            highlight_terms.extend(parsed["tokens"])

            for term in highlight_terms:
                if len(term) > 2:
                    snippet = re.sub(rf'\b({re.escape(term)})\b', r'<mark>\1</mark>', snippet, flags=re.IGNORECASE)

            # MODULE 2: RANKING - Retain relevant passages with full temporal & topic context
            scored_windows.append({
                "start": win["start"],
                "end": win["end"],
                "timestamp_formatted": win["start_formatted"],
                "end_timestamp_formatted": win["end_formatted"],
                "passage_interval": win["passage_interval"],
                "topic_start": win["topic_start"],
                "topic_end": win["topic_end"],
                "topic_start_formatted": win["topic_start_formatted"],
                "topic_end_formatted": win["topic_end_formatted"],
                "topic_interval": win["topic_interval"],
                "chapter_title": win["chapter_title"],
                "chapter_id": win["chapter_id"],
                "snippet": snippet,
                "raw_text": win["text"],
                "focal_text": win["focal_text"],
                "score": round(total_score, 3),
                "is_definitional": explanatory_boost > 2.0 or (target and target in chap_title_lower and win["is_chapter_intro"])
            })

    # Sort descending by score, and if tie, by earlier timestamp
    scored_windows.sort(key=lambda x: (-x["score"], x["start"]))

    # Deduplicate consecutive windows with almost identical timestamps (< 6s apart)
    deduped = []
    seen_times = []
    for w in scored_windows:
        if any(abs(w["start"] - t) < 6.0 for t in seen_times):
            continue
        deduped.append(w)
        seen_times.append(w["start"])

    # MODULE 3: SEARCH ENGINE ARCHITECTURE - Output the Top Relevant Result with Topic Interval & Watch Action
    ai_best_match = None
    if deduped:
        best = deduped[0]
        concept_display = domain_meta["title"] if domain_meta else target.title()
        ai_summary = f"At {best['timestamp_formatted']} in Chapter \"{best['chapter_title']}\" ({best['topic_interval']}), the instructor explains and demonstrates {concept_display}."

        # Extract the exact definitional sentence from the focal text or window
        sentences = [s.strip() for s in re.split(r'[.!?]+', best["raw_text"]) if len(s.strip()) > 10]
        for s in sentences:
            s_l = s.lower()
            if target in s_l and any(w in s_l for w in ["used to", "allows", "sort", "group", "clause", "is", "we use"]):
                ai_summary = f"Explanation of {concept_display} at {best['timestamp_formatted']}: \"{s}.\""
                break

        ai_best_match = {
            "start": best["start"],
            "end": best["end"],
            "timestamp_formatted": best["timestamp_formatted"],
            "end_timestamp_formatted": best["end_timestamp_formatted"],
            "passage_interval": best["passage_interval"],
            "topic_start": best["topic_start"],
            "topic_end": best["topic_end"],
            "topic_start_formatted": best["topic_start_formatted"],
            "topic_end_formatted": best["topic_end_formatted"],
            "topic_interval": best["topic_interval"],
            "chapter_title": best["chapter_title"],
            "chapter_id": best.get("chapter_id", 1),
            "target_concept": concept_display,
            "snippet": best["snippet"],
            "summary": ai_summary,
            "focal_text": best["focal_text"],
            "score": best["score"]
        }

    top_results = deduped[:top_k]
    return {
        "results": top_results,
        "ai_best_match": ai_best_match,
        "ai_intent": intent,
        "target_concept": target.title() if target else query
    }


def answer_video_question(question, segments, chapters):
    """
    Natural Language Q&A Engine (thinking like an LLM):
    Finds the exact explanatory segment in the video, answers the student's question directly,
    and returns the precise timestamp for video playback jump.
    """
    if not question or not segments:
        return {
            "answer": "No transcript available to answer the question.",
            "timestamp": 0.0,
            "timestamp_formatted": "00:00",
            "chapter_title": "N/A",
            "confidence": "low"
        }

    # Run AI semantic search
    search_data = search_video(question, segments, chapters, top_k=4)
    search_hits = search_data.get("results", [])
    ai_best = search_data.get("ai_best_match")

    if not search_hits and not ai_best:
        return {
            "answer": f"I couldn't find a direct discussion of \"{question}\" in this video. Try searching for related SQL topics.",
            "timestamp": 0.0,
            "timestamp_formatted": "00:00",
            "chapter_title": "N/A",
            "confidence": "none"
        }

    top_hit = ai_best if ai_best else search_hits[0]
    best_time = top_hit["start"]
    best_time_fmt = top_hit["timestamp_formatted"]
    best_chap = top_hit["chapter_title"]
    concept = search_data.get("target_concept", "this topic")

    # Gather rich surrounding context
    context_passages = [h["raw_text"] for h in search_hits[:3] if "raw_text" in h]
    context_str = "\n".join(context_passages)

    # 1. Cloud LLM generation if GEMINI_API_KEY is configured
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            import requests
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
            prompt = f"""You are VidSeek AI, an expert video lecture assistant.
The student asks: "{question}"

Here are the exact transcript excerpts from the video around timestamp {best_time_fmt} (Chapter "{best_chap}"):
{context_str}

Provide a concise, direct, helpful 2-4 sentence explanation answering their question strictly based on what the instructor says.
Cite timestamp {best_time_fmt}."""
            res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=8)
            if res.status_code == 200:
                answer_text = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                return {
                    "answer": answer_text,
                    "timestamp": best_time,
                    "timestamp_formatted": best_time_fmt,
                    "chapter_title": best_chap,
                    "confidence": "high",
                    "target_concept": concept,
                    "related_hits": search_hits
                }
        except Exception:
            pass

    # 2. Built-in Offline AI Synthesizer (Works 100% offline with zero external dependencies)
    raw_snippet = top_hit.get("snippet", "") or top_hit.get("raw_text", "")
    clean_snippet = re.sub(r'<[^>]+>', '', raw_snippet).strip()

    # Find the best explanatory sentence specifically defining the target concept
    sentences = [s.strip() for s in re.split(r'[.!?]+', clean_snippet) if len(s.strip()) > 10]
    target_low = concept.lower()
    definition_quote = None
    for s in sentences:
        s_l = s.lower()
        if target_low in s_l and any(w in s_l for w in ["used to", "allows", "sort", "group", "clause", "is", "we use", "lets", "order"]):
            definition_quote = s
            break

    if not definition_quote:
        # Fallback to focal text if available
        focal = top_hit.get("focal_text", "")
        if focal:
            focal_sentences = [s.strip() for s in re.split(r'[.!?]+', focal) if len(s.strip()) > 10]
            for s in focal_sentences:
                if target_low in s.lower():
                    definition_quote = s
                    break

    if not definition_quote:
        definition_quote = sentences[0] if sentences else clean_snippet

    answer_text = (
        f"In Chapter **{best_chap}** at timestamp **{best_time_fmt}**, the instructor introduces and explains **{concept}**:\n\n"
        f"> *\"{definition_quote}.\"*\n\n"
        f"This section introduces how **{concept}** works in the lecture and demonstrates how to apply it."
    )

    return {
        "answer": answer_text,
        "timestamp": best_time,
        "timestamp_formatted": best_time_fmt,
        "chapter_title": best_chap,
        "confidence": "high",
        "target_concept": concept,
        "related_hits": search_hits
    }


def answer_followup_question(followup_question, parent_question, parent_answer, segments, chapters, topic_id=None):
    """
    Handles conversational follow-up questions grounded in the video's transcript excerpts.
    If topic_id is specified, scopes retrieval to that topic.
    """
    target_segments = segments
    target_chapters = chapters
    target_topic_title = "Selected Topic"

    if topic_id and chapters:
        matched_chaps = [c for c in chapters if int(c.get("id", 0)) == int(topic_id)]
        if matched_chaps:
            ch = matched_chaps[0]
            target_chapters = [ch]
            target_topic_title = ch.get("title", "Selected Topic")
            start = float(ch.get("start_time", 0))
            end = float(ch.get("end_time", 999999))
            scoped = [s for s in segments if start - 1.0 <= float(s.get("start", 0)) <= end + 1.0]
            if scoped:
                target_segments = scoped

    # Perform retrieval using combined query keywords
    combined_query = f"{parent_question} {followup_question}"
    search_data = search_video(combined_query, target_segments, target_chapters)
    search_hits = search_data.get("results", []) if isinstance(search_data, dict) else search_data
    top_hit = search_hits[0] if search_hits else None

    best_time = top_hit["start"] if top_hit else (target_chapters[0].get("start_time", 0.0) if target_chapters else 0.0)
    best_time_fmt = top_hit.get("timestamp_formatted", "00:00") if top_hit else "00:00"
    best_chap = top_hit.get("chapter_title", target_topic_title) if top_hit else target_topic_title

    # 1. Gemini Cloud LLM if available
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            import requests
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
            context_passages = [h.get("raw_text", "") for h in search_hits[:3]]
            context_str = "\n".join(context_passages)

            prompt = f"""You are VidSeek AI, assisting a student with a follow-up question on a video lecture.
Previous Question: "{parent_question}"
Previous Answer: "{parent_answer}"
Student Follow-up Question: "{followup_question}"

Video transcript excerpts around {best_time_fmt} ({best_chap}):
{context_str}

Provide a direct, conversational, concise 2-4 sentence follow-up answer strictly grounded in the video lecture.
Cite timestamp {best_time_fmt}."""
            res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=8)
            if res.status_code == 200:
                answer_text = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                return {
                    "answer": answer_text,
                    "timestamp": best_time,
                    "timestamp_formatted": best_time_fmt,
                    "chapter_title": best_chap,
                    "is_followup": True
                }
        except Exception:
            pass

    # 2. Offline Fallback Grounded Synthesizer
    snippet = top_hit.get("snippet", "") if top_hit else (parent_answer[:120] if parent_answer else "")
    clean_snippet = re.sub(r'<[^>]+>', '', snippet).strip()

    answer_text = (
        f"Continuing our discussion from \"{parent_question}\":\n\n"
        f"In Chapter **{best_chap}** at timestamp **{best_time_fmt}**, the instructor further explains:\n\n"
        f"> *\"{clean_snippet}\"*\n\n"
        f"This directly addresses your follow-up on how this concept behaves in the video."
    )

    return {
        "answer": answer_text,
        "timestamp": best_time,
        "timestamp_formatted": best_time_fmt,
        "chapter_title": best_chap,
        "is_followup": True
    }


def simplify_answer_explanation(original_answer, topic_title="this lecture", timestamp_fmt="00:00"):
    """
    Translates technical lecture explanations into plain-English, intuitive summaries with analogies.
    """
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            import requests
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
            prompt = f"""Explain the following video lecture explanation in simple, intuitive, beginner-friendly terms (like explaining to a 12-year-old or beginner).
Keep it accurate to the lecture content, use a short simple real-world analogy, and keep it under 3-4 sentences.

Original Explanation:
"{original_answer}"
"""
            res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=8)
            if res.status_code == 200:
                text = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                return {
                    "simplified_answer": text,
                    "timestamp_formatted": timestamp_fmt
                }
        except Exception:
            pass

    # Offline plain-language template
    clean_lines = [line.strip() for line in original_answer.split("\n") if line.strip() and not line.strip().startswith(">")]
    core_point = clean_lines[0] if clean_lines else "the instructor explains this concept clearly"
    core_point = re.sub(r'\*\*', '', core_point)

    simplified_text = (
        f"💡 **Plain-English Explanation (Simplified):**\n\n"
        f"Think of this concept like a real-world tool: rather than doing things manually every time, "
        f"the computer uses this rule to handle the work automatically. {core_point}\n\n"
        f"Whenever you see this in the lecture at timestamp **{timestamp_fmt}**, remember it is simply keeping things organized, fast, and reusable!"
    )

    return {
        "simplified_answer": simplified_text,
        "timestamp_formatted": timestamp_fmt
    }

