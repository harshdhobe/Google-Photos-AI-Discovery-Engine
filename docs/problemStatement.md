# Problem Statement

## What are we building?
An AI-powered discovery engine that analyzes public user feedback about Google Photos to 
identify and compare why users fail to retrieve photos they remember vaguely but can't 
precisely search for — evidence for a Google Photos PM case study project.

## Who is it for?
Evaluators/mentors who will open a deployed link, filter/query the findings themselves, and 
judge whether the analysis goes beyond summarization or sentiment scoring.

## What does success look like?
- ≥100-150 real, relevant items collected from at least 2 public sources
- Each item tagged with structured fields (photo type, memory cues retained/missing, failure 
  stage, workaround) via a free-tier AI model — not manual reading
- A public dashboard where cross-tab comparisons (e.g. failure stage by photo type) are 
  filterable, with drill-down to real quotes
- A Q&A panel that answers free-form questions grounded in the tagged corpus, with citations

## What is explicitly out of scope (for now)?
- Reddit / App Store / YouTube collectors (Phase 1 covers only keyless sources)
- Any paid AI API (Claude, OpenAI, Grok) — Gemini free tier only, by hard constraint
- Gemini tagging, SQLite storage, and the Streamlit interface are separate phases, not built yet
