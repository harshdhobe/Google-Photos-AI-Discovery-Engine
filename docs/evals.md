# Evals

Pass/fail is a checklist, not a judgment call.

## Phase 1 — Collection

**Scenario:** `run_collection.py` executed with default counts.

**Expected:** A JSON file is created in `data/raw/` with combined items from both sources; no item has empty text; `item_id` is unique within each source; the console prints total count and a per-source breakdown.

**Pass criteria (all must hold):**

- [ ] `run_collection.py` exits without an uncaught exception.
- [ ] A new file matching `data/raw/collected_YYYYMMDD_HHMMSS.json` exists after the run.
- [ ] The file is valid JSON and contains a list of objects.
- [ ] The list includes items with `source` equal to `play_store`.
- [ ] The list includes items with `source` equal to `google_photos_community`.
- [ ] Every object has keys: `source`, `item_id`, `text`, `date`, `rating`.
- [ ] No item has `text` that is missing, `null`, or empty/whitespace-only.
- [ ] Within `play_store`, every `item_id` appears at most once.
- [ ] Within `google_photos_community`, every `item_id` appears at most once.
- [ ] Console output includes a total item count.
- [ ] Console output includes a per-source count for `play_store`.
- [ ] Console output includes a per-source count for `google_photos_community`.

## Phase 2+

Not specified yet.
