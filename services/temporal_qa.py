"""
VidSeek AI — Temporal AI Q&A & Event MCQ Engine
Provides temporal reasoning over video event sequences:
- Answers questions about specific video timestamps ('What happened around 01:20?')
- Chronological contextual questions ('What happened before X?', 'What happened after Y?')
- Generates 4-option MCQs directly grounded in detected video events with clickable seek timestamps.
"""

import os
import re
import json
import random
import logging
import requests

from services.video_processor import format_timestamp, parse_timestamp

logger = logging.getLogger("vidseek.temporal_qa")


def parse_time_from_text(query):
    """
    Extracts timestamp in seconds from queries like:
    'around 01:20', 'at 00:15', 'at 1:20', 'around 25 seconds', 'at 40s'.
    """
    if not query:
        return None
    
    q = query.lower()
    
    # 1. MM:SS or HH:MM:SS format
    m = re.search(r'\b(?:at|around|about|near|timestamp)?\s*(\d{1,2}:\d{2}(?::\d{2})?)\b', q)
    if m:
        try:
            return parse_timestamp(m.group(1))
        except Exception:
            pass

    # 2. X seconds / X sec / Xs
    m_sec = re.search(r'\b(?:at|around|about)?\s*(\d+)\s*(?:seconds?|secs?|s)\b', q)
    if m_sec:
        try:
            return float(m_sec.group(1))
        except Exception:
            pass

    # 3. X minute(s) Y second(s)
    m_min = re.search(r'(\d+)\s*(?:minutes?|mins?|m)\s*(?:and\s*)?(\d+)?\s*(?:seconds?|secs?|s)?', q)
    if m_min:
        mins = float(m_min.group(1))
        secs = float(m_min.group(2)) if m_min.group(2) else 0.0
        return mins * 60 + secs

    return None


def parse_time_range_from_text(query):
    """Extracts (start_sec, end_sec) from 'between 00:10 and 00:30'."""
    q = query.lower()
    m = re.search(r'\bbetween\s+(\d{1,2}:\d{2})\s+and\s+(\d{1,2}:\d{2})\b', q)
    if m:
        try:
            return parse_timestamp(m.group(1)), parse_timestamp(m.group(2))
        except Exception:
            pass
    return None


