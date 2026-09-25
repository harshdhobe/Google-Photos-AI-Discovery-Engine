"""
SQLite storage for Discovery Engine Layer 2 tagged items.
Handles schema initialization, upserting tagged items, and resume state checks.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Set

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "tagged.db"


@contextlib.contextmanager
def get_db(db_path: Path | str = DEFAULT_DB_PATH) -> Generator[sqlite3.Connection, None, None]:
    """Yields a SQLite connection with row factory and closes it when done."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db(db_path: Path | str = DEFAULT_DB_PATH) -> None:
    """Initializes the SQLite database tables and indices if they do not exist."""
    with get_db(db_path) as conn:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tagged_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id TEXT UNIQUE NOT NULL,
                    source TEXT NOT NULL,
                    raw_text TEXT NOT NULL,
                    date TEXT,
                    rating INTEGER,
                    is_relevant INTEGER NOT NULL,
                    photo_type TEXT,
                    memory_cues_retained TEXT,
                    memory_cues_missing TEXT,
                    failure_stage TEXT,
                    workaround TEXT,
                    representative_quote TEXT,
                    tagged_at TEXT NOT NULL
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tagged_item_id ON tagged_items(item_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tagged_source ON tagged_items(source);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tagged_is_relevant ON tagged_items(is_relevant);")


def save_tagged_item(
    item: Dict[str, Any],
    tags: Dict[str, Any],
    db_path: Path | str = DEFAULT_DB_PATH,
) -> None:
    """
    Inserts or updates a tagged item in SQLite.
    Serializes list fields (memory cues) to JSON strings.
    """
    retained_json = json.dumps(tags.get("memory_cues_retained") or [])
    missing_json = json.dumps(tags.get("memory_cues_missing") or [])
    tagged_at = datetime.now(timezone.utc).isoformat()
    is_relevant_int = 1 if tags.get("is_relevant") else 0

    with get_db(db_path) as conn:
        with conn:
            conn.execute(
                """
                INSERT INTO tagged_items (
                    item_id, source, raw_text, date, rating,
                    is_relevant, photo_type, memory_cues_retained, memory_cues_missing,
                    failure_stage, workaround, representative_quote, tagged_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(item_id) DO UPDATE SET
                    source=excluded.source,
                    raw_text=excluded.raw_text,
                    date=excluded.date,
                    rating=excluded.rating,
                    is_relevant=excluded.is_relevant,
                    photo_type=excluded.photo_type,
                    memory_cues_retained=excluded.memory_cues_retained,
                    memory_cues_missing=excluded.memory_cues_missing,
                    failure_stage=excluded.failure_stage,
                    workaround=excluded.workaround,
                    representative_quote=excluded.representative_quote,
                    tagged_at=excluded.tagged_at;
                """,
                (
                    item.get("item_id"),
                    item.get("source"),
                    item.get("text"),
                    item.get("date"),
                    item.get("rating"),
                    is_relevant_int,
                    tags.get("photo_type"),
                    retained_json,
                    missing_json,
                    tags.get("failure_stage"),
                    tags.get("workaround"),
                    tags.get("representative_quote"),
                    tagged_at,
                ),
            )


def get_tagged_item_ids(db_path: Path | str = DEFAULT_DB_PATH) -> Set[str]:
    """Returns a set of all item_ids currently stored in the database for resumability."""
    init_db(db_path)
    with get_db(db_path) as conn:
        cursor = conn.execute("SELECT item_id FROM tagged_items;")
        return {row[0] for row in cursor.fetchall()}


def get_tagged_sample(db_path: Path | str = DEFAULT_DB_PATH, limit: int = 20) -> List[Dict[str, Any]]:
    """Retrieves a sample of tagged items for manual inspection."""
    init_db(db_path)
    with get_db(db_path) as conn:
        cursor = conn.execute(
            """
            SELECT item_id, source, raw_text, date, rating,
                   is_relevant, photo_type, memory_cues_retained, memory_cues_missing,
                   failure_stage, workaround, representative_quote, tagged_at
            FROM tagged_items
            ORDER BY id DESC
            LIMIT ?;
            """,
            (limit,),
        )
        results = []
        for row in cursor.fetchall():
            d = dict(row)
            d["is_relevant"] = bool(d["is_relevant"])
            try:
                d["memory_cues_retained"] = json.loads(d["memory_cues_retained"] or "[]")
            except Exception:
                pass
            try:
                d["memory_cues_missing"] = json.loads(d["memory_cues_missing"] or "[]")
            except Exception:
                pass
            results.append(d)
        return results


def get_tag_stats(db_path: Path | str = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """Returns summary metrics of the current database state."""
    init_db(db_path)
    with get_db(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM tagged_items;").fetchone()[0]
        relevant = conn.execute("SELECT COUNT(*) FROM tagged_items WHERE is_relevant = 1;").fetchone()[0]
        sources = dict(
            conn.execute(
                "SELECT source, COUNT(*) FROM tagged_items GROUP BY source;"
            ).fetchall()
        )
        stages = dict(
            conn.execute(
                "SELECT failure_stage, COUNT(*) FROM tagged_items WHERE failure_stage IS NOT NULL GROUP BY failure_stage;"
            ).fetchall()
        )
        photo_types = dict(
            conn.execute(
                "SELECT photo_type, COUNT(*) FROM tagged_items WHERE photo_type IS NOT NULL GROUP BY photo_type;"
            ).fetchall()
        )
        return {
            "total_items": total,
            "relevant_items": relevant,
            "irrelevant_items": total - relevant,
            "relevance_rate_pct": round((relevant / total * 100), 1) if total > 0 else 0.0,
            "sources": sources,
            "failure_stages": stages,
            "photo_types": photo_types,
        }
