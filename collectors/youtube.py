"""YouTube collector for Google Photos photo-retrieval comments (Layer 1).

Uses google-api-python-client (YouTube Data API v3).
Required env var (set in .env):
    YOUTUBE_API_KEY -- developer key from Google Cloud Console

If the key is missing the collector logs a warning and returns [] without
crashing the orchestrator.  Quota errors (HTTP 403 quotaExceeded) are caught
and return any items collected before the limit was hit.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from dotenv import find_dotenv, load_dotenv

_ROOT = Path(__file__).resolve().parent
for _candidate in [_ROOT / ".env", _ROOT.parent / ".env", _ROOT.parents[1] / ".env"]:
    if _candidate.exists():
        load_dotenv(_candidate)
load_dotenv(find_dotenv(usecwd=True))

SOURCE = "youtube_comment"

# Video search queries targeting vague-memory photo retrieval on Google Photos
VIDEO_SEARCH_QUERIES = [
    "Google Photos search tips find old photos",
    "find old photos Google Photos tutorial",
    "Google Photos search not working fix",
    "how to find a photo in Google Photos",
    "recover deleted photos Google Photos",
    "Google Photos search by date face recognition",
    "Google Photos backup problem find pictures",
]

# Max videos to retrieve per search query (to stay within quota)
VIDEOS_PER_QUERY = 8
# Max comment pages to fetch per video
MAX_COMMENT_PAGES = 5
COMMENTS_PER_PAGE = 50  # maxResults cap for commentThreads.list

logger = logging.getLogger(__name__)


def _parse_yt_datetime(value: str | None) -> str | None:
    """Parse YouTube's RFC 3339 datetime string into ISO 8601."""
    if not value:
        return None
    # YouTube returns e.g. "2024-03-15T12:34:56.000Z"
    try:
        dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
        return dt.replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        pass
    try:
        dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        return dt.replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return value  # Return as-is rather than None


def collect_youtube_comments(count: int = 100) -> list[dict[str, Any]]:
    """Pull YouTube comments from Google Photos help/tutorial videos.

    Returns [] with a warning if YOUTUBE_API_KEY is missing or
    google-api-python-client is not installed.
    Returns partial results on quota exhaustion or network errors.
    """
    # --- Credential check (fail soft) ---
    api_key = os.getenv("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        logger.warning(
            "WARNING: YouTube collector skipped -- YOUTUBE_API_KEY env var is not set. "
            "Set it in .env (see .env.example) and re-run to include YouTube data."
        )
        return []

    try:
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
    except ImportError:
        logger.warning(
            "google-api-python-client is not installed. "
            "Run `pip install google-api-python-client` or install requirements.txt."
        )
        return []

    try:
        youtube = build("youtube", "v3", developerKey=api_key)
    except Exception as exc:
        logger.warning("YouTube: failed to build API client: %s", exc)
        return []

    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    def _add_comment(snippet: dict[str, Any]) -> None:
        """Extract a top-level comment snippet into a Layer 1 record."""
        top = snippet.get("topLevelComment", {}).get("snippet", {})
        text = (top.get("textDisplay") or top.get("textOriginal") or "").strip()
        if not text:
            return
        comment_id = snippet.get("topLevelComment", {}).get("id", "")
        if not comment_id or comment_id in seen_ids:
            return
        seen_ids.add(comment_id)
        records.append(
            {
                "source": SOURCE,
                "item_id": comment_id,
                "text": text,
                "date": _parse_yt_datetime(top.get("publishedAt")),
                "rating": None,
            }
        )

    try:
        for query in VIDEO_SEARCH_QUERIES:
            if len(records) >= count:
                break

            # --- Search for relevant videos ---
            try:
                search_resp = (
                    youtube.search()
                    .list(
                        part="id",
                        q=query,
                        type="video",
                        relevanceLanguage="en",
                        maxResults=VIDEOS_PER_QUERY,
                    )
                    .execute()
                )
            except HttpError as exc:
                reason = _http_error_reason(exc)
                if reason == "quotaExceeded":
                    logger.warning(
                        "YouTube: quota exhausted during video search -- "
                        "returning %d items collected so far.",
                        len(records),
                    )
                    return records
                logger.warning("YouTube: search error for %r: %s", query, exc)
                continue
            except Exception as exc:
                logger.warning("YouTube: unexpected search error for %r: %s", query, exc)
                continue

            video_ids = [
                item["id"]["videoId"]
                for item in search_resp.get("items", [])
                if item.get("id", {}).get("videoId")
            ]

            # --- Fetch comments for each video ---
            for video_id in video_ids:
                if len(records) >= count:
                    break

                page_token: str | None = None
                for _page in range(MAX_COMMENT_PAGES):
                    if len(records) >= count:
                        break
                    try:
                        kwargs: dict[str, Any] = {
                            "part": "snippet",
                            "videoId": video_id,
                            "maxResults": COMMENTS_PER_PAGE,
                            "order": "relevance",
                            "textFormat": "plainText",
                        }
                        if page_token:
                            kwargs["pageToken"] = page_token

                        ct_resp = youtube.commentThreads().list(**kwargs).execute()
                    except HttpError as exc:
                        reason = _http_error_reason(exc)
                        if reason == "quotaExceeded":
                            logger.warning(
                                "YouTube: quota exhausted fetching comments for video %s "
                                "-- returning %d items collected so far.",
                                video_id,
                                len(records),
                            )
                            return records
                        if reason == "commentsDisabled":
                            logger.warning(
                                "YouTube: comments disabled for video %s, skipping.",
                                video_id,
                            )
                            break
                        logger.warning(
                            "YouTube: commentThreads error for video %s: %s",
                            video_id,
                            exc,
                        )
                        break
                    except Exception as exc:
                        logger.warning(
                            "YouTube: unexpected error fetching comments for %s: %s",
                            video_id,
                            exc,
                        )
                        break

                    for item in ct_resp.get("items", []):
                        if len(records) >= count:
                            break
                        _add_comment(item.get("snippet", {}))

                    page_token = ct_resp.get("nextPageToken")
                    if not page_token:
                        break

    except Exception as exc:
        logger.warning(
            "YouTube collection encountered an unhandled error: %s -- returning %d items.",
            exc,
            len(records),
        )

    return records


def _http_error_reason(exc: Any) -> str:
    """Extract the first error reason string from a googleapiclient HttpError."""
    try:
        import json as _json

        content = exc.content
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")
        data = _json.loads(content)
        errors = data.get("error", {}).get("errors", [])
        if errors:
            return errors[0].get("reason", "")
    except Exception:
        pass
    return ""
