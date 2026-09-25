# Decisions

Log architectural and scope decisions here. Newest first.

## 2026-09-23 — Redesigned Phase 5 interface from tab-based navigation to single-scroll layout

**Decision:** Redesigned Phase 5 interface from tab-based navigation to a single-scroll layout
with a visible pipeline-status strip and evidence-confidence badges, based on review of stronger
reference implementations (e.g. Blinkit's discovery engine pattern: visible pipeline status,
question-first framing, validation signals, progressive disclosure of raw data).

**Structure:** Header → Provisional Data Banner → Pipeline Status Strip (5 stage cards with live
counts) → KPI Banner (data-driven, no hardcoding) → Question-Framed Cluster Cards with
Confidence Badges → Q&A Panel → Collapsed Full Data Explorer → Methodology Footer.

**Visual identity:** Color palette aligned to Google Photos brand colors — Google Blue (#4285F4),
Google Green (#34A853), Google Yellow (#FBBC04), Google Red (#EA4335) — on a deep slate dark base.
Typography uses Inter / Google Sans from Google Fonts.

**Evidence confidence badges:** Derived from real item counts per cluster (≥20 items → Strong,
8–19 → Moderate, <8 → Limited) and displayed beside the cluster headline for immediate visibility.

**Status:** Accepted.

## 2026-09-22 — Algorithmic derivation of Phase 4 opportunity clusters

**Decision:** Opportunity clusters in Phase 4 are algorithmically derived from matrix cell counts after aggregation, not predefined — this ensures findings reflect actual data patterns rather than a pre-written narrative.

**Why:** Pre-defining cluster labels (e.g. assuming specific drop-offs ahead of time) risks confirmation bias. Deriving clusters directly from ranked cell counts across the 4 cross-tabulation matrices guarantees that opportunity areas emerge strictly from real user feedback frequencies and are backed by authentic quotes.

**Status:** Accepted.

## 2026-09-22 — Added Quora source and fixed App Store collector wiring (Phase 1c)

**Decision:** Added Quora as a 6th collection source — highest expected relevance density among candidate sources for narrative, memory-specific photo-search questions. Fixed App Store collector wiring/config issue found during Phase 1c.

**Why:** App Store was previously scaffolded in `collectors/app_store.py` but defaulted to 0 and was excluded from `ALL_SOURCES` in `run_collection.py`. Quora provides rich user-written questions and detailed workarounds for retrieval challenges without needing API credentials (`requests` + `BeautifulSoup`).

**Status:** Accepted.

## 2026-09-21 — Switched Layer 2 tagging provider to Groq (from Cerebras)

**Decision:** Use Groq free-tier API (`llama-3.3-70b-versatile`, OpenAI-compatible endpoint at `https://api.groq.com/openai/v1`) for Phase 2 AI tagging. Cerebras was originally planned but failed at runtime: `llama-3.3-70b` returned HTTP 404 (model not found on account); `qwen-3.8-27b` (an available model) returned HTTP 402 (payment required — Cerebras free tier is credit-card-gated). Groq is genuinely free with no credit card required.

**Why:** Groq offers `llama-3.3-70b-versatile` (the originally intended model) with 14,400 req/day free, no payment required, supports JSON mode (`response_format={"type": "json_object"}`), and is OpenAI-compatible — identical code change (3 lines: base_url, model, env var name).

**Status:** Accepted.

## 2026-09-21 — Reddit collection switched to public unauthenticated JSON endpoints

**Decision:** Switched Reddit collection from PRAW/OAuth to Reddit's public unauthenticated JSON endpoints, since Reddit's script-app creation flow is currently blocked/gated for new registrations. This also keeps Reddit collection keyless, consistent with Play Store and Google Photos Community.

**Why:** Allows collecting real Reddit posts and comments without requiring blocked or gated OAuth credentials. Employs polite request delays and single retry on 429 rate-limiting.

**Status:** Accepted.

## 2026-09-21 — Phase 1b collectors fail soft on missing credentials

**Decision:** Reddit (`collectors/reddit.py`) and YouTube (`collectors/youtube.py`) collectors check for required env vars at startup. If any var is missing they log a descriptive warning and return `[]` rather than raising an exception.

**Why:** API credentials (Reddit app ID/secret, YouTube API key) may be added incrementally across sessions. A missing credential in `.env` must not abort the full `run_collection.py` run or produce an uncaught exception. The orchestrator will show `0 items` for the skipped source in its summary.

**Status:** Accepted.

## 2026-09-18 — Phase 1 restricted to keyless sources

**Decision:** Phase 1 collectors are Google Play Store reviews and Google Photos Help Community only.

**Why:** Those sources work without API keys (`google-play-scraper`; public HTML via `requests` + BeautifulSoup). Reddit, App Store, and YouTube wait until keys exist so collection is not blocked on account/API setup.

**Status:** Accepted.

## 2026-09-18 — Free-tier AI only (updated 2026-09-21)

**Decision:** Layer 2 tagging uses Cerebras free tier (see decision above). Layer 5 Q&A will also use a free-tier LLM (TBD at Phase 5). Do not use any paid API: no Claude, no OpenAI (paid), no Grok.

**Why:** Only free-tier APIs are available for this project. There is no paid API budget.

**Status:** Accepted (updated).
