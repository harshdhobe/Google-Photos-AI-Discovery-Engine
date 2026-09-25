"""Reddit collector for Google Photos photo-retrieval discussions (Layer 1).

Uses Reddit's public unauthenticated JSON endpoints (no OAuth or API keys needed).
Endpoints:
    - Subreddit search: https://www.reddit.com/r/{subreddit}/search.json
    - Global search:    https://www.reddit.com/r/all/search.json
    - Post comments:    https://www.reddit.com{permalink}.json

Uses a custom User-Agent header, polite delays between requests (1.5-2s),
and backs off + retries once if rate-limited (HTTP 429).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import requests

SOURCE_POST = "reddit_post"
SOURCE_COMMENT = "reddit_comment"

# Custom User-Agent: Reddit blocks requests with default / missing headers
USER_AGENT = (
    "discovery-engine-research/0.1 (public research on photo retrieval; "
    "contact: u/discoveryengine_bot)"
)

# Target subreddits + global fallback
SUBREDDITS = ["googlephotos", "androidapps", "google", "techsupport", "all"]

# Search queries targeting vague-memory photo retrieval
SEARCH_QUERIES = [
    "find old photo google photos",
    "google photos search not working",
    "can't find photo google photos",
    "lost photos google photos",
    "google photos missing photos",
    "google photos search by date",
    "google photos recognize face search",
    "google photos search people",
    "google photos archive search",
    "google photos search album",
    "google photos library search",
    "find pictures google photos",
]

REQUEST_TIMEOUT = 15
POLITE_DELAY = 1.0        # seconds between normal requests
RATE_LIMIT_BACKOFF = 4.0  # seconds to sleep before retrying on HTTP 429

logger = logging.getLogger(__name__)


def _to_iso(timestamp: float | int | None) -> str | None:
    """Convert a Unix UTC timestamp to an ISO 8601 string."""
    if timestamp is None:
        return None
    try:
        return datetime.fromtimestamp(float(timestamp), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _fetch_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any] | list[Any] | None:
    """Fetch JSON from Reddit with polite delay, custom headers, and 429 backoff retry."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    time.sleep(POLITE_DELAY)

    for attempt in range(2):
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                if attempt == 0:
                    logger.warning("Reddit returned 429 (rate limit). Backing off for %.1fs...", RATE_LIMIT_BACKOFF)
                    time.sleep(RATE_LIMIT_BACKOFF)
                    continue
                else:
                    logger.warning("Reddit 429 rate limit persisted after retry for %s. Skipping.", url)
                    return None
            logger.warning("Reddit request to %s failed with HTTP %s", url, resp.status_code)
            return None
        except requests.RequestException as exc:
            logger.warning("Reddit network error requesting %s: %s", url, exc)
            return None
        except Exception as exc:
            logger.warning("Reddit failed to parse JSON from %s: %s", url, exc)
            return None

    return None


def _fetch_from_arctic_shift(
    endpoint: str,
    subreddit: str,
    limit: int = 100,
    before: int | None = None,
) -> list[dict[str, Any]]:
    """Query Arctic Shift Reddit archive API with retry on transient failure."""
    url = f"https://arctic-shift.photon-reddit.com/api/{endpoint}/search?subreddit={subreddit}&limit={limit}"
    if before:
        url += f"&before={before}"
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    for attempt in range(2):
        try:
            resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                return resp.json().get("data", [])
            elif resp.status_code == 429:
                time.sleep(2.0)
                continue
        except Exception as exc:
            if attempt == 0:
                time.sleep(1.0)
                continue
            logger.warning("Arctic Shift request for %s (r/%s) failed: %s", endpoint, subreddit, exc)
    return []


def _fetch_from_pullpush(
    endpoint: str,
    query: str,
    subreddit: str,
    size: int = 25,
) -> list[dict[str, Any]]:
    """Query the open public Reddit archive API (PullPush) when reddit.com blocks."""
    url = f"https://api.pullpush.io/reddit/search/{endpoint}/"
    params: dict[str, Any] = {"q": query, "size": size}
    if subreddit != "all":
        params["subreddit"] = subreddit

    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            return resp.json().get("data", [])
    except Exception as exc:
        logger.warning("PullPush request for %s (%s) failed: %s", endpoint, query, exc)
    return []


