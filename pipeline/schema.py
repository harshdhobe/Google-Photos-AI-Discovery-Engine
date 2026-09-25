"""
Schema definition and validation for Discovery Engine Layer 2 tags.
Enforces the 7 structured fields defined in docs/architecture.md.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

# Allowed enum values matching docs/architecture.md
VALID_PHOTO_TYPES: Set[str] = {
    "travel",
    "event",
    "person",
    "screenshot",
    "document_receipt",
    "health_related",
    "other",
}

VALID_MEMORY_CUES_RETAINED: Set[str] = {
    "place",
    "rough_time_period",
    "people_present",
    "activity_event",
    "emotion_context",
    "visual_detail",
    "none_mentioned",
}

VALID_MEMORY_CUES_MISSING: Set[str] = {
    "exact_date",
    "location_name",
    "album",
    "search_terms",
    "device_or_year",
    "none_mentioned",
}

VALID_FAILURE_STAGES: Set[str] = {
    "could_not_formulate_query",
    "query_returned_nothing",
    "query_returned_too_much",
    "could_not_recognize_correct_result",
    "gave_up",
    "not_applicable",
}

VALID_WORKAROUNDS: Set[str] = {
    "manual_scrolling",
    "asked_another_person",
    "checked_other_app",
    "cross_referenced_calendar_location",
    "none",
    "gave_up_entirely",
}

REQUIRED_SCHEMA_KEYS: Set[str] = {
    "is_relevant",
    "photo_type",
    "memory_cues_retained",
    "memory_cues_missing",
    "failure_stage",
    "workaround",
    "representative_quote",
}


def normalize_tag(tag: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalizes tag dictionary: strips strings, ensures lists are lists,
    converts null-like strings to None, and ensures is_relevant is bool.
    """
    normalized = dict(tag)

    # is_relevant
    if "is_relevant" in normalized:
        val = normalized["is_relevant"]
        if isinstance(val, str):
            normalized["is_relevant"] = val.strip().lower() in ("true", "1", "yes")
        else:
            normalized["is_relevant"] = bool(val)

    # string fields
    for field in ["photo_type", "failure_stage", "workaround"]:
        val = normalized.get(field)
        if isinstance(val, str):
            val = val.strip().lower()
            normalized[field] = val if val not in ("null", "none", "") else None
        elif val is not None:
            normalized[field] = str(val).strip().lower()

    # representative_quote
    val = normalized.get("representative_quote")
    if isinstance(val, str):
        val = val.strip()
        normalized["representative_quote"] = val if val not in ("null", "none", "") else None

    # list fields
    for list_field in ["memory_cues_retained", "memory_cues_missing"]:
        val = normalized.get(list_field)
        if isinstance(val, str):
            # If model returned a single string or comma-separated string
            items = [s.strip().lower() for s in val.split(",") if s.strip()]
            normalized[list_field] = items
        elif isinstance(val, list):
            normalized[list_field] = [str(x).strip().lower() for x in val if x]
        else:
            normalized[list_field] = ["none_mentioned"]

    return normalized


def validate_tag(tag: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validates a tag dictionary against the Layer 2 schema.
    Returns (True, []) if valid, or (False, [error_messages]) if invalid.
    """
    errors: List[str] = []

    if not isinstance(tag, dict):
        return False, ["Tag output must be a dictionary/object."]

    # Check for missing keys
    missing_keys = REQUIRED_SCHEMA_KEYS - set(tag.keys())
    if missing_keys:
        errors.append(f"Missing required schema keys: {sorted(list(missing_keys))}")

    # 1. is_relevant
    is_rel = tag.get("is_relevant")
    if not isinstance(is_rel, bool):
        errors.append(f"'is_relevant' must be a boolean, got {type(is_rel).__name__}")

    # 2. photo_type
    pt = tag.get("photo_type")
    if pt is not None and pt not in VALID_PHOTO_TYPES:
        errors.append(f"Invalid photo_type '{pt}'. Allowed: {sorted(list(VALID_PHOTO_TYPES))} or null")

    # 3. memory_cues_retained
    mcr = tag.get("memory_cues_retained")
    if not isinstance(mcr, list):
        errors.append(f"'memory_cues_retained' must be a list, got {type(mcr).__name__}")
    else:
        invalid_cues = [c for c in mcr if c not in VALID_MEMORY_CUES_RETAINED]
        if invalid_cues:
            errors.append(f"Invalid memory_cues_retained: {invalid_cues}. Allowed: {sorted(list(VALID_MEMORY_CUES_RETAINED))}")

    # 4. memory_cues_missing
    mcm = tag.get("memory_cues_missing")
    if not isinstance(mcm, list):
        errors.append(f"'memory_cues_missing' must be a list, got {type(mcm).__name__}")
    else:
        invalid_missing = [c for c in mcm if c not in VALID_MEMORY_CUES_MISSING]
        if invalid_missing:
            errors.append(f"Invalid memory_cues_missing: {invalid_missing}. Allowed: {sorted(list(VALID_MEMORY_CUES_MISSING))}")

    # 5. failure_stage
    fs = tag.get("failure_stage")
    if fs is not None and fs not in VALID_FAILURE_STAGES:
        errors.append(f"Invalid failure_stage '{fs}'. Allowed: {sorted(list(VALID_FAILURE_STAGES))} or null")

    # 6. workaround
    wa = tag.get("workaround")
    if wa is not None and wa not in VALID_WORKAROUNDS:
        errors.append(f"Invalid workaround '{wa}'. Allowed: {sorted(list(VALID_WORKAROUNDS))} or null")

    # 7. representative_quote
    rq = tag.get("representative_quote")
    if rq is not None and not isinstance(rq, str):
        errors.append(f"'representative_quote' must be a string or null, got {type(rq).__name__}")

    return len(errors) == 0, errors
