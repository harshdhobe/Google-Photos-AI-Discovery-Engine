# Architecture

Discovery Engine is a 5-layer pipeline. Each layer has one job. Intelligence lives in Layer 2 (tagging) and Layer 5 (grounded Q&A) — not in collection or storage.

Source of truth for *why* we are building this: [problemStatement.md](problemStatement.md).

```text
Public feedback
      |
      v
Layer 1  Collection     -> flat records {source, item_id, text, date, rating}
      |
      v
Layer 2  AI Tagging     -> Gemini structured JSON (relevance + retrieval tags)
      |
      v
Layer 3  Storage        -> SQLite, one row per tagged item
      |
      v
Layer 4  Aggregation    -> cross-tabs (opportunity clusters, not sentiment)
      |
      v
Layer 5  Interface      -> Streamlit dashboard + cited Q&A (public link)
```

## Why this shape

- **Comparative, not summarative.** Mentors will judge whether we go beyond sentiment. Layers 2–4 force every item into comparable fields (failure stage, photo type, memory cues) so Layer 5 can show cross-tabs and quotes, not a prose recap.
- **Free-tier only.** There is no paid API budget. Tagging uses Cerebras free tier (`llama-3.3-70b`, OpenAI-compatible API, 1M tokens/day, 30 RPM). Claude, OpenAI (paid), and Grok APIs are out of scope.
- **Keyless collection first.** Layer 1 starts with Play Store and Google Photos Help Community so work is not blocked on Reddit / App Store / YouTube keys.
- **Local, queryable store.** SQLite is enough for 100–150+ tagged rows, easy to ship, no hosted DB.
- **Sharable evaluation surface.** Streamlit Community Cloud is the deployed link evaluators open.

## Layer 1 — Collection

Scrapers / keyless APIs return a **flat list** of records. No relevance filter, no NLP.

Shared record shape:

```text
{
  source: str,          # e.g. "play_store" or "google_photos_community"
  item_id: str,         # unique within source, for dedup
  text: str,            # raw feedback; empty text is skipped
  date: str | null,     # ISO if available
  rating: int | null    # star rating if applicable
}
```

Phase 1 sources: Google Play Store reviews; Google Photos Help Community threads. Later sources (Reddit, App Store, YouTube) plug into the same shape.

## Layer 2 — AI tagging

Each Layer 1 item is sent to **Cerebras** (`llama-3.3-70b`) with a **fixed instruction** and **JSON mode** (`response_format={"type": "json_object"}`). The response is parsed and validated against the schema definition in `pipeline/schema.py`. No free-text parsing.

Fields:

- `is_relevant` — is this about vague-memory photo retrieval?
- `photo_type` — travel, event, person, screenshot, document_receipt, health_related, other (or null)
- `memory_cues_retained` — place, rough_time_period, people_present, activity_event, emotion_context, visual_detail, none_mentioned
- `memory_cues_missing` — exact_date, location_name, album, search_terms, device_or_year, none_mentioned
- `failure_stage` — could_not_formulate_query, query_returned_nothing, query_returned_too_much, could_not_recognize_correct_result, gave_up, not_applicable (or null)
- `workaround` — manual_scrolling, asked_another_person, checked_other_app, cross_referenced_calendar_location, none, gave_up_entirely (or null)
- `representative_quote` — short verbatim snippet for traceability

## Layer 3 — Storage

Tagged output joined back to the Layer 1 record. SQLite: one row per feedback item. Tag fields as columns plus `raw_text` and `source`.

## Layer 4 — Aggregation

Cross-tabulations over tagged rows (e.g. `failure_stage` × `photo_type`, `memory_cues_missing` × `source`). This is where comparative “opportunity area” findings come from — counts of tags, not star-rating averages.

## Layer 5 — Interface

Streamlit app, two views:

1. Filterable dashboard of Layer 4 cross-tabs, drill-down to `representative_quote` / source text.
2. Q&A panel: retrieve relevant tagged rows, then Gemini synthesizes a **cited** answer (RAG over the tagged corpus).

Deployed on Streamlit Community Cloud.

## Explicit non-goals in this architecture

- Paid model SDKs (`anthropic`, `openai` paid tiers, etc.).
- Intelligence inside Layer 1 (collectors stay dumb).
- Hosted databases or a custom web frontend for Phase 5.
