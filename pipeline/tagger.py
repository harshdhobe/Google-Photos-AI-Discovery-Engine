"""
Groq LLaMA-3.3-70B AI Tagger for Discovery Engine Layer 2.
Calls Groq OpenAI-compatible endpoint with JSON mode, rate limiting, and retries.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Dict, Optional, Tuple

from dotenv import load_dotenv

from pipeline.schema import (
    VALID_FAILURE_STAGES,
    VALID_MEMORY_CUES_MISSING,
    VALID_MEMORY_CUES_RETAINED,
    VALID_PHOTO_TYPES,
    VALID_WORKAROUNDS,
    normalize_tag,
    validate_tag,
)

load_dotenv()

logger = logging.getLogger("pipeline.tagger")

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = "openai/gpt-oss-120b"

# Groq free tier: 30 RPM, 14,400 req/day -> minimum 2.1s between calls.
DEFAULT_REQUEST_INTERVAL_SECONDS = 2.1

TAGGER_SYSTEM_PROMPT = f"""You are an expert product discovery analyst analyzing user feedback for Google Photos.
Your job is to identify pain points related to VAGUE-MEMORY PHOTO RETRIEVAL:
Users trying to find a specific photo/video when they only remember partial, vague cues (e.g., "that beach trip 3 years ago", "receipt for printer", "picture with Sarah wearing a red hat"), rather than exact dates or technical metadata.

You must evaluate the user feedback and return ONLY a valid JSON object with EXACTLY these 7 keys:

1. "is_relevant": (boolean) true if the feedback touches on searching, finding, retrieving, organizing photos for discovery, or failing to find photos with vague recall. false if it is purely about storage limits, pricing, backup/sync errors, app installation, UI redesign complaints unrelated to search, etc.

2. "photo_type": (string or null) The subject of the photo being sought. Must be one of:
   {sorted(list(VALID_PHOTO_TYPES))} or null.

3. "memory_cues_retained": (list of strings) Cues the user remembered. Subset of:
   {sorted(list(VALID_MEMORY_CUES_RETAINED))}. Use ["none_mentioned"] if none or if is_relevant is false.

4. "memory_cues_missing": (list of strings) Details the user could NOT remember or lacked. Subset of:
   {sorted(list(VALID_MEMORY_CUES_MISSING))}. Use ["none_mentioned"] if none or if is_relevant is false.

5. "failure_stage": (string or null) Where the retrieval process failed. Must be one of:
   {sorted(list(VALID_FAILURE_STAGES))} or null.

6. "workaround": (string or null) How the user attempted to cope. Must be one of:
   {sorted(list(VALID_WORKAROUNDS))} or null.

7. "representative_quote": (string or null) Verbatim substring from the user feedback highlighting the search struggle or problem, or null.

