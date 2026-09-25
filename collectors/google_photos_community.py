"""Google Photos Help Community collector (Layer 1).

Scrapes public thread listing and thread pages with requests + BeautifulSoup.
Google may change forum HTML or embedded JSON; selectors in this module may
need updating if collection starts returning empty results.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

SOURCE = "google_photos_community"
BASE = "https://support.google.com"
THREADS_URL = f"{BASE}/photos/threads"
THREAD_URL_TEMPLATE = f"{BASE}/photos/thread/{{thread_id}}?hl=en"

# Queries aimed at vague-memory photo retrieval rather than the default
# "deleted photos" browse feed.
SEARCH_QUERIES = [
    "can't find photos",
    "search not working",
    "find old photos",
    "search by date",
    "can't search photos",
    "search photos not found",
    "find a photo I remember",
]

THREAD_ID_RE = re.compile(r"/photos/thread/(\d+)")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 20
SLEEP_SECONDS = 0.8

POST_SELECTORS = [
    "[data-thread-message]",
    ".thread-message",
    ".forum-thread-message",
    "article",
    "[itemprop='comment']",
    ".posted-by",
]


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    return session


def _get(session: requests.Session, url: str) -> str | None:
    try:
        response = session.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.text
    except requests.RequestException as exc:
        print(f"Request failed for {url}: {exc}")
        return None


def _search_listing_url(query: str) -> str:
    encoded = quote(query, safe="")
    return f"{THREADS_URL}?hl=en&thread_filter=(query:{encoded})"


def _discover_thread_ids(session: requests.Session) -> list[str]:
    seen: list[str] = []
    found: set[str] = set()

    listing_urls = [f"{THREADS_URL}?hl=en"]
    listing_urls.extend(_search_listing_url(q) for q in SEARCH_QUERIES)

    for url in listing_urls:
        html = _get(session, url)
        time.sleep(SLEEP_SECONDS)
        if not html:
            continue
        for thread_id in THREAD_ID_RE.findall(html):
            if thread_id not in found:
                found.add(thread_id)
                seen.append(thread_id)
    return seen


def _iso_from_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (int, float)):
        # Heuristic: ms vs seconds timestamps
        ts = float(value)
        if ts > 1e12:
            ts /= 1000.0
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        except (OSError, OverflowError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text.replace("Z", "+0000"), fmt).isoformat()
        except ValueError:
            continue
    return text


def _clean_text(*parts: str | None) -> str:
    chunks = [re.sub(r"\s+", " ", (p or "").strip()) for p in parts]
    return " ".join(c for c in chunks if c).strip()


def _walk_json(node: Any, posts: list[dict[str, Any]]) -> None:
    """Best-effort walk of embedded JSON looking for post-like objects."""
    if isinstance(node, dict):
        text_candidates = [
            node.get("text"),
            node.get("body"),
            node.get("content"),
            node.get("message"),
            node.get("snippet"),
        ]
        title = node.get("title") or node.get("subject")
        body = next((t for t in text_candidates if isinstance(t, str) and t.strip()), None)
        combined = _clean_text(title if isinstance(title, str) else None, body)
        msgid = node.get("id") or node.get("messageId") or node.get("msgid")
        date = (
            node.get("createTime")
            or node.get("created")
            or node.get("timestamp")
            or node.get("date")
        )
        if combined and len(combined) >= 20:
            posts.append(
                {
                    "msgid": str(msgid) if msgid is not None else None,
                    "text": combined,
                    "date": _iso_from_value(date),
                }
            )
        for value in node.values():
            _walk_json(value, posts)
    elif isinstance(node, list):
        for item in node:
            _walk_json(item, posts)


def _extract_json_posts(html: str) -> list[dict[str, Any]]:
    posts: list[dict[str, Any]] = []
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script"):
        raw = script.string or script.get_text() or ""
        if not raw.strip():
            continue
        # JSON-LD
        if script.get("type") == "application/ld+json":
            try:
                _walk_json(json.loads(raw), posts)
            except json.JSONDecodeError:
                pass
            continue
        # AF_initDataCallback / assignment blobs often contain nested JSON
        for match in re.finditer(r"(\{[^{}]{20,}\}|(\[[^\[\]]{20,}\]))", raw):
            snippet = match.group(0)
            if "thread" not in snippet.lower() and "message" not in snippet.lower():
                continue
            try:
                _walk_json(json.loads(snippet), posts)
            except json.JSONDecodeError:
                continue
    return posts


def _extract_html_posts(html: str, thread_id: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.replace("- Google Photos Community", "").strip()

    posts: list[dict[str, Any]] = []
    seen_text: set[str] = set()

    for selector in POST_SELECTORS:
        for node in soup.select(selector):
            text = _clean_text(node.get_text(" ", strip=True))
            if not text or len(text) < 20 or text in seen_text:
                continue
            seen_text.add(text)
            msgid = node.get("data-message-id") or node.get("id")
            time_el = node.find("time")
            date = None
            if time_el is not None:
                date = _iso_from_value(time_el.get("datetime") or time_el.get_text(strip=True))
            posts.append({"msgid": msgid, "text": text, "date": date})

    if not posts:
        main = soup.find("main") or soup.body
        if main:
            body = _clean_text(main.get_text(" ", strip=True))
            # Drop obvious chrome if the fallback blob is huge
            if body:
                combined = _clean_text(title, body[:4000])
                if len(combined) >= 20:
                    posts.append({"msgid": None, "text": combined, "date": None})

    if title and posts:
        first = posts[0]
        if title.lower() not in first["text"].lower():
            first["text"] = _clean_text(title, first["text"])

    # Keep thread_id available for item_id construction
    for post in posts:
        post["thread_id"] = thread_id
    return posts


def _posts_from_thread(html: str, thread_id: str) -> list[dict[str, Any]]:
    html_posts = _extract_html_posts(html, thread_id)
    json_posts = _extract_json_posts(html)

    # Prefer HTML posts when they look like real messages; otherwise JSON walk.
    if html_posts and not (
        len(html_posts) == 1 and "Skip to main content" in html_posts[0]["text"]
    ):
        return html_posts
    if json_posts:
        for post in json_posts:
            post["thread_id"] = thread_id
        return json_posts
    return html_posts


def _to_record(post: dict[str, Any], index: int) -> dict[str, Any] | None:
    text = (post.get("text") or "").strip()
    if not text:
        return None
    thread_id = post.get("thread_id") or "unknown"
    msgid = post.get("msgid")
    item_id = f"{thread_id}:{msgid}" if msgid else f"{thread_id}:{index}"
    return {
        "source": SOURCE,
        "item_id": str(item_id),
        "text": text,
        "date": post.get("date"),
        "rating": None,
    }


def _extract_listing_records(session: requests.Session, target_count: int) -> list[dict[str, Any]]:
    """Extract threads directly from the support listing page using max_results."""
    max_results = min(max(target_count + 50, 100), 700)
    url = f"{THREADS_URL}?hl=en&max_results={max_results}"
    html = _get(session, url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    thread_links = soup.find_all("a", class_="thread-list-thread")
    if not thread_links:
        # Fallback: any link matching /photos/thread/
        thread_links = soup.find_all("a", href=lambda h: h and "/photos/thread/" in h)

    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for a in thread_links:
        item_id = a.get("data-stats-id")
        if not item_id:
            match = THREAD_ID_RE.search(a.get("href", ""))
            item_id = match.group(1) if match else None
        if not item_id or str(item_id) in seen_ids:
            continue

        top = a.find(class_="thread-list-thread__top-row")
        snip = a.find(class_="thread-list-thread__snippet")
        title = top.get_text(" ", strip=True) if top else ""
        body = snip.get_text(" ", strip=True) if snip else ""
        text = f"{title}\n{body}".strip() if body else title
        if not text or len(text) < 15:
            # Try getting all text from link if specific classes not found
            text = a.get_text(" ", strip=True)
            if len(text) < 15:
                continue

        seen_ids.add(str(item_id))
        records.append({
            "source": SOURCE,
            "item_id": f"{item_id}:0",
            "text": text,
            "date": None,
            "rating": None,
        })
        if len(records) >= target_count:
            break

    return records


def collect_community_posts(count: int = 100) -> list[dict[str, Any]]:
    """Pull Help Community thread posts/replies into Layer 1 records.

    Uses Google's server-rendered max_results parameter to collect up to 100+ threads
    directly, falling back to individual thread fetching if needed.
    """
    session = _session()
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    # 1. Fast, high-yield listing extraction with max_results
    try:
        listing_records = _extract_listing_records(session, target_count=count)
        for r in listing_records:
            if r["item_id"] not in seen_ids:
                seen_ids.add(r["item_id"])
                records.append(r)
    except Exception as exc:
        print(f"Community listing extraction failed: {exc}")

    # 2. If we already reached count, return immediately
    if len(records) >= count:
        return records[:count]

    # 3. Fallback / top-up: discover and scrape individual thread pages
    try:
        thread_ids = _discover_thread_ids(session)
    except Exception as exc:
        print(f"Community thread discovery failed: {exc}")
        return records

    for thread_id in thread_ids:
        if len(records) >= count:
            break
        url = THREAD_URL_TEMPLATE.format(thread_id=thread_id)
        html = _get(session, url)
        time.sleep(SLEEP_SECONDS)
        if not html:
            continue
        try:
            posts = _posts_from_thread(html, thread_id)
        except Exception as exc:
            print(f"Failed to parse thread {thread_id}: {exc}")
            continue
        if not posts:
            continue
        for index, post in enumerate(posts):
            if len(records) >= count:
                break
            record = _to_record(post, index)
            if not record or record["item_id"] in seen_ids:
                continue
            seen_ids.add(record["item_id"])
            records.append(record)

    return records[:count]

