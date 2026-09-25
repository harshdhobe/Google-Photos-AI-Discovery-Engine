"""
Prefiltering and deduplication for Discovery Engine raw collected items.
Cleans raw text, discards empty/whitespace records, and removes duplicate item IDs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple


def clean_item(item: Dict[str, Any]) -> Dict[str, Any] | None:
    """
    Cleans a single raw record. Returns cleaned record, or None if invalid.
    """
    if not isinstance(item, dict):
        return None

    item_id = item.get("item_id")
    if not item_id or not str(item_id).strip():
        return None

    text = item.get("text")
    if not text or not isinstance(text, str) or not text.strip():
        return None

    cleaned = dict(item)
    cleaned["item_id"] = str(item_id).strip()
    cleaned["text"] = text.strip()
    cleaned["source"] = str(item.get("source", "unknown")).strip()
    return cleaned


def filter_and_deduplicate(items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Filters and deduplicates a list of raw items.
    Returns (cleaned_items, stats_dict).
    """
    seen_ids: Set[str] = set()
    cleaned_items: List[Dict[str, Any]] = []
    skipped_empty: int = 0
    skipped_duplicate: int = 0

    for item in items:
        cleaned = clean_item(item)
        if cleaned is None:
            skipped_empty += 1
            continue

        item_id = cleaned["item_id"]
        if item_id in seen_ids:
            skipped_duplicate += 1
            continue

        seen_ids.add(item_id)
        cleaned_items.append(cleaned)

    stats = {
        "input_total": len(items),
        "kept": len(cleaned_items),
        "skipped_empty": skipped_empty,
        "skipped_duplicate": skipped_duplicate,
    }
    return cleaned_items, stats


def load_raw_dataset(json_path: Path | str) -> List[Dict[str, Any]]:
    """Loads a JSON dataset from disk using UTF-8 encoding."""
    path = Path(json_path)
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
        if not isinstance(data, list):
            raise ValueError(f"Expected JSON list in {path}, got {type(data).__name__}")
        return data
