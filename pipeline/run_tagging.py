"""
Discovery Engine — Phase 2 AI Tagging Orchestrator.
Processes raw collected feedback items through Cerebras LLaMA-3.3-70B,
validates schema, and stores tagged rows in SQLite with resumable progress.
"""

from __future__ import annotations

import argparse
import glob
import logging
import os
import sys
import time
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

# Ensure discovery-engine root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from db.database import (
    DEFAULT_DB_PATH,
    get_tag_stats,
    get_tagged_item_ids,
    init_db,
    save_tagged_item,
)
from pipeline.prefilter import filter_and_deduplicate, load_raw_dataset
from pipeline.schema import validate_tag
from pipeline.tagger import CerebrasTagger, mock_tag_item

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_tagging")


def find_latest_raw_file(data_raw_dir: Path) -> Optional[Path]:
    """Finds the most recently created collected_*.json file in data/raw/."""
    pattern = str(data_raw_dir / "collected_*.json")
    files = sorted(glob.glob(pattern))
    return Path(files[-1]) if files else None


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Discovery Engine Layer 2 Tagging Orchestrator")
    parser.add_argument(
        "--input",
        "-i",
        type=str,
        default=None,
        help="Path to raw JSON dataset (defaults to latest in data/raw/)",
    )
    parser.add_argument(
        "--limit",
        "-n",
        type=int,
        default=None,
        help="Limit number of items to tag in this run (useful for testing)",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=str(DEFAULT_DB_PATH),
        help=f"Path to SQLite database file (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use deterministic heuristic mock tagger. ONLY use with --limit for testing. Never use on a production DB.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.1,
        help="Interval in seconds between Groq API calls (default: 2.1s for 30 RPM limit)",
    )

    args = parser.parse_args()

    # Safety: refuse to run --mock without an explicit --limit to prevent
    # accidentally overwriting the real DB with heuristic fake tags.
    if args.mock and (not args.limit or args.limit <= 0):
        logger.error("=" * 70)
        logger.error("REFUSED: --mock requires an explicit --limit N (e.g. --limit 10)")
        logger.error("Running --mock without a limit would overwrite the real DB with fake tags.")
        logger.error("Use --mock --limit 10 for testing only.")
        logger.error("=" * 70)
        sys.exit(1)

    db_path = Path(args.db)
    init_db(db_path)

    # 1. Locate raw input file
    raw_file: Optional[Path] = Path(args.input) if args.input else None
    if not raw_file:
        raw_dir = BASE_DIR / "data" / "raw"
        raw_file = find_latest_raw_file(raw_dir)
        if not raw_file:
            logger.error("No raw collection files found in %s. Run run_collection.py first.", raw_dir)
            sys.exit(1)

    logger.info("Using raw dataset: %s", raw_file)

    # 2. Load and prefilter raw items
    raw_items = load_raw_dataset(raw_file)
    clean_items, filter_stats = filter_and_deduplicate(raw_items)
    logger.info(
        "Prefilter stats: %d loaded -> %d valid items (skipped %d empty, %d duplicates)",
        filter_stats["input_total"],
        filter_stats["kept"],
        filter_stats["skipped_empty"],
        filter_stats["skipped_duplicate"],
    )

    # 3. Check resume state
    tagged_ids = get_tagged_item_ids(db_path)
    logger.info("Found %d items already tagged in SQLite (%s)", len(tagged_ids), db_path)

    unprocessed = [item for item in clean_items if item["item_id"] not in tagged_ids]
    logger.info("Items remaining to tag: %d", len(unprocessed))

    if not unprocessed:
        logger.info("All %d items have already been tagged. Nothing to do!", len(clean_items))
        _print_summary(db_path)
        return

    # Apply limit if specified
    if args.limit and args.limit > 0:
        unprocessed = unprocessed[: args.limit]
        logger.info("Limit specified: processing %d items in this session", len(unprocessed))

    # 4. Check API credentials or mock mode
    cerebras_key = os.getenv("GROQ_API_KEY")
    use_mock = args.mock

    if not use_mock and not cerebras_key:
        logger.warning("=" * 70)
        logger.warning("WARNING: GROQ_API_KEY not found in environment or .env!")
        logger.warning("Get a free key at https://console.groq.com then add GROQ_API_KEY to discovery-engine/.env")
        logger.warning("Falling back to --mock mode for this run.")
        logger.warning("=" * 70)
        use_mock = True

    tagger = None
    if not use_mock:
        tagger = CerebrasTagger(
            api_key=cerebras_key,
            interval_seconds=args.interval,
        )
        logger.info("Groq tagger initialized (model: %s, interval: %.1fs)", tagger.model, args.interval)
    else:
        logger.info("Running with deterministic mock tagger.")

    # 5. Process items
    total_to_process = len(unprocessed)
    tagged_count = 0
    error_count = 0
    relevant_count = 0
    start_time = time.time()

    logger.info("Starting tagging run for %d items...", total_to_process)

    try:
        for idx, item in enumerate(unprocessed, start=1):
            item_id = item["item_id"]
            source = item.get("source", "unknown")
            snippet = item.get("text", "")[:60].replace("\n", " ")

            if use_mock:
                tags = mock_tag_item(item)
                err = None
            else:
                assert tagger is not None
                tags, err = tagger.tag_item(item)

            if tags is None or err is not None:
                error_count += 1
                logger.error("[%d/%d] FAILED item_id=%s (%s): %s", idx, total_to_process, item_id, source, err)
                continue

            # Validate schema
            is_valid, validation_errors = validate_tag(tags)
            if not is_valid:
                error_count += 1
                logger.error("[%d/%d] SCHEMA ERROR item_id=%s: %s", idx, total_to_process, item_id, validation_errors)
                continue

            # Save immediately to SQLite
            save_tagged_item(item, tags, db_path=db_path)
            tagged_count += 1
            if tags.get("is_relevant"):
                relevant_count += 1

            rel_str = "RELEVANT" if tags.get("is_relevant") else "not-relevant"
            photo_str = f" [{tags.get('photo_type')}]" if tags.get("photo_type") else ""
            logger.info(
                "[%d/%d] (%s) %s%s | %s...",
                idx,
                total_to_process,
                source,
                rel_str,
                photo_str,
                snippet,
            )

    except KeyboardInterrupt:
        logger.warning("\nTagging run interrupted by user (Ctrl+C).")
        logger.warning("Progress so far has been safely committed to SQLite.")

    elapsed = time.time() - start_time
    logger.info("=" * 60)
    logger.info(
        "Run finished: %d tagged successfully, %d errors in %.1f seconds (%.2f s/item)",
        tagged_count,
        error_count,
        elapsed,
        (elapsed / tagged_count) if tagged_count > 0 else 0,
    )
    _print_summary(db_path)


def _print_summary(db_path: Path) -> None:
    """Prints a formatted summary of the database."""
    stats = get_tag_stats(db_path)
    print("\n" + "=" * 60)
    print(f"DATABASE SUMMARY ({db_path}):")
    print(f"  Total Tagged Items:  {stats['total_items']}")
    print(f"  Relevant Items:      {stats['relevant_items']} ({stats['relevance_rate_pct']}%)")
    print(f"  Irrelevant Items:    {stats['irrelevant_items']}")
    print("\n  Counts by Source:")
    for src, count in sorted(stats["sources"].items()):
        print(f"    - {src:25s}: {count}")
    if stats["photo_types"]:
        print("\n  Counts by Photo Type:")
        for pt, count in sorted(stats["photo_types"].items()):
            print(f"    - {pt:25s}: {count}")
    if stats["failure_stages"]:
        print("\n  Counts by Failure Stage:")
        for stage, count in sorted(stats["failure_stages"].items()):
            print(f"    - {stage:35s}: {count}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
