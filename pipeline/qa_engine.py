"""
Discovery Engine — Phase 5 Grounded Q&A Retrieval Engine.

Implements lexical retrieval and cited RAG synthesis over the verified SQLite tagged corpus.
All responses are grounded strictly in authentic user feedback with exact [Source #ID] citations.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DB_PATH = BASE_DIR / "data" / "tagged.db"

# Synonym expansion map for photo retrieval domain
SYNONYMS: dict[str, list[str]] = {
    "person": ["people", "face", "faces", "someone", "friend", "family", "child", "baby"],
    "people": ["person", "face", "faces", "group", "family"],
    "face": ["faces", "person", "people", "facial", "recognition"],
    "time": ["date", "year", "month", "summer", "winter", "years", "ago", "old", "rough_time_period"],
    "date": ["time", "year", "calendar", "timestamp", "exact_date"],
    "workaround": ["scroll", "scrolling", "manual", "spreadsheet", "whatsapp", "gave_up"],
    "scroll": ["scrolling", "manual", "workaround", "timeline"],
    "nothing": ["zero", "empty", "blank", "query_returned_nothing", "no results"],
    "receipt": ["receipts", "document", "order", "screenshot", "bill"],
    "screenshot": ["screenshots", "document", "receipt", "text"],
}


def clean_tokens(text: str) -> set[str]:
    """Tokenize and normalize text into clean words."""
    if not text:
        return set()
    words = re.findall(r"\b[a-zA-Z0-9_-]{3,}\b", text.lower())
    tokens = set(words)
    # Add domain synonyms
    expanded = set(tokens)
    for t in tokens:
        if t in SYNONYMS:
            expanded.update(SYNONYMS[t])
    return expanded


def parse_json_list(val: Any) -> list[str]:
    """Parse a stored JSON list safely."""
    if not val:
        return []
    if isinstance(val, list):
        return [str(x) for x in val if x]
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return [str(x) for x in parsed if x]
        except Exception:
            pass
    return []


def load_tagged_items(db_path: Path = DB_PATH) -> list[dict[str, Any]]:
    """Load all relevant tagged items from SQLite."""
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, item_id, source, raw_text, date, rating,
                   is_relevant, photo_type, memory_cues_retained, memory_cues_missing,
                   failure_stage, workaround, representative_quote, tagged_at
            FROM tagged_items
            WHERE is_relevant = 1
            ORDER BY id ASC
            """
        )
        items = []
        for r in cur.fetchall():
            d = dict(r)
            d["retained_cues"] = parse_json_list(d.get("memory_cues_retained"))
            d["missing_cues"] = parse_json_list(d.get("memory_cues_missing"))
            d["photo_type"] = d.get("photo_type") or "(not_stated)"
            d["failure_stage"] = d.get("failure_stage") or "(not_stated)"
            d["workaround"] = d.get("workaround") or "none"
            d["quote"] = (d.get("representative_quote") or "").strip()
            
            # Format friendly citation label
            src = d["source"]
            if src == "google_photos_community":
                src_label = "Community"
            elif src.startswith("reddit"):
                src_label = "Reddit"
            elif src == "youtube_comment":
                src_label = "YouTube"
            elif src == "app_store":
                src_label = "AppStore"
            elif src == "play_store":
                src_label = "PlayStore"
            else:
                src_label = src.capitalize()
            d["citation_label"] = f"[{src_label} #{d['item_id']}]"
            
            # Build search index tokens
            searchable_text = f"{d['quote']} {d['raw_text']} {d['photo_type']} {d['failure_stage']} {d['workaround']} {' '.join(d['retained_cues'])} {' '.join(d['missing_cues'])}"
            d["tokens"] = clean_tokens(searchable_text)
            items.append(d)
        return items
    finally:
        conn.close()


def score_item(query_tokens: set[str], query_raw: str, item: dict[str, Any]) -> float:
    """Compute heuristic relevance score of an item against query tokens."""
    score = 0.0
    item_tokens = item.get("tokens", set())
    
    # Exact phrase matches
    q_lower = query_raw.lower()
    raw_lower = item["raw_text"].lower()
    quote_lower = item["quote"].lower()
    
    if q_lower in quote_lower and len(q_lower) > 4:
        score += 25.0
    elif q_lower in raw_lower and len(q_lower) > 4:
        score += 15.0

    # Token overlaps
    shared_tokens = query_tokens.intersection(item_tokens)
    score += len(shared_tokens) * 3.0

    # Boost for specific fields
    if any(t in item["photo_type"].lower() for t in query_tokens):
        score += 8.0
    if any(t in item["failure_stage"].lower() for t in query_tokens):
        score += 8.0
    if any(t in item["workaround"].lower() for t in query_tokens):
        score += 8.0

    # Boost if item has a strong representative quote
    if len(item["quote"]) >= 20 and item["quote"].lower() not in ("none", "n/a"):
        score += 2.0

    return score


