"""Quora collector for photo retrieval questions and answers (Layer 1).

Uses requests + BeautifulSoup to harvest questions and top answers matching
vague-memory photo search queries on Quora.

NOTE: Quora employs aggressive anti-scraping measures (Cloudflare challenges,
CAPTCHAs, and IP rate limits). This collector sets a browser-like User-Agent,
uses polite request intervals (1.5–2.0s), and detects block pages gracefully.
HTML structure and anti-scraping challenges may require adjusting selectors or
backing off if blocking becomes frequent — this collector may yield fewer items
or 0 items if Quora blocks the automated session.
"""

from __future__ import annotations

import hashlib
import logging
import re
import sys
import time
from typing import Any
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

TARGET_QUERIES = [
    "how to find old photos on google photos",
    "find a photo I don't remember when I took",
    "search google photos by memory",
    "can't find old photo phone gallery",
    "how to search google photos by description",
]

SEED_QUESTION_SLUGS = [
    "How-can-I-find-old-photos-on-Google-Photos",
    "How-do-I-find-a-photo-on-Google-Photos-if-I-dont-know-the-date",
    "How-do-I-search-for-a-photo-in-Google-Photos-by-description",
    "Why-cant-I-find-a-photo-in-Google-Photos-when-I-search-for-it",
    "How-can-I-find-a-photo-I-took-years-ago-when-I-dont-remember-the-date",
]

BLOCK_INDICATORS = [
    "captcha",
    "cf-browser-verification",
    "challenge-running",
    "just a moment...",
    "attention required! | cloudflare",
    "waf-block",
]


def _is_block_page(html_text: str, status_code: int) -> bool:
    """Return True if the response is a CAPTCHA, Cloudflare block, or access denied page."""
    if status_code in (403, 429, 503):
        return True
    lower = html_text.lower()
    return any(indicator in lower for indicator in BLOCK_INDICATORS)


def _make_item_id(prefix: str, text_or_slug: str) -> str:
    """Derive a stable unique identifier for a question or answer."""
    slug = re.sub(r"[^a-zA-Z0-9_\-]+", "-", text_or_slug).strip("-")[:60]
    digest = hashlib.sha256(text_or_slug.encode("utf-8", errors="replace")).hexdigest()[:10]
    return f"quora_{prefix}_{slug}_{digest}" if slug else f"quora_{prefix}_{digest}"


def _extract_from_question_html(
    url: str,
    html: str,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Parse a Quora question page to extract the question record and its answers."""
    soup = BeautifulSoup(html, "html.parser")

    title_text = ""
    title_el = (
        soup.find("h1")
        or soup.find("title")
        or soup.find(class_=re.compile(r"question_title|title", re.I))
    )
    if title_el:
        title_text = title_el.get_text(separator=" ", strip=True)
        title_text = re.sub(r"\s*-\s*Quora$", "", title_text, flags=re.I).strip()

    if not title_text or len(title_text) < 10:
        return None, []

    detail_text = ""
    detail_el = soup.find("div", class_=re.compile(r"question_detail|context|detail", re.I))
    if detail_el:
        detail_text = detail_el.get_text(separator=" ", strip=True)

    full_q_text = f"{title_text}\n\n{detail_text}".strip() if detail_text else title_text

    slug = url.split("quora.com/")[-1].split("?")[0].strip("/")
    question_record = {
        "source": "quora_question",
        "item_id": _make_item_id("q", slug or title_text),
        "text": full_q_text,
        "date": None,
        "rating": None,
    }

    answers: list[dict[str, Any]] = []
    answer_blocks = soup.find_all(
        ["div", "section"],
        class_=re.compile(r"ans_text|answer_content|content_text|spacing_log_answer_content", re.I),
    )

    if not answer_blocks:
        answer_containers = soup.find_all("div", class_=re.compile(r"AnswerBase|Answer", re.I))
        for container in answer_containers:
            paragraphs = container.find_all("p")
            if paragraphs:
                body = " ".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
                if len(body) >= 50:
                    ans_id = _make_item_id("a", f"{slug}_{len(answers)}_{body[:40]}")
                    answers.append({
                        "source": "quora_answer",
                        "item_id": ans_id,
                        "text": body,
                        "date": None,
                        "rating": None,
                    })
    else:
        for idx, block in enumerate(answer_blocks):
            body = block.get_text(separator=" ", strip=True)
            if len(body) >= 50:
                ans_id = _make_item_id("a", f"{slug}_{idx}_{body[:40]}")
                answers.append({
                    "source": "quora_answer",
                    "item_id": ans_id,
                    "text": body,
                    "date": None,
                    "rating": None,
                })

    return question_record, answers


def collect_quora_posts(count: int = 250) -> list[dict[str, Any]]:
    """Harvest Quora questions and answers related to vague-memory photo retrieval.

    Collects question titles/details (quora_question) and top answers (quora_answer).
    Employs polite pacing (1.5-2.0s) and catches block/CAPTCHA pages without crashing.
    Returns whatever live items were collected.
    """
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    session = requests.Session()
    session.headers.update(HEADERS)

    # 1. Try live scrape of target seed questions
    for slug in SEED_QUESTION_SLUGS:
        url = f"https://www.quora.com/{slug}"
        try:
            resp = session.get(url, timeout=6)
            if _is_block_page(resp.text, resp.status_code):
                logger.warning("Quora returned CAPTCHA/block page for %s (status %d). Skipping.", url, resp.status_code)
                time.sleep(1.5)
                continue

            q_record, ans_records = _extract_from_question_html(url, resp.text)
            if q_record and q_record["item_id"] not in seen_ids:
                seen_ids.add(q_record["item_id"])
                records.append(q_record)

            for ans in ans_records:
                if ans["item_id"] not in seen_ids:
                    seen_ids.add(ans["item_id"])
                    records.append(ans)
                    if len(records) >= count:
                        return records

        except Exception as exc:
            logger.warning("Error scraping Quora question %s: %s", url, exc)

        time.sleep(1.5)
        if len(records) >= count:
            return records

    return records
