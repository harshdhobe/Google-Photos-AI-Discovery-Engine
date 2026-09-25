"""
Discovery Engine — Phase 2 Sample Review Tool.
Prints tagged items with raw feedback text side-by-side with parsed tags for manual inspection.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure discovery-engine root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from db.database import DEFAULT_DB_PATH, get_db, init_db

# Configure stdout for UTF-8 on Windows
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def print_sample_review(db_path: Path, limit: int = 20, relevant_only: bool = False) -> None:
    init_db(db_path)

    query = """
        SELECT item_id, source, raw_text, date, rating,
               is_relevant, photo_type, memory_cues_retained, memory_cues_missing,
               failure_stage, workaround, representative_quote, tagged_at
        FROM tagged_items
    """
    if relevant_only:
        query += " WHERE is_relevant = 1"
    query += " ORDER BY is_relevant DESC, id DESC LIMIT ?"

    with get_db(db_path) as conn:
        cursor = conn.execute(query, (limit,))
        rows = cursor.fetchall()

    if not rows:
        print(f"No tagged items found in {db_path}.")
        return

    print("=" * 80)
    print(f"SAMPLE REVIEW: {len(rows)} ITEMS FROM {db_path}")
    print("=" * 80)

    for idx, row in enumerate(rows, start=1):
        item_id = row["item_id"]
        source = row["source"]
        is_relevant = bool(row["is_relevant"])
        raw_text = (row["raw_text"] or "").strip()
        photo_type = row["photo_type"] or "N/A"
        retained = row["memory_cues_retained"] or "[]"
        missing = row["memory_cues_missing"] or "[]"
        stage = row["failure_stage"] or "N/A"
        workaround = row["workaround"] or "N/A"
        quote = row["representative_quote"] or "N/A"

        status_badge = "[RELEVANT]" if is_relevant else "[NOT RELEVANT]"

        print(f"\n--- Item {idx}/{len(rows)}: {status_badge} ({source}) ---")
        print(f"ID: {item_id}")
        print("RAW FEEDBACK:")
        # Indent raw feedback for readability
        for line in raw_text.splitlines():
            print(f"  > {line}")

        print("EXTRACTED TAGS:")
        print(f"  - Relevant:             {is_relevant}")
        print(f"  - Photo Type:           {photo_type}")
        print(f"  - Memory Cues Retained: {retained}")
        print(f"  - Memory Cues Missing:  {missing}")
        print(f"  - Failure Stage:        {stage}")
        print(f"  - Workaround:           {workaround}")
        print(f"  - Quote:                \"{quote}\"")

    print("\n" + "=" * 80)
    print(f"Review complete ({len(rows)} items displayed).")
    print("=" * 80)


def main() -> None:
    parser = argparse.ArgumentParser(description="Review sample tagged items for Phase 2 validation")
    parser.add_argument(
        "--db",
        type=str,
        default=str(DEFAULT_DB_PATH),
        help=f"Path to SQLite database file (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--limit",
        "-n",
        type=int,
        default=20,
        help="Number of items to display (default: 20)",
    )
    parser.add_argument(
        "--relevant-only",
        action="store_true",
        help="Only display items tagged as relevant",
    )

    args = parser.parse_args()
    print_sample_review(Path(args.db), limit=args.limit, relevant_only=args.relevant_only)


if __name__ == "__main__":
    main()
