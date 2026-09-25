"""
Discovery Engine — Phase 4 Aggregation & Cross-Tabulations.

Connects to data/tagged.db, pulls all rows where is_relevant = 1,
unnests multi-value memory cues, and computes 4 core cross-tabulation matrices:
  1. failure_stage × photo_type
  2. memory_cues_missing × photo_type
  3. failure_stage × workaround
  4. memory_cues_retained × memory_cues_missing

Exports matrices to data/aggregated/crosstabs.json and displays raw tables.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "tagged.db"
AGGREGATED_DIR = BASE_DIR / "data" / "aggregated"

# Configure stdout for UTF-8 on Windows
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def parse_json_list(val: Any) -> list[str]:
    """Safely parse a JSON array of strings, or return empty list."""
    if not val:
        return []
    if isinstance(val, list):
        return [str(x) for x in val if x]
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return [str(x) for x in parsed if x]
        except Exception:
            pass
    return []


def load_relevant_items(db_path: Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    """Pull all rows from tagged_items where is_relevant = 1."""
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found at {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, item_id, source, raw_text, date, rating,
                   is_relevant, photo_type, memory_cues_retained, memory_cues_missing,
                   failure_stage, workaround, representative_quote, tagged_at
            FROM tagged_items
            WHERE is_relevant = 1
            ORDER BY id ASC
            """
        )
        rows = cursor.fetchall()
        items = []
        for r in rows:
            d = dict(r)
            d["retained_cues"] = parse_json_list(d.get("memory_cues_retained"))
            d["missing_cues"] = parse_json_list(d.get("memory_cues_missing"))
            d["photo_type"] = d.get("photo_type") or "(not_stated)"
            d["failure_stage"] = d.get("failure_stage") or "(not_stated)"
            d["workaround"] = d.get("workaround") or "none"
            items.append(d)
        return items
    finally:
        conn.close()


def compute_cross_tab(
    pairs: list[tuple[str, str]],
    row_label: str = "Row",
    col_label: str = "Col",
) -> dict[str, Any]:
    """Given a list of (row_val, col_val), build a 2D matrix structure."""
    counts = Counter(pairs)
    all_rows = sorted({r for r, _ in counts.keys()})
    all_cols = sorted({c for _, c in counts.keys()})

    matrix_data: dict[str, dict[str, int]] = {r: {c: 0 for c in all_cols} for r in all_rows}
    row_totals: dict[str, int] = {r: 0 for r in all_rows}
    col_totals: dict[str, int] = {c: 0 for c in all_cols}

    for (r, c), n in counts.items():
        matrix_data[r][c] = n
        row_totals[r] += n
        col_totals[c] += n

    # Also extract individual cells sorted descending by count
    ranked_cells = [
        {"row": r, "col": c, "count": n}
        for (r, c), n in sorted(counts.items(), key=lambda x: x[1], reverse=True)
    ]

    return {
        "row_label": row_label,
        "col_label": col_label,
        "rows": all_rows,
        "columns": all_cols,
        "grid": matrix_data,
        "row_totals": row_totals,
        "col_totals": col_totals,
        "total_associations": len(pairs),
        "ranked_cells": ranked_cells,
    }


def format_matrix_table(matrix: dict[str, Any], title: str) -> str:
    """Format a computed matrix as a clean ASCII/Markdown table."""
    rows = matrix["rows"]
    cols = matrix["columns"]
    grid = matrix["grid"]
    row_totals = matrix["row_totals"]
    col_totals = matrix["col_totals"]
    total = sum(row_totals.values())

    # Header
    col_widths = {c: max(len(c), 6) for c in cols}
    row_label = f"{matrix['row_label']} \\ {matrix['col_label']}"
    first_col_width = max(len(row_label), max((len(r) for r in rows), default=10)) + 2

    for r in rows:
        for c in cols:
            col_widths[c] = max(col_widths[c], len(str(grid[r][c])))
    for c in cols:
        col_widths[c] = max(col_widths[c], len(str(col_totals[c])))

    lines = []
    lines.append(f"\n{'=' * 90}")
    lines.append(f"  {title.upper()}")
    lines.append(f"{'=' * 90}")

    header = f"{row_label:<{first_col_width}} | " + " | ".join(f"{c:>{col_widths[c]}}" for c in cols) + " | " + f"{'TOTAL':>6}"
    sep = "-" * len(header)
    lines.append(header)
    lines.append(sep)

    for r in rows:
        row_str = f"{r:<{first_col_width}} | " + " | ".join(f"{grid[r][c]:>{col_widths[c]}}" for c in cols) + " | " + f"{row_totals[r]:>6}"
        lines.append(row_str)

    lines.append(sep)
    total_str = f"{'TOTAL':<{first_col_width}} | " + " | ".join(f"{col_totals[c]:>{col_widths[c]}}" for c in cols) + " | " + f"{total:>6}"
    lines.append(total_str)
    lines.append(f"{'=' * 90}\n")
    return "\n".join(lines)