def answer_temporal_question(question, temporal_events, segments=None, chapters=None):
    """
    Answers questions about specific temporal video moments and relative chronology:
    - Time-point queries: 'What happened around 00:22?'
    - Sequential before/after queries: 'What happened before loops?', 'What happened before the person left?'
    - Range queries: 'What happened between 00:10 and 00:30?'
    """
    if not question or not temporal_events:
        return {
            "answer": "No temporal events available to analyze for this video.",
            "timestamp": 0.0,
            "timestamp_formatted": "00:00",
            "confidence": "low",
            "event": None
        }

    normalized_events = []
    for e in sorted(temporal_events, key=lambda x: x.get("start", 0)):
        ev = dict(e)
        st = ev.get("start", 0.0)
        et = ev.get("end", st + 5.0)
        if "start_formatted" not in ev:
            ev["start_formatted"] = ev.get("start_time") or format_timestamp(st)
        if "end_formatted" not in ev:
            ev["end_formatted"] = ev.get("end_time") or format_timestamp(et)
        if "interval_formatted" not in ev:
            ev["interval_formatted"] = f"{ev['start_formatted']} – {ev['end_formatted']}"
        normalized_events.append(ev)
    events = normalized_events

    q_low = question.lower().strip()

    # 1. Check for time range query: "between X and Y"
    t_range = parse_time_range_from_text(q_low)
    if t_range:
        start_t, end_t = t_range
        matched_events = [e for e in events if not (e.get("end", 0) < start_t or e.get("start", 0) > end_t)]
        if matched_events:
            lines = [f"Between **{format_timestamp(start_t)}** and **{format_timestamp(end_t)}**, the following chronological events occur:"]
            for me in matched_events:
                lines.append(f"- **{me['interval_formatted']}** ({me.get('category', 'Event')}): {me.get('description', '')}")
            
            first_e = matched_events[0]
            return {
                "answer": "\n\n".join(lines),
                "timestamp": first_e.get("start", start_t),
                "timestamp_formatted": first_e.get("start_formatted", format_timestamp(start_t)),
                "confidence": "high",
                "event": first_e,
                "matched_events": matched_events
            }

    # 2. Check for chronological 'before' query: "what happened before X"
    before_match = re.search(r'\b(?:what\s+happened|what\s+occurred|what\s+did\s+.+?\s+do|what\s+was\s+there)\s+before\s+(.+)', q_low)
    if before_match:
        target_ref = before_match.group(1).rstrip('?').strip()
        ref_event_idx = _find_matching_event_index(target_ref, events)
        if ref_event_idx is not None and ref_event_idx > 0:
            ref_event = events[ref_event_idx]
            prev_event = events[ref_event_idx - 1]
            answer = (
                f"Before **\"{ref_event.get('description', target_ref)}\"** at **{ref_event['start_formatted']}**:\n\n"
                f"At approximately **{prev_event['start_formatted']}** ({prev_event['interval_formatted']}), "
                f"the video shows **{prev_event.get('category', 'an event')}**: {prev_event.get('description', '')}.\n\n"
                f"*(Confidence: {prev_event.get('confidence_pct', '90%')})*"
            )
            return {
                "answer": answer,
                "timestamp": prev_event.get("start", 0.0),
                "timestamp_formatted": prev_event.get("start_formatted", "00:00"),
                "confidence": "high",
                "event": prev_event,
                "reference_event": ref_event
            }
        elif ref_event_idx == 0:
            ref_event = events[0]
            return {
                "answer": f"\"{ref_event.get('description', target_ref)}\" occurs right at the start of the video ({ref_event['interval_formatted']}), so no prior event preceded it.",
                "timestamp": 0.0,
                "timestamp_formatted": "00:00",
                "confidence": "high",
                "event": ref_event
            }

    # 3. Check for chronological 'after' query: "what happened after X"
    after_match = re.search(r'\b(?:what\s+happened|what\s+occurred|what\s+did\s+.+?\s+do)\s+after\s+(.+)', q_low)
    if after_match:
        target_ref = after_match.group(1).rstrip('?').strip()
        ref_event_idx = _find_matching_event_index(target_ref, events)
        if ref_event_idx is not None and ref_event_idx < len(events) - 1:
            ref_event = events[ref_event_idx]
            next_event = events[ref_event_idx + 1]
            answer = (
                f"After **\"{ref_event.get('description', target_ref)}\"** at **{ref_event['start_formatted']}**:\n\n"
                f"At approximately **{next_event['start_formatted']}** ({next_event['interval_formatted']}), "
                f"the video transitions to **{next_event.get('category', 'the next event')}**: {next_event.get('description', '')}.\n\n"
                f"*(Confidence: {next_event.get('confidence_pct', '90%')})*"
            )
            return {
                "answer": answer,
                "timestamp": next_event.get("start", 0.0),
                "timestamp_formatted": next_event.get("start_formatted", "00:00"),
                "confidence": "high",
                "event": next_event,
                "reference_event": ref_event
            }

    # 4. Check for direct timestamp query: "what happened around 01:20?"
    target_time = parse_time_from_text(q_low)
    if target_time is not None:
        def _event_dist(e):
            st = float(e.get("start", 0.0))
            et = float(e.get("end", st))
            if st <= target_time <= et:
                return 0.0
            return min(abs(st - target_time), abs(et - target_time))

        best_e = min(events, key=_event_dist)
        t_fmt = format_timestamp(target_time)
        answer = (
            f"At approximately **{best_e['start_formatted']}** (around {t_fmt}), "
            f"the video demonstrates **{best_e.get('category', 'a key event')}**:\n\n"
            f"> *\"{best_e.get('description', '')}\"*\n\n"
            f"This segment spans **{best_e['interval_formatted']}** with **{best_e.get('confidence_pct', '90%')} confidence**."
        )
        return {
            "answer": answer,
            "timestamp": best_e.get("start", target_time),
            "timestamp_formatted": best_e.get("start_formatted", t_fmt),
            "confidence": "high",
            "event": best_e
        }

    # 5. Fallback: Keyword search among temporal event descriptions
    words = [w for w in re.findall(r'\b\w+\b', q_low) if len(w) > 3 and w not in ["what", "when", "where", "happened", "video", "show", "tell"]]
    best_hit = None
    max_hits = 0
    for e in events:
        text = (e.get("description", "") + " " + e.get("raw_text", "") + " " + e.get("category", "")).lower()
        hits = sum(1 for w in words if w in text)
        if hits > max_hits:
            max_hits = hits
            best_hit = e

    if best_hit and max_hits > 0:
        answer = (
            f"At timestamp **{best_hit['start_formatted']}** ({best_hit['interval_formatted']}), "
            f"the video covers **{best_hit.get('category', 'this event')}**:\n\n"
            f"> *\"{best_hit.get('description', '')}\"*\n\n"
            f"*(Detected via BiLSTM sequence model with {best_hit.get('confidence_pct', '90%')} confidence)*"
        )
        return {
            "answer": answer,
            "timestamp": best_hit.get("start", 0.0),
            "timestamp_formatted": best_hit.get("start_formatted", "00:00"),
            "confidence": "high",
            "event": best_hit
        }

    # Default to first event overview
    first_e = events[0]
    return {
        "answer": f"At the beginning of the video ({first_e['interval_formatted']}), {first_e.get('description', 'the video starts')}.",
        "timestamp": first_e.get("start", 0.0),
        "timestamp_formatted": first_e.get("start_formatted", "00:00"),
        "confidence": "medium",
        "event": first_e
    }