If "is_relevant" is false, set photo_type, failure_stage, workaround, and representative_quote to null, and set memory cue lists to ["none_mentioned"].
Respond with nothing else except the JSON object.
"""


class RateLimiter:
    """Enforces a minimum interval between API calls."""

    def __init__(self, interval_seconds: float = DEFAULT_REQUEST_INTERVAL_SECONDS):
        self.interval_seconds = interval_seconds
        self.last_call_time: float = 0.0

    def wait(self) -> None:
        elapsed = time.time() - self.last_call_time
        if elapsed < self.interval_seconds:
            time.sleep(self.interval_seconds - elapsed)
        self.last_call_time = time.time()


class CerebrasTagger:
    """Tagger client using Groq OpenAI-compatible API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = GROQ_BASE_URL,
        model: str = GROQ_MODEL,
        interval_seconds: float = DEFAULT_REQUEST_INTERVAL_SECONDS,
    ):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.base_url = base_url
        self.model = model
        self.rate_limiter = RateLimiter(interval_seconds)
        self._client = None

    def _get_client(self):
        if self._client is None:
            if not self.api_key:
                raise ValueError(
                    "GROQ_API_KEY not found in environment or constructor. "
                    "Please add GROQ_API_KEY=your_key to .env (free at console.groq.com) or use mock mode."
                )
            try:
                from openai import OpenAI
                self._client = OpenAI(
                    base_url=self.base_url,
                    api_key=self.api_key,
                )
            except ImportError:
                raise ImportError("The 'openai' package is required for Groq API calls. Run 'pip install openai'.")
        return self._client

    def tag_item(self, item: Dict[str, Any], max_retries: int = 3) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Tags a single item dict using Cerebras LLaMA 3.3 70B.
        Returns (tag_dict, None) on success, or (None, error_msg) on failure.
        """
        text = item.get("text", "").strip()
        if not text:
            return None, "Empty text"

        client = self._get_client()

        messages = [
            {"role": "system", "content": TAGGER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Source: {item.get('source', 'unknown')}\nUser Feedback:\n\"\"\"{text}\"\"\"",
            },
        ]

        attempt = 0
        backoff = 2.0

        while attempt < max_retries:
            attempt += 1
            try:
                self.rate_limiter.wait()
                response = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.1,
                )

                raw_content = response.choices[0].message.content
                if not raw_content:
                    raise ValueError("Model returned empty response content")

                parsed = json.loads(raw_content)
                normalized = normalize_tag(parsed)
                is_valid, errors = validate_tag(normalized)

                if is_valid:
                    return normalized, None

                logger.warning("Tag validation error on attempt %d: %s", attempt, errors)
                # If invalid schema, prompt correction on retry
                messages.append({"role": "assistant", "content": raw_content})
                messages.append({
                    "role": "user",
                    "content": f"The previous JSON had schema errors: {'; '.join(errors)}. Return the corrected JSON object.",
                })

            except Exception as e:
                err_str = str(e)
                logger.warning("Cerebras API attempt %d failed: %s", attempt, err_str)
                if attempt >= max_retries:
                    return None, f"Failed after {max_retries} attempts: {err_str}"
                time.sleep(backoff)
                backoff *= 2.0

        return None, "Max retries exceeded"


def mock_tag_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deterministic heuristic mock tagger for local testing / dry-runs without API keys.
    Detects photo retrieval cues and returns valid Layer 2 tags.
    """
    text = (item.get("text") or "").lower()

    # Keywords suggesting search / retrieval struggles
    search_keywords = ["search", "find", "look for", "looking for", "lost photo", "locate", "scroll", "album", "where is"]
    is_search = any(kw in text for kw in search_keywords)

    if not is_search:
        return {
            "is_relevant": False,
            "photo_type": None,
            "memory_cues_retained": ["none_mentioned"],
            "memory_cues_missing": ["none_mentioned"],
            "failure_stage": None,
            "workaround": None,
            "representative_quote": None,
        }

    # Photo type heuristics
    photo_type = "other"
    if any(w in text for w in ["trip", "vacation", "beach", "hotel", "flight", "travel"]):
        photo_type = "travel"
    elif any(w in text for w in ["wedding", "party", "birthday", "concert", "event"]):
        photo_type = "event"
    elif any(w in text for w in ["screenshot", "screen shot"]):
        photo_type = "screenshot"
    elif any(w in text for w in ["receipt", "bill", "document", "invoice", "paper"]):
        photo_type = "document_receipt"
    elif any(w in text for w in ["baby", "mom", "dad", "friend", "cousin", "daughter", "son"]):
        photo_type = "person"

    # Retained cues
    retained = []
    if any(w in text for w in ["years ago", "yesterday", "last month", "summer", "december", "202"]):
        retained.append("rough_time_period")
    if any(w in text for w in ["beach", "park", "paris", "home", "city", "lake"]):
        retained.append("place")
    if any(w in text for w in ["red shirt", "dog", "car", "sunset", "blue"]):
        retained.append("visual_detail")
    if not retained:
        retained = ["none_mentioned"]

    # Missing cues
    missing = []
    if any(w in text for w in ["exact date", "when was", "what day"]):
        missing.append("exact_date")
    if any(w in text for w in ["don't remember where", "no location"]):
        missing.append("location_name")
    if not missing:
        missing = ["search_terms"]

    # Failure stage
    failure_stage = "query_returned_nothing"
    if any(w in text for w in ["too many", "hundreds", "cluttered"]):
        failure_stage = "query_returned_too_much"
    elif any(w in text for w in ["gave up", "impossible", "can't find"]):
        failure_stage = "gave_up"

    # Workaround
    workaround = "manual_scrolling" if "scroll" in text else "none"

    # Representative quote
    raw_text = item.get("text", "")
    quote = raw_text[:80] + "..." if len(raw_text) > 80 else raw_text

    return {
        "is_relevant": True,
        "photo_type": photo_type,
        "memory_cues_retained": retained,
        "memory_cues_missing": missing,
        "failure_stage": failure_stage,
        "workaround": workaround,
        "representative_quote": quote,
    }
