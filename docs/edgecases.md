# Edge cases

## Anticipated

- **Empty / missing text** — skip the item; do not write it to JSON.
- **Forum HTML structure changes** — Google Photos Help Community selectors / embedded JSON can break; collector should fail that page, log, and continue rather than crash. Selectors may need updating.
- **Rate-limiting / blocking** — Play Store or community requests may throttle or block; use timeouts, polite delays, catch HTTP errors, return partial results.
- **Duplicate items across runs** — same `item_id` can reappear if collection is re-run; uniqueness is required *within a source in a single output file* for Phase 1. Cross-run dedup is later.
- **Missing / unparseable dates** — store `date` as `null`; do not drop the item if `text` is present.
- **Missing or invalid API credentials** — Reddit and YouTube collectors check for required env vars (`REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT`, `YOUTUBE_API_KEY`) at startup. If any required var is absent or empty, the collector logs a warning and returns `[]`. An invalid credential that causes an API error (e.g. 401/403) should be caught, logged, and return partial results.
- **YouTube quota exhaustion** — the YouTube Data API v3 has a default daily quota of 10,000 units. `commentThreads().list` costs 1 unit per call. If quota is exceeded the API returns HTTP 403 with `quotaExceeded` in the error reason; the collector must catch `HttpError`, log the reason, and return whatever items were collected before the quota hit.
- **Reddit unauthenticated rate limiting (429s) — mitigated with delay + single retry** — Reddit's public endpoints return HTTP 429 when hit too frequently. The collector uses a polite delay (1.8s) between requests, custom User-Agent, and catches 429 to sleep/back off for 6s before a single retry; if it still fails, skips the request without crashing.
- **Quora CAPTCHA/block pages served instead of content** — Quora aggressively challenges and blocks automated HTTP requests with Cloudflare or CAPTCHA pages (e.g. HTTP 403 or challenge payloads). The collector checks for block indicators, logs a warning, and skips rather than treating as valid empty content.

## Discovered during build

- **App Store collector was scaffolded but never wired into run_collection.py**: The collector `collectors/app_store.py` existed, but `run_collection.py` defaulted `app_store_count` to 0, omitted `app_store` from `ALL_SOURCES`, and lacked visible try/except reporting, so reviews never appeared in the output.
- **`app-store-scraper` token extraction on Apple web layout**: Apple's App Store landing page structure changed, removing the legacy `web-experience-app/config/environment` meta tag that `app-store-scraper` used to parse its bearer token. Consequently, requests to Apple's review API return non-JSON responses (`Expecting value: line 1 column 1`). The collector caught this failure and safely returned `[]` without crashing the orchestrator.
- **Python 3.12 & `app-store-scraper` dependency pinning**: `app-store-scraper`'s PyPI package pins `requests==2.23.0` which pulls `urllib3 1.25.11` (which fails on Python 3.12 due to `urllib3.packages.six.moves`). Upgrading to modern `requests` and `urllib3` allows all packages to import cleanly on Python 3.12.
- **Reddit unauthenticated JSON HTTP 403**: Reddit's `search.json` endpoints frequently return HTTP 403 Forbidden to scripted requests depending on IP range and headers. The collector caught the status, logged warnings, and safely returned without aborting the pipeline.
- **Windows console emoji / Unicode encoding in terminal output**: Raw user feedback contains emojis (e.g., `😎`, `👍`) and unicode characters that cause `UnicodeEncodeError` on Windows `cp1252` consoles. Solved by calling `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` in `pipeline/run_tagging.py` and `pipeline/validate_sample.py`.
- **SQLite open connection handles on Windows**: Open database connections cause `PermissionError` when resetting or accessing files. Solved by wrapping connections in `get_db()` context manager that reliably executes `conn.close()`.
