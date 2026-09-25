"""Layer 1 orchestrator: run all collectors and save a timestamped JSON dump.

Sources (Phase 1 + 1b + 1c):
  - Google Play Store          (no credentials required)
  - Google Photos Community    (no credentials required)
  - Apple App Store            (no credentials required)
  - Reddit                     (public unauthenticated JSON, no credentials required)
  - YouTube                    (requires YOUTUBE_API_KEY in .env)
  - Quora                      (requests + BeautifulSoup, no credentials required)

The YouTube collector returns [] and logs a warning if its API key is not set
-- the collection pipeline never crashes due to missing credentials.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

ROOT = Path(__file__).resolve().parent

# Load .env from discovery-engine or workspace root if present
for env_candidate in [ROOT / ".env", ROOT.parent / ".env"]:
    if env_candidate.exists():
        load_dotenv(env_candidate)
load_dotenv(find_dotenv(usecwd=True))

from collectors.app_store import collect_app_store_reviews
from collectors.google_photos_community import collect_community_posts
from collectors.play_store import collect_play_store_reviews
from collectors.quora import collect_quora_posts
from collectors.reddit import collect_reddit_posts
from collectors.youtube import collect_youtube_comments

RAW_DIR = ROOT / "data" / "raw"

# Sources tracked in the summary
ALL_SOURCES = [
    "play_store",
    "google_photos_community",
    "youtube_comment",
    "reddit_post",
    "reddit_comment",
    "app_store",
    "quora_question",
    "quora_answer",
]

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s: %(message)s",
)


def run_collection(
    play_store_count: int = 250,
    community_count: int = 500,
    reddit_post_count: int = 250,
    reddit_comment_count: int = 250,
    youtube_count: int = 250,
    app_store_count: int = 250,
    quora_count: int = 250,
) -> Path:
    print("Starting collection with targets:")
    print(f"  Play Store:               {play_store_count}")
    print(f"  Google Photos Community:  {community_count}")
    print(f"  Reddit Posts:             {reddit_post_count}")
    print(f"  Reddit Comments:          {reddit_comment_count}")
    print(f"  YouTube Comments:         {youtube_count}")
    print(f"  App Store:                {app_store_count}")
    print(f"  Quora:                    {quora_count}")

    try:
        play_store_items = collect_play_store_reviews(count=play_store_count) if play_store_count > 0 else []
    except Exception as exc:
        print(f"Error collecting Play Store reviews: {exc}")
        play_store_items = []

    try:
        community_items = collect_community_posts(count=community_count) if community_count > 0 else []
    except Exception as exc:
        print(f"Error collecting Community posts: {exc}")
        community_items = []

    try:
        reddit_items = (
            collect_reddit_posts(post_count=reddit_post_count, comment_count=reddit_comment_count)
            if (reddit_post_count > 0 or reddit_comment_count > 0)
            else []
        )
    except Exception as exc:
        print(f"Error collecting Reddit posts/comments: {exc}")
        reddit_items = []

    try:
        youtube_items = collect_youtube_comments(count=youtube_count) if youtube_count > 0 else []
    except Exception as exc:
        print(f"Error collecting YouTube comments: {exc}")
        youtube_items = []

    try:
        app_store_items = collect_app_store_reviews(count=app_store_count) if app_store_count > 0 else []
    except Exception as exc:
        print(f"Error collecting App Store reviews: {exc}")
        app_store_items = []

    try:
        quora_items = collect_quora_posts(count=quora_count) if quora_count > 0 else []
    except Exception as exc:
        print(f"Error collecting Quora posts: {exc}")
        quora_items = []

    items = (
        play_store_items
        + community_items
        + app_store_items
        + reddit_items
        + youtube_items
        + quora_items
    )

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = RAW_DIR / f"collected_{stamp}.json"
    output_path.write_text(
        json.dumps(items, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    counts = Counter(item.get("source", "unknown") for item in items)

    print(f"\nSaved {len(items)} items to {output_path}")
    print("Breakdown by source:")
    for source in ALL_SOURCES:
        n = counts.get(source, 0)
        skipped = " (skipped -- credentials not set)" if n == 0 and source == "youtube_comment" else ""
        print(f"  {source}: {n}{skipped}")

    # Also print any unexpected or extra sources not in the primary list
    for source, n in sorted(counts.items()):
        if source not in ALL_SOURCES:
            print(f"  {source}: {n}")

    return output_path


if __name__ == "__main__":
    run_collection()
