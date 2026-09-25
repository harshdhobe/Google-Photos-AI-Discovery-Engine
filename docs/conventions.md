# Conventions

Persistent coding and environment rules. Mirror: `.cursorrules` at project root (auto-loaded each session).

## Environment

- Machine: Windows
- Shell: PowerShell only
- Activate venv: `.\venv\Scripts\Activate.ps1` (never `source venv/bin/activate`)
- Create venv: `python -m venv venv` (or the installed Python 3.12 path if `python` is the Store stub)
- Install: `pip install -r requirements.txt`
- Run collection: `python run_collection.py`

## Folder structure

```text
collectors/          # Layer 1 source collectors
pipeline/            # tagging logic (Phase 2+)
db/                  # SQLite storage (Phase 3+)
data/raw/            # timestamped Layer 1 JSON dumps
run_collection.py    # Phase 1 orchestrator
docs/                # project memory (this folder)
```

## Error handling

- Every collector **catches its own failures** and returns `[]` or partial results. Do not crash the orchestrator.
- Skip records with empty / missing `text`.
- One failed source or thread must not abort the rest of the run.
- Any collector that **requires API credentials** must check for their presence at startup. If any required env var is missing, log a clear warning (e.g. `WARNING: REDDIT_CLIENT_ID not set — reddit collector skipped`) and return `[]`. A partial `.env` must never break the full collection run.
- **Quora scraping**: Quora requires a browser-like `User-Agent` header and conservative request pacing (1.5–2.0s delay between calls) due to strict anti-scraping measures and CAPTCHA challenge pages.

## Layer 1 record shape

Every collected item:

```text
source: str
item_id: str          # unique within that source
text: str             # non-empty
date: str | null      # ISO when available
rating: int | null
```

## Libraries to use

| Phase | Libraries |
| --- | --- |
| 1 | `google-play-scraper`, `requests`, `beautifulsoup4`, `python-dotenv` |
| 1b | `app-store-scraper`, `praw`, `google-api-python-client` |
| 2 | `google-generativeai` (Gemini free tier only) |
| 5 | `streamlit` |

## Libraries to avoid (hard constraint)

- `anthropic`
- `openai`
- Any other paid API SDK

There is **no paid API budget**. Tagging and Q&A use Gemini free tier only (Google AI Studio). Do not add Claude, OpenAI, or Grok API clients.

## Docs vs chat

`docs/` is the source of truth across sessions. Prefer these files over prior chat history when they disagree.
