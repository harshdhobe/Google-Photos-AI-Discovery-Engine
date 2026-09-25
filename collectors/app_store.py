"""Apple App Store collector for Google Photos reviews (Layer 1).

Uses Apple's official keyless iTunes Customer Reviews RSS feed
(no API key required).
Target app: Google Photos, App Store numeric ID 962194608.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from typing import Any
import xml.etree.ElementTree as ET

import requests

APP_NAME = "google-photos"
APP_ID = 962194608
PRIMARY_COUNTRY = "us"
SOURCE = "app_store"

# Storefronts to paginate reviews across when reaching higher counts
STOREFRONTS = [
    "us", "au", "gb", "ca", "nz", "ie", "in", "sg", "ph", "za",
    "de", "fr", "es", "it", "mx", "br", "nl", "se", "no", "dk",
]

logger = logging.getLogger(__name__)


def _to_iso_date(value: Any) -> str | None:
    """Convert various date representations to ISO 8601 string or None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(text, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            continue
    return text


def _fetch_itunes_rss_reviews(count: int = 250) -> list[dict[str, Any]]:
    """Fetch reviews via Apple's official keyless customer reviews RSS feed."""
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        )
    }

    for country in STOREFRONTS:
        for sort_by in ("mostRecent", "mostHelpful"):
            url_json = f"https://itunes.apple.com/{country}/rss/customerreviews/id={APP_ID}/sortBy={sort_by}/json"
            try:
                resp = requests.get(url_json, headers=headers, timeout=6)
                if resp.status_code == 200:
                    entries = resp.json().get("feed", {}).get("entry", [])
                    if isinstance(entries, list):
                        for entry in entries:
                            if "id" not in entry or "content" not in entry:
                                continue
                            item_id = str(entry["id"].get("label", "")).strip()
                            text = str(entry["content"].get("label", "")).strip()
                            if not text or not item_id or item_id in seen_ids:
                                continue
                            seen_ids.add(item_id)

                            rating = None
                            if "im:rating" in entry and "label" in entry["im:rating"]:
                                try:
                                    rating = int(entry["im:rating"]["label"])
                                except (ValueError, TypeError):
                                    rating = None

                            date_val = None
                            if "updated" in entry and "label" in entry["updated"]:
                                date_val = _to_iso_date(entry["updated"]["label"])

                            records.append({
                                "source": SOURCE,
                                "item_id": item_id,
                                "text": text,
                                "date": date_val,
                                "rating": rating,
                            })
                            if len(records) >= count:
                                return records
            except Exception as exc:
                logger.debug("iTunes JSON fetch failed for %s (%s): %s", country, sort_by, exc)

            for page in (2, 7):
                url_xml = f"https://itunes.apple.com/{country}/rss/customerreviews/page={page}/id={APP_ID}/sortBy={sort_by}/xml"
                try:
                    resp_xml = requests.get(url_xml, headers=headers, timeout=6)
                    if resp_xml.status_code == 200 and resp_xml.content:
                        root = ET.fromstring(resp_xml.content)
                        ns = {"atom": "http://www.w3.org/2005/Atom"}
                        for entry in root.findall("atom:entry", ns):
                            id_el = entry.find("atom:id", ns)
                            content_el = entry.find("atom:content", ns)
                            if id_el is None or content_el is None or not content_el.text:
                                continue
                            item_id = str(id_el.text).strip()
                            text = str(content_el.text).strip()
                            if not text or not item_id or item_id in seen_ids:
                                continue
                            seen_ids.add(item_id)

                            rating = None
                            rating_el = entry.find("{http://itunes.apple.com/rss}rating")
                            if rating_el is not None and rating_el.text:
                                try:
                                    rating = int(rating_el.text)
                                except (ValueError, TypeError):
                                    rating = None

                            updated_el = entry.find("atom:updated", ns)
                            date_val = _to_iso_date(updated_el.text) if updated_el is not None else None

                            records.append({
                                "source": SOURCE,
                                "item_id": item_id,
                                "text": text,
                                "date": date_val,
                                "rating": rating,
                            })
                            if len(records) >= count:
                                return records
                except Exception as exc:
                    logger.debug("iTunes XML fetch failed for %s page %d (%s): %s", country, page, sort_by, exc)

            if len(records) >= count:
                break
        if len(records) >= count:
            break

    return records


def collect_app_store_reviews(count: int = 250) -> list[dict[str, Any]]:
    """Pull Google Photos App Store reviews into Layer 1 records.

    Uses Apple's direct iTunes Customer Reviews RSS feed across storefronts.
    Catches all exceptions and logs/prints clear error details so failures
    are never silent and never crash the orchestrator.
    """
    try:
        records = _fetch_itunes_rss_reviews(count=count)
    except Exception as exc:
        msg = f"ERROR: App Store collection failed via iTunes RSS feed: {exc}"
        print(msg, file=sys.stderr)
        logger.error(msg)
        return []

    if not records:
        msg = "WARNING: App Store collection returned 0 items across all available endpoints."
        print(msg, file=sys.stderr)
        logger.warning(msg)

    return records