def collect_reddit_posts(
    post_count: int = 250,
    comment_count: int = 250,
) -> list[dict[str, Any]]:
    """Pull Reddit posts and comments using public archive APIs.

    Collects up to `post_count` posts and up to `comment_count` comments.
    """
    posts: list[dict[str, Any]] = []
    comments: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    def _add_post(record: dict[str, Any]) -> bool:
        iid = record["item_id"]
        if iid not in seen_ids:
            seen_ids.add(iid)
            posts.append(record)
        return len(posts) >= post_count

    def _add_comment(record: dict[str, Any]) -> bool:
        iid = record["item_id"]
        if iid not in seen_ids:
            seen_ids.add(iid)
            comments.append(record)
        return len(comments) >= comment_count

    try:
        # Primary: Arctic Shift archive with timestamp pagination
        for sub in ["googlephotos", "androidapps", "google"]:
            if len(posts) >= post_count:
                break
            before = None
            max_pages = 10
            for _ in range(max_pages):
                if len(posts) >= post_count:
                    break
                batch = _fetch_from_arctic_shift("posts", sub, limit=100, before=before)
                if not batch:
                    break
                for post in batch:
                    pid = post.get("id")
                    if not pid:
                        continue
                    title = (post.get("title") or "").strip()
                    selftext = (post.get("selftext") or "").strip()
                    text = f"{title}\n{selftext}".strip() if selftext else title
                    if not text:
                        continue
                    if _add_post({
                        "source": SOURCE_POST,
                        "item_id": str(pid),
                        "text": text,
                        "date": _to_iso(post.get("created_utc")),
                        "rating": None,
                    }):
                        break
                oldest_ts = batch[-1].get("created_utc")
                if not oldest_ts or oldest_ts == before:
                    break
                before = oldest_ts
                time.sleep(0.5)

        for sub in ["googlephotos", "androidapps", "google"]:
            if len(comments) >= comment_count:
                break
            before_c = None
            max_pages = 10
            for _ in range(max_pages):
                if len(comments) >= comment_count:
                    break
                batch = _fetch_from_arctic_shift("comments", sub, limit=100, before=before_c)
                if not batch:
                    break
                for c in batch:
                    cid = c.get("id")
                    body = (c.get("body") or "").strip()
                    if not cid or not body or body in ("[deleted]", "[removed]"):
                        continue
                    if _add_comment({
                        "source": SOURCE_COMMENT,
                        "item_id": str(cid),
                        "text": body,
                        "date": _to_iso(c.get("created_utc")),
                        "rating": None,
                    }):
                        break
                oldest_ts = batch[-1].get("created_utc")
                if not oldest_ts or oldest_ts == before_c:
                    break
                before_c = oldest_ts
                time.sleep(0.5)

        # Secondary fallback: PullPush archive if targets not yet met
        if len(posts) < post_count or len(comments) < comment_count:
            for query in SEARCH_QUERIES:
                if len(posts) >= post_count and len(comments) >= comment_count:
                    break

                for sub in SUBREDDITS:
                    if len(posts) >= post_count and len(comments) >= comment_count:
                        break

                    if len(posts) < post_count:
                        submissions = _fetch_from_pullpush("submission", query, sub, size=25)
                        for post in submissions:
                            pid = post.get("id")
                            if not pid:
                                continue
                            title = (post.get("title") or "").strip()
                            selftext = (post.get("selftext") or "").strip()
                            text = f"{title}\n{selftext}".strip() if selftext else title
                            if not text:
                                continue
                            if _add_post({
                                "source": SOURCE_POST,
                                "item_id": str(pid),
                                "text": text,
                                "date": _to_iso(post.get("created_utc")),
                                "rating": None,
                            }):
                                break

                    if len(comments) < comment_count:
                        raw_comments = _fetch_from_pullpush("comment", query, sub, size=25)
                        for c in raw_comments:
                            cid = c.get("id")
                            body = (c.get("body") or "").strip()
                            if not cid or not body or body in ("[deleted]", "[removed]"):
                                continue
                            if _add_comment({
                                "source": SOURCE_COMMENT,
                                "item_id": str(cid),
                                "text": body,
                                "date": _to_iso(c.get("created_utc")),
                                "rating": None,
                            }):
                                break

    except Exception as exc:
        logger.warning("Reddit collection encountered an error: %s -- returning collected items.", exc)

    return posts[:post_count] + comments[:comment_count]