def retrieve_relevant_items(
    query: str,
    items: list[dict[str, Any]],
    top_k: int = 6,
) -> list[dict[str, Any]]:
    """Retrieve top-k most relevant feedback items for a query."""
    if not items:
        return []
    
    q_tokens = clean_tokens(query)
    scored = []
    for item in items:
        s = score_item(q_tokens, query, item)
        if s > 0:
            scored.append((s, item))

    # Sort descending by score
    scored.sort(key=lambda x: x[0], reverse=True)

    # Return top_k items
    if scored:
        return [it for _, it in scored[:top_k]]
    
    # Fallback if no lexical match: return items with longest quotes
    fallback = sorted(items, key=lambda x: len(x["quote"]), reverse=True)
    return fallback[:top_k]


def format_evidence_context(retrieved_items: list[dict[str, Any]]) -> str:
    """Format retrieved items into a structured evidence string for the LLM prompt."""
    blocks = []
    for idx, it in enumerate(retrieved_items, 1):
        blocks.append(
            f"Evidence Item {idx}: {it['citation_label']}\n"
            f"- Source: {it['source']}\n"
            f"- Photo Type: {it['photo_type']}\n"
            f"- Failure Stage: {it['failure_stage']}\n"
            f"- Workaround Attempted: {it['workaround']}\n"
            f"- Retained Cues: {', '.join(it['retained_cues']) or 'none'}\n"
            f"- Missing Cues: {', '.join(it['missing_cues']) or 'none'}\n"
            f"- Verbatim Quote: \"{it['quote']}\"\n"
            f"- Full Feedback Snippet: \"{it['raw_text'][:280].replace(chr(10), ' ')}\"\n"
        )
    return "\n".join(blocks)


def ask_grounded_qa(
    query: str,
    items: Optional[list[dict[str, Any]]] = None,
    api_key: Optional[str] = None,
    top_k: int = 6,
) -> dict[str, Any]:
    """
    Synthesizes a grounded answer with strict citations to authentic user feedback.
    Uses Groq llama-3.3-70b-versatile via OpenAI-compatible API.
    """
    if items is None:
        items = load_tagged_items()

    if not items:
        return {
            "query": query,
            "answer": "No tagged items found in database. Please verify `data/tagged.db` is populated.",
            "evidence": [],
        }

    retrieved = retrieve_relevant_items(query, items, top_k=top_k)
    evidence_text = format_evidence_context(retrieved)

    # Resolve API key
    key = api_key or os.getenv("GROQ_API_KEY")
    if not key:
        return {
            "query": query,
            "answer": (
                "⚠️ **Groq API key not detected.**\n\n"
                "Please configure `GROQ_API_KEY` in your `.env` file or enter it in the sidebar "
                "to generate cited answers from the LLM.\n\n"
                "In the meantime, you can inspect the retrieved evidence items below directly from the corpus."
            ),
            "evidence": retrieved,
        }

    from openai import OpenAI

    client = OpenAI(
        api_key=key,
        base_url="https://api.groq.com/openai/v1",
    )

    system_prompt = (
        "You are an expert Google Photos Product Discovery Research Assistant preparing evidence for a PM case study. "
        "You are analyzing authentic user feedback concerning vague-memory photo retrieval struggles.\n\n"
        "STRICT GROUNDING RULES:\n"
        "1. Base your answer EXCLUSIVELY and SOLELY on the provided Evidence Items. Do not speculate or introduce unverified assumptions.\n"
        "2. EVERY assertion, finding, or cited behavioral pattern MUST be explicitly cited inline with the exact item label, "
        "e.g. [Community #468729533:0], [Reddit #1wi9thz], or [YouTube #Ugx93_R2n6SjY4eM2lV4AaABAg].\n"
        "3. Structure your answer cleanly with:\n"
        "   - **Direct Answer / Finding Summary**\n"
        "   - **Behavioral Evidence & User Patterns** (citing specific quotes and metrics)\n"
        "   - **PM Takeaway / Opportunity**\n"
        "4. Quote users verbatim when illustrating emotional frustration or exact failure behavior.\n"
        "5. If the provided evidence is silent or insufficient on any point, explicitly state: 'The retrieved corpus contains insufficient data to determine...'"
    )

    user_prompt = (
        f"RESEARCH QUESTION:\n{query}\n\n"
        f"RETRIEVED CORPUS EVIDENCE (ONLY USE THESE ITEMS):\n"
        f"{evidence_text}\n\n"
        f"Provide your cited research synthesis adhering to the grounding rules."
    )

    candidate_models = ["openai/gpt-oss-120b", "llama-3.1-8b-instant", "llama3-70b-8192"]
    last_err = None

    for model_name in candidate_models:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=900,
            )
            answer = completion.choices[0].message.content or ""
            return {
                "query": query,
                "answer": answer.strip(),
                "evidence": retrieved,
            }
        except Exception as e:
            last_err = e
            continue

    return {
        "query": query,
        "answer": f"⚠️ Error calling Groq API: {str(last_err)}\n\nPlease check your API key or network connection.",
        "evidence": retrieved,
    }