def run_aggregation(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    """Execute aggregation, display matrices, and save to crosstabs.json."""
    items = load_relevant_items(db_path)
    total_relevant = len(items)

    print(f"\nLoaded {total_relevant} relevant items (is_relevant = 1) from {db_path}\n")

    # 1. failure_stage × photo_type (1 pair per item)
    p1 = [(i["failure_stage"], i["photo_type"]) for i in items]
    m1 = compute_cross_tab(p1, row_label="failure_stage", col_label="photo_type")

    # 2. memory_cues_missing × photo_type (unnested missing cues)
    p2 = [
        (cue, i["photo_type"])
        for i in items
        for cue in (i["missing_cues"] if i["missing_cues"] else ["none_mentioned"])
    ]
    m2 = compute_cross_tab(p2, row_label="memory_cues_missing", col_label="photo_type")

    # 3. failure_stage × workaround (1 pair per item)
    p3 = [(i["failure_stage"], i["workaround"]) for i in items]
    m3 = compute_cross_tab(p3, row_label="failure_stage", col_label="workaround")

    # 4. memory_cues_retained × memory_cues_missing (unnested pairs)
    p4 = []
    for i in items:
        retained = i["retained_cues"] if i["retained_cues"] else ["none_mentioned"]
        missing = i["missing_cues"] if i["missing_cues"] else ["none_mentioned"]
        for r_cue in retained:
            for m_cue in missing:
                p4.append((r_cue, m_cue))
    m4 = compute_cross_tab(p4, row_label="memory_cues_retained", col_label="memory_cues_missing")

    # Display tables in terminal
    print(format_matrix_table(m1, "Matrix 1: Failure Stage × Photo Type"))
    print(format_matrix_table(m2, "Matrix 2: Memory Cues Missing × Photo Type"))
    print(format_matrix_table(m3, "Matrix 3: Failure Stage × Workaround"))
    print(format_matrix_table(m4, "Matrix 4: Memory Cues Retained × Memory Cues Missing"))

    # Print top ranked cells for each matrix
    print("\n" + "=" * 90)
    print("  TOP CELL ASSOCIATIONS BY COUNT (RAW RANKINGS)")
    print("=" * 90)

    print("\n[Matrix 1 Top Cells: failure_stage × photo_type]")
    for idx, c in enumerate(m1["ranked_cells"][:6], 1):
        print(f"  {idx}. {c['row']} × {c['col']}: {c['count']} items")

    print("\n[Matrix 2 Top Cells: memory_cues_missing × photo_type]")
    for idx, c in enumerate(m2["ranked_cells"][:6], 1):
        print(f"  {idx}. missing {c['row']} on photo_type {c['col']}: {c['count']} associations")

    print("\n[Matrix 3 Top Cells: failure_stage × workaround]")
    for idx, c in enumerate(m3["ranked_cells"][:6], 1):
        print(f"  {idx}. {c['row']} -> workaround {c['col']}: {c['count']} items")

    print("\n[Matrix 4 Top Cells: memory_cues_retained × memory_cues_missing]")
    for idx, c in enumerate(m4["ranked_cells"][:6], 1):
        print(f"  {idx}. retained {c['row']} while missing {c['col']}: {c['count']} associations")

    print("\n" + "=" * 90 + "\n")

    # Package output
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_relevant_items": total_relevant,
        "matrix_1_failure_stage_x_photo_type": m1,
        "matrix_2_memory_cues_missing_x_photo_type": m2,
        "matrix_3_failure_stage_x_workaround": m3,
        "matrix_4_memory_cues_retained_x_memory_cues_missing": m4,
    }

    # Save to data/aggregated/crosstabs.json
    AGGREGATED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = AGGREGATED_DIR / "crosstabs.json"
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Exported raw matrices to {out_path}\n")

    return payload


if __name__ == "__main__":
    run_aggregation()
