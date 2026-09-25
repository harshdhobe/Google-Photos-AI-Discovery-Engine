"""Google Play Store collector for Google Photos reviews (Layer 1)."""

from __future__ import annotations

from datetime import datetime
from typing import Any


APP_ID = "com.google.android.apps.photos"
SOURCE = "play_store"


def _to_iso_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def _normalize_review(review: dict[str, Any]) -> dict[str, Any] | None:
    text = (review.get("content") or "").strip()
    if not text:
        return None

    item_id = review.get("reviewId")
    if not item_id:
        return None

    rating = review.get("score")
    if rating is not None:
        try:
            rating = int(rating)
        except (TypeError, ValueError):
            rating = None

    return {
        "source": SOURCE,
        "item_id": str(item_id),
        "text": text,
        "date": _to_iso_date(review.get("at")),
        "rating": rating,
    }


def collect_play_store_reviews(count: int = 100) -> list[dict[str, Any]]:
    """Pull newest Google Photos Play Store reviews into Layer 1 records."""
    try:
        from google_play_scraper import Sort, reviews
    except ImportError:
        print("google-play-scraper is not installed. Install requirements.txt first.")
        return []

    try:
        # Request a buffer so any reviews with empty content don't reduce the final count below target
        fetch_count = int(count * 1.15) + 10
        result, _continuation = reviews(
            APP_ID,
            lang="en",
            country="us",
            sort=Sort.NEWEST,
            count=fetch_count,
        )
    except Exception as exc:
        print(f"Play Store collection failed: {exc}")
        return []

    records: list[dict[str, Any]] = []
    for review in result or []:
        normalized = _normalize_review(review)
        if normalized:
            records.append(normalized)
        if len(records) >= count:
            break
    return records