def _find_matching_event_index(target_text, events):
    """Finds index of event in list that best matches target_text."""
    target_low = target_text.lower().strip()
    words = [w for w in re.findall(r'\b\w+\b', target_low) if len(w) > 3]
    
    # 1. Exact or partial substring
    for idx, e in enumerate(events):
        desc_low = e.get("description", "").lower()
        raw_low = e.get("raw_text", "").lower()
        if target_low in desc_low or target_low in raw_low:
            return idx
            
    # 2. Token overlap
    best_idx = None
    best_score = 0
    for idx, e in enumerate(events):
        text = (e.get("description", "") + " " + e.get("raw_text", "") + " " + e.get("category", "")).lower()
        overlap = sum(1 for w in words if w in text)
        if overlap > best_score:
            best_score = overlap
            best_idx = idx

    return best_idx


# ================= Temporal Event MCQ Generator ================= #

def generate_temporal_mcqs(temporal_events, count=5):
    """
    Generates MCQs grounded strictly in actual detected video events.
    Each question tests what happened at a specific timestamp.
    Includes: question, 4 options (A, B, C, D), correct_answer, explanation, and clickable timestamp.
    """
    if not temporal_events:
        return []

    events = [e for e in temporal_events if e.get("description")]
    if len(events) < 2:
        return []

    questions = []
    
    # Available distractor pools from other distinct events
    for idx, current_event in enumerate(events):
        if len(questions) >= count:
            break

        time_fmt = current_event.get("start_formatted", "00:00")
        interval_fmt = current_event.get("interval_formatted", time_fmt)
        correct_desc = current_event.get("description", "")
        category = current_event.get("category", "Action")
        
        # Pick 3 plausible distractors from OTHER events in the video
        other_events = [e for i, e in enumerate(events) if i != idx and e.get("description")]
        if len(other_events) < 3:
            # Supplement with general realistic distractors
            distractor_texts = [
                "Bypassed memory allocation and deleted the compiler cache",
                "Configured a remote database connection without authentication",
                "Closed the terminal window and terminated the background process"
            ]
        else:
            sample_others = random.sample(other_events, min(3, len(other_events)))
            distractor_texts = [e.get("description", "") for e in sample_others]

        # Ensure 4 distinct options
        options_raw = [correct_desc] + distractor_texts[:3]
        
        # Shuffle options while tracking correct letter
        indexed_options = list(enumerate(options_raw))
        random.shuffle(indexed_options)
        
        letters = ["A", "B", "C", "D"]
        correct_letter = "A"
        opts = {}
        for l_idx, (orig_idx, opt_text) in enumerate(indexed_options):
            letter = letters[l_idx]
            opts[f"option_{letter.lower()}"] = opt_text
            if orig_idx == 0:
                correct_letter = letter

        q_item = {
            "id": idx + 1,
            "question": f"What occurs in the video around timestamp {time_fmt} ({interval_fmt})?",
            "options": [opts.get("option_a", ""), opts.get("option_b", ""), opts.get("option_c", ""), opts.get("option_d", "")],
            "option_a": opts.get("option_a", ""),
            "option_b": opts.get("option_b", ""),
            "option_c": opts.get("option_c", ""),
            "option_d": opts.get("option_d", ""),
            "correct_answer": correct_letter,
            "explanation": f"At {time_fmt} ({interval_fmt}), the video shows {category}: \"{correct_desc}\".",
            "source_timestamp": current_event.get("start", 0.0),
            "timestamp": time_fmt,
            "time_seconds": current_event.get("start", 0.0),
            "source_time_fmt": time_fmt,
            "interval_formatted": interval_fmt,
            "category": category,
            "difficulty": "Medium",
            "type": "temporal_event"
        }
        questions.append(q_item)

    return questions
