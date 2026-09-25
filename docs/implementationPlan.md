# Implementation Plan

Phases match the five architecture layers. Detail exists only for the current phase. Phases 2–5 are one-line placeholders until we get there.

Source of truth: [architecture.md](architecture.md), [problemStatement.md](problemStatement.md).

## Phase 1 — Collection (current)

**Goal:** Collect ~100 items each from:

- Google Play Store reviews via `google-play-scraper`, app id `com.google.android.apps.photos`
- Google Photos Help Community via `requests` + BeautifulSoup (public HTML, no API)

**Depends on:** nothing

**Done when:** `run_collection.py` produces a timestamped JSON file with combined items from both sources, each matching the shared record shape `{source, item_id, text, date, rating}`, and prints a summary of counts per source.

## Phase 1b — Additional Collectors

**Goal:** Add App Store, Reddit, and YouTube collectors to the existing Play Store + Google Photos Community collectors.

**Depends on:** Phase 1

**Done when:** `run_collection.py` merges all 5 sources into one output file, with sources gracefully skipped (not crashing) if their required env vars are missing. The printed summary explicitly shows 0 items for any skipped source.

## Phase 1c — App Store Fix + Quora Collector (complete)

**Goal:** Debug why App Store reviews aren't appearing in run output despite the collector already existing, and add a new Quora collector.

**Depends on:** Phase 1

**Done when:** `run_collection.py`'s per-source summary shows non-zero counts for `app_store` and attempts `quora`. (Satisfied: 1,750 real live items collected in `data/raw/collected_20260922_134105.json`, including 250 App Store reviews; hardcoded fallbacks removed from Quora).

## Phase 2 — AI Tagging (complete)

**Goal:** Tag every pre-filtered Layer 1 item with structured JSON via Groq (`llama-3.3-70b`) — relevance, photo type, memory cues, failure stage, workaround, and a representative quote. Store results in SQLite.

**Depends on:** Phase 1b & 1c (corpus in `data/raw/`)

**Done when:**
- `pipeline/run_tagging.py` runs to completion without crashing (Satisfied: 2,171 items tagged in SQLite).
- SQLite DB at `data/tagged.db` contains rows for all successfully tagged items.
- Each row passes `validate_tag()` (all 7 schema fields present and valid).
- Run is safely resumable — re-running skips already-tagged items.
- `pipeline/validate_sample.py` prints items with raw text + parsed tags side-by-side for manual review.

## Phase 3 — Storage (complete)

**Goal:** Persist tagged items in local SQLite, one row per item, joined to the original Layer 1 record.
(Satisfied: Implemented via `db/database.py` with indexed schema; 2,171 rows stored in `data/tagged.db`).

## Phase 4 — Aggregation (complete)

**Goal:** Compute 4 core cross-tabulation matrices over `data/tagged.db` (`is_relevant = 1`), algorithmically derive opportunity clusters backed by real quotes, and produce the primary PM research deliverable (`docs/findings.md`).

**Depends on:** Phase 2 & 3 (tagged SQLite database)

**Done when:**
- `pipeline/aggregate.py` connects to `data/tagged.db`, unnests memory cues, and generates all 4 cross-tab matrices exported to `data/aggregated/crosstabs.json`:
  1. `failure_stage × photo_type`
  2. `memory_cues_missing × photo_type`
  3. `failure_stage × workaround`
  4. `memory_cues_retained × memory_cues_missing`
- Opportunity clusters are algorithmically derived from top cell rankings (not predefined) with 3 traceable authentic user quotes each, exported to `data/aggregated/findings.json` via `pipeline/generate_findings.py`.
- Senior PM research memo written at `docs/findings.md` covering:
  1. Executive summary (biggest failure pattern: zero-yield cliff at 52.8%)
  2. 4 Markdown matrix tables
  3. 5 derived opportunity clusters with data, behavioral gap, quotes, and PM product recommendations
  4. Cross-platform source breakdown across all 6 channels
  5. Methodological notes and constraints

## Phase 5 — Interface (complete)

**Goal:** Ship a high-design Streamlit web app deployed on Streamlit Community Cloud featuring:
1. **Interactive Cross-Tabs Dashboard:** Visual matrices, dynamic filters (by source, failure stage, photo type, missing cues), and drill-down to verbatim representative quotes.
2. **Derived Opportunity Clusters View:** Cards showcasing the 5 algorithmically derived failure clusters with metrics and behavioral gaps.
3. **Cited Q&A Panel (RAG over Tagged Corpus):** Free-text PM research questions answered using free-tier LLM, grounded with exact verbatim citations from the SQLite corpus.

(Satisfied: Built `discovery-engine/app.py` with 3 comprehensive tabs, `discovery-engine/pipeline/qa_engine.py` with Groq RAG citation engine, `app.py` root entrypoint for Streamlit Community Cloud, and `docs/deployment.md` step-by-step guide. App running live locally on `http://localhost:8501`).


