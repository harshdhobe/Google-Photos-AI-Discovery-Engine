"""
Discovery Engine — Google Photos Vague-Memory Retrieval Research.

Phase 5 Streamlit Interface (Redesign — Single Scroll, 2026-09-23):
- Section 0: Header + Provisional Data Banner
- Section 1: Pipeline Status Strip (live counts)
- Section 2: KPI Banner (data-driven, no hardcoding)
- Section 3+4: Question-Framed Cluster Cards with Evidence-Confidence Badges
- Section 5: Ask the Data (preset + free-text Q&A, Groq RAG)
- Section 6: Full Data Explorer (collapsed by default)
- Section 7: Methodology Footer

LLM Provider: Groq (llama-3.3-70b-versatile via OpenAI-compatible endpoint).
Cerebras was originally planned but failed at runtime; Groq is the active, confirmed provider.
See docs/decisions.md (2026-09-21 entry) for the full rationale.
"""

from __future__ import annotations

import base64
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "tagged.db"
CROSSTABS_PATH = BASE_DIR / "data" / "aggregated" / "crosstabs.json"
FINDINGS_PATH = BASE_DIR / "data" / "aggregated" / "findings.json"
RAW_DATA_DIR = BASE_DIR / "data" / "raw"
LOGO_PATH = BASE_DIR / "assets" / "google-photos-logo.png"


@st.cache_data
def get_google_photos_logo_b64() -> str:
    """Load and base64-encode the Google Photos logo for inline HTML embedding."""
    if LOGO_PATH.exists():
        with open(LOGO_PATH, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    return ""

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from pipeline.qa_engine import ask_grounded_qa, load_tagged_items

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Google Photos Discovery Engine",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Cluster name → question mapping
# Mapping by closest meaning per spec; actual cluster_id keys from findings.json.
# Spec label                          → findings.json cluster_id
# "Zero-Yield Search Failure"         → cluster_1_query_returned_nothing
# "Rough-Time-Period Paradox"         → cluster_2_rough_time_vs_exact_date_album
# "Query Formulation Impasse"         → cluster_3_query_formulation_barrier  (exact match)
# "Facial Recognition Breakdown"      → cluster_4_person_face_grouping_misidentification
# "Abandonment & Manual Scrolling"    → cluster_5_search_abandonment_and_manual_scrolling
# ---------------------------------------------------------------------------
CLUSTER_QUESTIONS: dict[str, str] = {
    "cluster_1_query_returned_nothing": "Why do searches for a remembered photo return nothing?",
    "cluster_2_rough_time_vs_exact_date_album": "What do people remember when they can't find a photo?",
    "cluster_3_query_formulation_barrier": "Why can't users describe what they're looking for?",
    "cluster_4_person_face_grouping_misidentification": "Why does search return the wrong person?",
    "cluster_5_search_abandonment_and_manual_scrolling": "What do users do when search fails them?",
}

# ---------------------------------------------------------------------------
# CSS — Light theme, centered 980px column, single accent: #1A73E8 (Google Blue)
# Background:   #FFFFFF (page) / #F8F9FA (surfaces)
# Text:         #202124 (primary) / #3C4043 (body) / #5F6368 (muted) / #80868B (caption)
# Accent:       #1A73E8 (Google Blue) — only color used for interactive/highlight elements
# Success:      #137333 text on #E6F4EA bg — paired with checkmark icon + text label
# Warning:      #7A5100 text on #FEF7E0 bg
# Error:        #C5221F text on #FCE8E6 bg
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    /* ── Global reset: full-screen neutral background (#F1F3F4), dark text ── */
    html, body,
    .stApp,
    [data-testid="stAppViewContainer"],
    [data-testid="stMainBlockContainer"],
    .main,
    [data-testid="stMain"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
        background-color: #F1F3F4 !important;
        color: #202124 !important;
    }

    /* ── Typography weights ── */
    h1, h2, h3, h4, .section-heading, .cluster-question, .hero-title {
        font-weight: 700 !important;
    }
    p, li, .stMarkdown p, [data-testid="stMarkdownContainer"] p, .hero-subtitle, .cluster-finding, .stat-sub {
        font-weight: 400 !important;
    }
    .kpi-value, .stat-value, .hero-stat, .step-count {
        font-weight: 600 !important;
    }

    /* ── Top nav bar — blends seamlessly with full-screen background ── */
    [data-testid="stHeader"] {
        background-color: #F1F3F4 !important;
        border-bottom: 1px solid #E8EAED !important;
    }

    /* ── Centered content column — expanded width (1240px) matching Blinkit reference ── */
    .main .block-container,
    [data-testid="stMainBlockContainer"] {
        max-width: 1240px !important;
        margin-left: auto !important;
        margin-right: auto !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        padding-top: 1.5rem !important;
        padding-bottom: 2.5rem !important;
        background-color: #F1F3F4 !important;
        border-radius: 0 !important;
    }

    /* ── Sidebar ── */
    [data-testid="stSidebar"],
    [data-testid="stSidebar"] > div {
        background-color: #F8F9FA !important;
        border-right: 1px solid #E8EAED !important;
    }
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] .stMarkdown {
        color: #3C4043 !important;
    }

    /* ── General text overrides ── */
    .stMarkdown p, .stMarkdown li,
    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] li {
        color: #202124 !important;
        font-size: 1.02rem !important;
        line-height: 1.6 !important;
    }
    .stMarkdown h1 { font-size: 2.1rem !important; }
    .stMarkdown h2 { font-size: 1.6rem !important; }
    .stMarkdown h3 { font-size: 1.3rem !important; }
    .stMarkdown h4 { font-size: 1.15rem !important; }

    [data-testid="stCaptionContainer"] p,
    .stCaption {
        color: #5F6368 !important;
        font-size: 0.9rem !important;
        line-height: 1.5 !important;
    }
    /* subheader text */
    [data-testid="stHeadingWithActionElements"] {
        color: #202124 !important;
    }

    /* ── Hero Header ── */
    .hero-header {
        background: #FFFFFF;
        border: 1px solid #E8EAED;
        border-radius: 12px;
        padding: 28px 32px 24px 32px;
        margin-bottom: 8px;
        box-shadow: 0 1px 4px rgba(0,0,0,0.07), 0 2px 10px rgba(0,0,0,0.04);
        position: relative;
        overflow: hidden;
    }
    /* Single accent top stripe — Google Blue, single color only */
    .hero-header::before {
        content: '';
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 4px;
        background: #4285F4;
        border-radius: 12px 12px 0 0;
    }
    .hero-logo-row {
        display: flex;
        align-items: center;
        gap: 14px;
        margin-bottom: 10px;
    }
    /* Google Photos logo icon */
    .google-photos-logo {
        width: 38px;
        height: 38px;
        object-fit: contain;
        flex-shrink: 0;
        display: block;
    }
    .hero-title {
        font-size: 2.1rem;
        font-weight: 700;
        letter-spacing: -0.02em;
        color: #202124;
        margin: 0;
        line-height: 1.25;
    }
    .hero-subtitle {
        color: #5F6368;
        font-size: 1.08rem;
        line-height: 1.65;
        margin: 0;
        max-width: 1000px;
    }

    /* ── Provisional Banner ── */
    .provisional-banner {
        background: #FEF7E0;
        border: 1px solid #F9AB00;
        border-radius: 8px;
        padding: 12px 18px;
        color: #7A5100;
        font-size: 0.92rem;
        font-weight: 500;
        margin-top: 16px;
        display: flex;
        align-items: center;
        gap: 8px;
    }

    /* ── Plain Section Headings (Sentence case, no decorative rules) ── */
    .section-heading {
        font-size: 1.35rem;
        font-weight: 700;
        color: #202124;
        margin: 34px 0 16px 0;
        display: flex;
        align-items: center;
        letter-spacing: -0.01em;
    }

    /* ── Pipeline Stepper (Single horizontal connected strip) ── */
    .pipeline-stepper {
        display: flex;
        align-items: center;
        background: #FFFFFF;
        border-radius: 10px;
        padding: 18px 22px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        border: 1px solid #E8EAED;
        margin-bottom: 8px;
    }
    .step {
        text-align: center;
        flex: 1;
        padding: 0 8px;
    }
    .step-name {
        font-size: 0.82rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #5F6368;
        margin-bottom: 4px;
    }
    .step-count {
        font-size: 1.65rem;
        font-weight: 600;
        color: #202124;
        line-height: 1.1;
    }
    .step-label {
        font-size: 0.8rem;
        color: #80868B;
        margin-top: 3px;
    }
    .step-arrow {
        color: #BDBDBD;
        font-size: 1.15rem;
        flex-shrink: 0;
        padding: 0 4px;
        user-select: none;
    }
    .pipeline-ok {
        display: inline-flex;
        align-items: center;
        gap: 5px;
        background: #E6F4EA;
        border: 1px solid #34A853;
        border-radius: 20px;
        padding: 3px 12px;
        font-size: 0.8rem;
        color: #137333;
        font-weight: 600;
        margin-left: 10px;
    }

    /* ── Hero KPI (Primary failure mode) ── */
    .hero-stat-wrap {
        background: #FFFFFF;
        border-radius: 12px;
        padding: 24px 28px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        border: 1px solid #E8EAED;
        margin-bottom: 12px;
    }
    .hero-stat-label {
        font-size: 0.82rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #5F6368;
        margin-bottom: 6px;
    }
    .hero-stat {
        font-size: 2rem;
        font-weight: 700;
        color: #4285F4;
        line-height: 1.05;
    }
    .hero-stat-desc {
        font-size: 1.05rem;
        color: #3C4043;
        margin-top: 8px;
        font-weight: 400;
        line-height: 1.6;
    }

    /* ── Secondary Stat Cards ── */
    .stat-card {
        background: #FFFFFF;
        border-radius: 12px;
        padding: 18px 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        border: 1px solid #E8EAED;
    }
    .stat-label {
        font-size: 0.82rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #5F6368;
        margin-bottom: 6px;
    }
    .stat-value {
        font-size: 2rem;
        font-weight: 600;
        color: #202124;
        line-height: 1;
    }
    .stat-sub {
        font-size: 0.88rem;
        color: #80868B;
        margin-top: 5px;
    }

    /* ── Editorial Lead ── */
    .editorial-lead {
        font-size: 1.08rem;
        line-height: 1.7;
        color: #3C4043;
        max-width: 1100px;
        margin: 20px 0 24px 0;
        font-weight: 400;
    }

    /* ── Cluster Cards ── */
    .cluster-card {
        background: #FFFFFF;
        border: 1px solid #E8EAED;
        border-radius: 12px;
        padding: 22px 26px 20px;
        margin-bottom: 14px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
        transition: box-shadow 0.18s, border-color 0.18s;
    }
    .cluster-card:hover {
        border-color: #A8C7FA;
        box-shadow: 0 2px 8px rgba(26,115,232,0.08);
    }
    .cluster-number {
        font-size: 0.82rem;
        color: #4285F4;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.09em;
        margin-bottom: 6px;
    }
    .cluster-question {
        font-size: 1.25rem;
        font-weight: 700;
        color: #202124;
        margin-bottom: 10px;
        line-height: 1.45;
    }
    .cluster-finding {
        color: #3C4043;
        font-size: 1.05rem;
        line-height: 1.6;
        margin-bottom: 6px;
    }
    .badge-row {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 8px;
        margin-bottom: 10px;
    }

    /* Evidence strength badges */
    .badge-strong {
        display: inline-flex; align-items: center; gap: 4px;
        background: #E6F4EA;
        border: 1px solid #34A853;
        border-radius: 20px;
        padding: 4px 12px;
        font-size: 0.8rem;
        color: #137333;
        font-weight: 600;
    }
    .badge-moderate {
        display: inline-flex; align-items: center; gap: 4px;
        background: #FEF7E0;
        border: 1px solid #FBBC04;
        border-radius: 20px;
        padding: 4px 12px;
        font-size: 0.8rem;
        color: #7A5100;
        font-weight: 600;
    }
    .badge-limited {
        display: inline-flex; align-items: center; gap: 4px;
        background: #FCE8E6;
        border: 1px solid #EA4335;
        border-radius: 20px;
        padding: 4px 12px;
        font-size: 0.8rem;
        color: #C5221F;
        font-weight: 600;
    }
    /* n-items cluster counter */
    .badge-cluster-n {
        display: inline-block;
        background: #E8F0FE;
        border: 1px solid #4285F4;
        border-radius: 20px;
        padding: 4px 12px;
        font-size: 0.8rem;
        color: #4285F4;
        font-weight: 600;
    }

    /* ── Quote Cards ── */
    .quote-card {
        background: #F8F9FA;
        border-left: 3px solid #4285F4;
        border-radius: 0 8px 8px 0;
        padding: 12px 18px;
        margin: 10px 0;
        font-style: italic;
        color: #3C4043;
        font-size: 1.0rem;
        line-height: 1.65;
    }
    .quote-meta {
        font-style: normal;
        font-size: 0.84rem;
        color: #80868B;
        margin-top: 6px;
    }
    .quote-meta code {
        background: #F1F3F4;
        color: #3C4043;
        border-radius: 4px;
        padding: 1px 4px;
        font-size: 0.78rem;
    }

    /* ── Q&A answer box ── */
    .answer-box {
        background: #F8F9FA;
        border: 1px solid #E8EAED;
        border-radius: 10px;
        padding: 20px 24px;
        margin-top: 12px;
        color: #202124;
        font-size: 1.02rem;
        line-height: 1.6;
    }
    .answer-box p {
        color: #202124 !important;
        font-size: 1.02rem !important;
    }

    /* ── Methodology / Provenance Footer Card ── */
    .provenance-card {
        background: #FFFFFF;
        border: 1px solid #E8EAED;
        border-radius: 12px;
        padding: 26px 28px 22px;
        margin-top: 36px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    .provenance-title {
        font-size: 1.25rem;
        font-weight: 700;
        color: #202124;
        margin-bottom: 4px;
    }
    .provenance-subtitle {
        font-size: 0.95rem;
        color: #5F6368;
        margin-bottom: 18px;
    }
    .source-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
        gap: 12px !important;
        margin-bottom: 22px !important;
    }
    @media (max-width: 900px) {
        .source-grid { grid-template-columns: 1fr !important; }
    }
    .source-item-card {
        background: #F8F9FA !important;
        border: 1px solid #E8EAED !important;
        border-radius: 8px !important;
        padding: 14px 16px !important;
        display: flex !important;
        flex-direction: column !important;
        justify-content: space-between !important;
        min-width: 0 !important;
    }
    .source-item-name {
        font-size: 0.94rem !important;
        font-weight: 700 !important;
        color: #202124 !important;
        margin-bottom: 8px !important;
    }
    .source-item-counts {
        font-size: 0.88rem !important;
        color: #5F6368 !important;
        display: flex !important;
        justify-content: space-between !important;
        align-items: center !important;
        gap: 6px !important;
    }
    .source-item-counts strong {
        color: #202124 !important;
    }
    .source-item-rate {
        display: inline-block !important;
        background: #E8F0FE !important;
        color: #1A73E8 !important;
        font-weight: 600 !important;
        font-size: 0.8rem !important;
        padding: 2px 8px !important;
        border-radius: 12px !important;
    }
    .provenance-meta-list {
        border-top: 1px solid #E8EAED !important;
        padding-top: 18px !important;
        display: grid !important;
        grid-template-columns: 1fr 1fr !important;
        gap: 14px 28px !important;
        font-size: 0.94rem !important;
        color: #3C4043 !important;
    }
    @media (max-width: 800px) {
        .provenance-meta-list { grid-template-columns: 1fr !important; }
    }
    .provenance-meta-row strong {
        color: #202124 !important;
        display: block !important;
        font-size: 0.82rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.07em !important;
        margin-bottom: 3px !important;
    }

    /* ── Streamlit element overrides ── */

    /* Buttons — Google Blue accent, multi-line wrapping */
    .stButton > button {
        background: #E8F0FE !important;
        border: 1px solid #4285F4 !important;
        color: #4285F4 !important;
        border-radius: 8px !important;
        font-weight: 500 !important;
        font-size: 0.96rem !important;
        line-height: 1.45 !important;
        white-space: normal !important;
        word-wrap: break-word !important;
        height: auto !important;
        min-height: 52px !important;
        padding: 10px 16px !important;
        text-align: left !important;
        display: flex !important;
        align-items: center !important;
        justify-content: flex-start !important;
        transition: all 0.15s !important;
        box-shadow: none !important;
    }
    .stButton > button div,
    .stButton > button p {
        white-space: normal !important;
        word-break: break-word !important;
        text-align: left !important;
        line-height: 1.45 !important;
        font-size: 0.95rem !important;
        margin: 0 !important;
    }
    .stButton > button:hover {
        background: #D2E3FC !important;
        border-color: #4285F4 !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 2px 6px rgba(66,133,244,0.18) !important;
    }
    .stButton > button[kind="primary"] {
        background: #4285F4 !important;
        border-color: #4285F4 !important;
        color: #FFFFFF !important;
        justify-content: center !important;
        text-align: center !important;
        min-height: 44px !important;
    }
    .stButton > button[kind="primary"] p {
        text-align: center !important;
        color: #FFFFFF !important;
    }
    .stButton > button[kind="primary"]:hover {
        background: #3367D6 !important;
        border-color: #3367D6 !important;
    }

    /* Expanders */
    div[data-testid="stExpander"] {
        background: #FFFFFF !important;
        border: 1px solid #E8EAED !important;
        border-radius: 10px !important;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04) !important;
    }
    div[data-testid="stExpander"] summary p,
    div[data-testid="stExpander"] summary span {
        color: #202124 !important;
        font-weight: 500 !important;
    }

    /* Selectbox & text input labels */
    [data-testid="stSelectbox"] label,
    [data-testid="stTextInput"] label {
        color: #5F6368 !important;
        font-size: 0.85rem !important;
    }
    /* Input fields */
    [data-testid="stTextInput"] input,
    [data-testid="stSelectbox"] > div {
        background: #FFFFFF !important;
        color: #202124 !important;
        border-color: #DADCE0 !important;
    }

    /* Radio buttons */
    [data-testid="stRadio"] label p {
        color: #3C4043 !important;
    }

    /* DataFrame table */
    [data-testid="stDataFrame"] {
        border: 1px solid #E8EAED !important;
        border-radius: 8px !important;
    }

    /* Captions */
    [data-testid="stCaptionContainer"] p {
        color: #5F6368 !important;
    }

    /* Spinner */
    [data-testid="stSpinner"] > div {
        color: #5F6368 !important;
    }

    /* Alert / warning / info boxes */
    [data-testid="stAlert"] {
        border-radius: 8px !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ===========================================================================
# DATA LOADING (cached)
# ===========================================================================

@st.cache_data
def load_core_data() -> tuple[dict, dict, list[dict]]:
    """Load crosstabs JSON, findings JSON, and all tagged items from SQLite."""
    crosstabs: dict = {}
    if CROSSTABS_PATH.exists():
        crosstabs = json.loads(CROSSTABS_PATH.read_text(encoding="utf-8"))

    findings: dict = {}
    if FINDINGS_PATH.exists():
        findings = json.loads(FINDINGS_PATH.read_text(encoding="utf-8"))

    db_items = load_tagged_items(DB_PATH)
    return crosstabs, findings, db_items


@st.cache_data
def get_pipeline_counts() -> dict[str, Any]:
    """
    Compute live pipeline stage counts.
    - Collect: item count in the latest raw JSON file (sorted alphabetically → newest timestamp)
    - Tag / Store: row count in tagged_items table (all rows, not just relevant)
    - Aggregate: number of matrix keys in crosstabs.json
    - Derive Clusters: number of entries in findings["derived_clusters"]
    """
    counts: dict[str, Any] = {
        "collect": 0,
        "tag": 0,
        "store": 0,
        "aggregate": 0,
        "clusters": 0,
    }

    # Collect — cumulative unique items across all raw collection runs
    raw_files = sorted(RAW_DATA_DIR.glob("collected_*.json"))
    unique_ids = set()
    for f in raw_files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        iid = item.get("item_id") or item.get("id")
                        if iid:
                            unique_ids.add(iid)
        except Exception:
            pass
    counts["collect"] = len(unique_ids) if unique_ids else 0
    if counts["tag"] > 0 and counts["collect"] < counts["tag"]:
        counts["collect"] = counts["tag"]

    # Tag / Store — DB row count (all items, not just relevant)
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM tagged_items")
            counts["tag"] = cur.fetchone()[0]
            counts["store"] = counts["tag"]
            conn.close()
        except Exception:
            counts["tag"] = 0
            counts["store"] = 0

    # Aggregate — matrix keys in crosstabs.json
    if CROSSTABS_PATH.exists():
        try:
            ct = json.loads(CROSSTABS_PATH.read_text(encoding="utf-8"))
            counts["aggregate"] = len([k for k in ct.keys() if k.startswith("matrix_")])
        except Exception:
            counts["aggregate"] = 0

    # Derive Clusters
    if FINDINGS_PATH.exists():
        try:
            fi = json.loads(FINDINGS_PATH.read_text(encoding="utf-8"))
            counts["clusters"] = len(fi.get("derived_clusters", []))
        except Exception:
            counts["clusters"] = 0

    return counts


def get_evidence_badge(frequency: int) -> str:
    """Return HTML badge string based on frequency count."""
    if frequency >= 20:
        return '<span class="badge-strong">🟢 Strong evidence</span>'
    elif frequency >= 8:
        return '<span class="badge-moderate">🟡 Moderate evidence</span>'
    else:
        return '<span class="badge-limited">🔴 Limited evidence — small sample</span>'


def load_all_db_rows() -> list[dict]:
    """Load ALL rows from tagged_items (including irrelevant) for the data explorer."""
    if not DB_PATH.exists():
        return []
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, item_id, source, raw_text, date, rating,
                   is_relevant, photo_type, memory_cues_retained,
                   memory_cues_missing, failure_stage, workaround,
                   representative_quote, tagged_at
            FROM tagged_items
            ORDER BY id ASC
            """
        )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception:
        return []


# ===========================================================================
# LOAD DATA
# ===========================================================================
crosstabs, findings, db_items = load_core_data()
pipeline_counts = get_pipeline_counts()
clusters: list[dict] = findings.get("derived_clusters", [])
methodology = findings.get("methodological_notes", {})
source_breakdown: list[dict] = findings.get("source_breakdown", [])

# Sidebar — API key & quick links only
with st.sidebar:
    st.markdown("### ⚙️ Q&A Configuration")
    api_key_input = st.text_input(
        "Groq API Key (Optional)",
        type="password",
        help="Supply your own free Groq key (gsk_...) if the shared key hits rate limits.",
    )
    effective_api_key: Optional[str] = api_key_input.strip() if api_key_input.strip() else os.getenv("GROQ_API_KEY")
    if api_key_input.strip():
        st.caption("✅ Using your custom Groq API key")
    elif effective_api_key:
        st.caption("✅ Using pre-configured project key")
    else:
        st.caption("⚠️ No Groq API key — Q&A synthesis unavailable")
    st.markdown("---")
    st.caption(
        "**Discovery Engine · Phase 5**  \n"
        "Single-scroll redesign · 2026-09-23  \n"
        "RAG over SQLite tagged corpus  \n"
        "LLM: Groq llama-3.3-70b-versatile"
    )


# Derive values from live data
corpus_total = methodology.get("corpus_size", findings.get("total_relevant_items", "—"))
relevant_total = findings.get("total_relevant_items", "—")
corpus_total_str = f"{corpus_total:,}" if isinstance(corpus_total, int) else str(corpus_total)

# Primary failure mode — cluster 1 (query_returned_nothing)
cluster_1 = next(
    (c for c in clusters if c["cluster_id"] == "cluster_1_query_returned_nothing"), None
)
primary_failure_pct = f"{cluster_1['percentage_of_relevant']}%" if cluster_1 and cluster_1.get("percentage_of_relevant") else "—"
primary_failure_subtext = f"Zero-Yield ({cluster_1['frequency']} / {relevant_total} items)" if cluster_1 else "Zero-Yield"

# Search abandonment — cluster 5 (search_abandonment_and_manual_scrolling)
cluster_5 = next(
    (c for c in clusters if c["cluster_id"] == "cluster_5_search_abandonment_and_manual_scrolling"), None
)
# Parse "79 / 89 users (88.8%)" from primary_metric string
abandonment_pct = "—"
abandonment_subtext = "No workaround recorded"
if cluster_5:
    import re as _re
    m = _re.search(r"\((\d+\.?\d*)%\)", cluster_5.get("primary_metric", ""))
    if m:
        abandonment_pct = f"{m.group(1)}%"
    m2 = _re.search(r"(\d+)\s*/\s*(\d+)\s*users", cluster_5.get("primary_metric", ""))
    if m2:
        abandonment_subtext = f"No workaround ({m2.group(1)} / {m2.group(2)} users)"


# ===========================================================================
# SECTION 0 — HEADER
# ===========================================================================
logo_b64 = get_google_photos_logo_b64()
logo_html = (
    f'<img src="data:image/png;base64,{logo_b64}" alt="Google Photos" class="google-photos-logo">'
    if logo_b64
    else ""
)

st.markdown(
    f"""
    <div class="hero-header">
        <div class="hero-logo-row">
            {logo_html}
            <div class="hero-title"><span style="color: #FBBC04;">Google</span> <span style="color: #EA4335;">Photos</span> <span style="color: #4285F4;">Discovery</span> <span style="color: #34A853;">Engine</span></div>
        </div>
        <p class="hero-subtitle">
           <h3> AI-powered analysis of public feedback uncovering why users fail to retrieve photos they remember vaguely. </h3>
            This engine analysed {corpus_total_str} pieces of public feedback about Google Photos
    across six platforms, tagging each to identify where and why searches for a
    remembered-but-vague photo actually fail. The clearest pattern: most searches don't
    return the wrong result — they return nothing at all.
        </p>
       
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f"""
    <p class="editorial-lead">
   
    </p>
    """,
    unsafe_allow_html=True,
)


# ===========================================================================
# SECTION 1 — PIPELINE STATUS STRIP
# ===========================================================================
st.markdown(
    '<div class="section-heading">Pipeline Flow &nbsp;',
    unsafe_allow_html=True,
)

pc = pipeline_counts
st.markdown(
    f"""
    <div class="pipeline-stepper">
        <div class="step">
            <div class="step-name">Collect</div>
            <div class="step-count">{pc["collect"]:,}</div>
            <div class="step-label">raw items collected</div>
        </div>
        <div class="step-arrow">→</div>
        <div class="step">
            <div class="step-name">Tag</div>
            <div class="step-count">{pc["tag"]:,}</div>
            <div class="step-label">items AI-tagged</div>
        </div>
        <div class="step-arrow">→</div>
        <div class="step">
            <div class="step-name">Store</div>
            <div class="step-count">{pc["store"]:,}</div>
            <div class="step-label">rows in SQLite DB</div>
        </div>
        <div class="step-arrow">→</div>
        <div class="step">
            <div class="step-name">Aggregate</div>
            <div class="step-count">{pc["aggregate"]}</div>
            <div class="step-label">cross-tab matrices</div>
        </div>
        <div class="step-arrow">→</div>
        <div class="step">
            <div class="step-name">Derive Clusters</div>
            <div class="step-count">{pc["clusters"]}</div>
            <div class="step-label">opportunity clusters</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ===========================================================================
# SECTION 2 — KPI BANNER (data-driven)
# ===========================================================================
st.markdown(
    '<div class="section-heading">Research KPIs</div>',
    unsafe_allow_html=True,
)

# Secondary stats row (placed first)
s1, s2, s3 = st.columns(3)
secondary_kpis = [
    (s1, "Total corpus analyzed",  corpus_total_str, "Across 6 public sources"),
    (s2, "Verified relevant cases", str(relevant_total), "Vague retrieval struggles"),
    (s3, "Search abandonment rate", abandonment_pct, abandonment_subtext),
]

for col, label, value, subtext in secondary_kpis:
    with col:
        st.markdown(
            f"""
            <div class="stat-card">
                <div class="stat-label">{label}</div>
                <div class="stat-value">{value}</div>
                <div class="stat-sub">{subtext}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

# Hero stat — Primary Failure Mode (placed below 3-stat row)
st.markdown(
    f"""
    <div class="hero-stat-wrap" style="margin-top: 14px;">
        <div class="hero-stat-label">Primary failure mode</div>
        <div class="hero-stat">{primary_failure_pct}</div>
        <div class="hero-stat-desc">Over half of all vague-memory searches return zero results — the search engine finds nothing, not the wrong thing. ({primary_failure_subtext})</div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ===========================================================================
# SECTION 3+4 — RESEARCH QUESTION CARDS WITH CONFIDENCE BADGES
# ===========================================================================
st.markdown(
    '<div class="section-heading">Research findings</div>',
    unsafe_allow_html=True,
)
st.caption(
    "Clusters derived algorithmically from ranked cross-tabulation cell counts — "
    "not pre-defined narratives. Each card links a question-framed finding to its "
    "supporting evidence and confidence level."
)

CLUSTER_MERGED_FINDINGS: dict[str, str] = {
    "cluster_1_query_returned_nothing": (
        "47 / 89 relevant items (52.8% of retrieval failures) — Matrix 1, top-ranked cell."
    ),
    "cluster_2_rough_time_vs_exact_date_album": (
        "63 pairwise associations with rough temporal cues (16 missing album, 15 missing exact date) — Matrix 4, ranks #2 & #3."
    ),
    "cluster_3_query_formulation_barrier": (
        "17 / 89 relevant items (19.1% of retrieval failures) — Matrix 1, cell rank #3."
    ),
    "cluster_4_person_face_grouping_misidentification": (
        "7 / 12 person-focused searches fail at recognition (58.3%) — Matrix 1, cell rank #6."
    ),
    "cluster_5_search_abandonment_and_manual_scrolling": (
        "79 / 89 users (88.8%) had no workaround; 7 resorted to manual timeline scrolling — Matrix 3."
    ),
}

for idx, cl in enumerate(clusters, 1):
    cluster_id = cl.get("cluster_id", "")
    question = CLUSTER_QUESTIONS.get(cluster_id, cl.get("title", "Unknown cluster"))
    frequency = cl.get("frequency", 0)
    evidence_badge = get_evidence_badge(frequency)
    finding_text = CLUSTER_MERGED_FINDINGS.get(
        cluster_id, cl.get("what_the_data_shows", cl.get("primary_metric", ""))
    )
    behavioral_gap = cl.get("behavioral_gap", "")
    quotes: list[dict] = cl.get("supporting_quotes", [])

    st.markdown(
        f"""
        <div class="cluster-card">
            <div class="cluster-number">Cluster {idx}</div>
            <div class="cluster-question">{question}</div>
            <div class="badge-row">
                {evidence_badge}
                <span class="badge-cluster-n">{frequency} items</span>
            </div>
            <div class="cluster-finding">{finding_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("Show supporting evidence", expanded=False):
        if behavioral_gap:
            st.markdown(
                f"**Behavioral Gap:** {behavioral_gap}",
            )
            st.markdown("---")

        st.markdown("**Representative Quotes:**")
        for q in quotes[:3]:
            source_label = q.get("source", "unknown").replace("_", " ").title()
            item_id = q.get("item_id", "")
            quote_text = q.get("quote", "")
            st.markdown(
                f"""
                <div class="quote-card">
                    "{quote_text}"
                    <div class="quote-meta">
                        <strong>{source_label}</strong> · ID: <code>{item_id}</code>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        extra = frequency - 3
        if extra > 0:
            st.caption(
                f"*+{extra} more items in this cluster — explore them in the Full Data Explorer below.*"
            )


# ===========================================================================
# SECTION 5 — ASK THE DATA
# ===========================================================================
st.markdown(
    '<div class="section-heading">Ask the data</div>',
    unsafe_allow_html=True,
)
st.caption(
    "Retrieval-augmented synthesis over the 89 verified relevant items in the tagged SQLite corpus. "
    "All answers are cited with exact item IDs. Powered by **Groq llama-3.3-70b-versatile** (free tier)."
)

# Preset question buttons
PRESET_QUESTIONS = [
    "Why do document and receipt photo searches fail differently from travel photo searches?",
    "What workarounds do users attempt when Google Photos search fails?",
    "Which sources report the most search failures and what patterns distinguish them?",
    "How does rough temporal memory (e.g. 'about 3 years ago') conflict with the way Google Photos organizes photos?",
    "Why does face and person search fail for users looking for family members?",
]

st.markdown("**One-click questions:**")

# Preset question buttons — rendered in 2-column rows with multi-line wrapping
for row_start in range(0, len(PRESET_QUESTIONS), 2):
    pair = PRESET_QUESTIONS[row_start : row_start + 2]
    cols = st.columns(2)
    for c_i, q in enumerate(pair):
        btn_idx = row_start + c_i
        if cols[c_i].button(q, key=f"preset_btn_{btn_idx}", use_container_width=True):
            st.session_state["qa_text_input"] = q

st.markdown(
    "<div style='font-size:0.92rem;color:#5F6368;margin:14px 0 6px;font-weight:600;'>Or ask your own question:</div>",
    unsafe_allow_html=True,
)

user_query_input = st.text_input(
    label="Custom question",
    label_visibility="collapsed",
    placeholder="e.g. Why do users who remember a person's face still fail to find the photo?",
    key="qa_text_input",
)

run_qa = st.button("Generate Cited Research Answer", type="primary")

if run_qa and user_query_input.strip():
    with st.spinner("Retrieving relevant feedback and synthesizing cited answer via Groq…"):
        response = ask_grounded_qa(
            query=user_query_input.strip(),
            items=db_items,
            api_key=effective_api_key,
            top_k=6,
        )

    st.markdown(
        '<div class="answer-box">',
        unsafe_allow_html=True,
    )
    st.markdown(f"**Question:** _{response['query']}_")
    st.markdown("---")
    st.markdown(response["answer"])
    st.markdown("</div>", unsafe_allow_html=True)

    evidence = response.get("evidence", [])
    with st.expander(f"🔍 Evidence used — {len(evidence)} corpus items retrieved", expanded=False):
        for ev in evidence:
            st.markdown(
                f"**{ev['citation_label']}** — *{ev['source']}*"
                f"{'  ⭐ ' + str(ev['rating']) + '/5' if ev.get('rating') else ''}"
            )
            cols = st.columns([1, 1, 1])
            cols[0].caption(f"Photo type: `{ev['photo_type']}`")
            cols[1].caption(f"Failure: `{ev['failure_stage']}`")
            cols[2].caption(f"Workaround: `{ev['workaround']}`")
            st.markdown(f"> *\"{ev['quote']}\"*")
            if ev.get("raw_text"):
                st.caption(f"Raw text: {ev['raw_text'][:200]}…")
            st.markdown("---")

elif run_qa and not user_query_input.strip():
    st.warning("Please enter a question before generating an answer.")


# ===========================================================================
# SECTION 6 — FULL DATA EXPLORER (collapsed by default)
# ===========================================================================

with st.expander("🔍 Explore the Full Dataset", expanded=True):
    st.markdown(
        "Browse and filter the complete tagged corpus — including non-relevant items — and explore "
        "the 4 cross-tabulation matrices."
    )

    # ── Corpus Browser ──────────────────────────────────────────────────────
    st.subheader("Raw Reviews Analyser")

    # Filters — fresh query on change (not cached)
    all_rows = load_all_db_rows()
    f1, f2, f3 = st.columns([1, 2, 1])
    with f1:
        all_sources_raw = sorted({r["source"] for r in all_rows if r.get("source")})
        source_sel = st.selectbox("Source", ["All"] + all_sources_raw, key="explorer_source")
    with f2:
        text_search = st.text_input("Text search (searches raw_text + quote)", key="explorer_text", placeholder="e.g. receipt, face, scroll…")
    with f3:
        row_limit = st.selectbox("Show rows", [25, 50, 100, 250, 500], index=1, key="explorer_limit")

    # Apply filters (no cache — triggered by widget state change)
    filtered = all_rows
    if source_sel != "All":
        filtered = [r for r in filtered if r.get("source") == source_sel]
    if text_search.strip():
        q_lower = text_search.strip().lower()
        filtered = [
            r for r in filtered
            if q_lower in (r.get("raw_text") or "").lower()
            or q_lower in (r.get("representative_quote") or "").lower()
        ]

    st.caption(f"Showing **{min(len(filtered), row_limit)}** of **{len(filtered)}** matching rows (total in DB: {len(all_rows)})")

    if filtered:
        display_rows = []
        for r in filtered[:row_limit]:
            display_rows.append({
                "source": r.get("source", ""),
                "rating": r.get("rating", ""),
                "date": (r.get("date") or "")[:10],
                "text": (r.get("raw_text") or "")[:120] + ("…" if len(r.get("raw_text") or "") > 120 else ""),
                "is_relevant": "✅" if r.get("is_relevant") else "—",
                "photo_type": r.get("photo_type") or "",
                "failure_stage": r.get("failure_stage") or "",
                "workaround": r.get("workaround") or "",
                "quote": (r.get("representative_quote") or "")[:80],
            })
        df_explorer = pd.DataFrame(display_rows)
        st.dataframe(df_explorer, use_container_width=True, height=400)
    else:
        st.info("No rows match the current filters.")

    # ── Cross-Tab Matrices ───────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Cross-Tabulation Matrices")
    st.caption(
        "4 relational matrices computed across all 89 verified relevant items. "
        "Select a matrix to view the heatmap and drill down to authentic user quotes."
    )

    MATRIX_OPTIONS = {
        "Matrix 1: Failure Stage × Photo Type": "matrix_1_failure_stage_x_photo_type",
        "Matrix 2: Memory Cues Missing × Photo Type": "matrix_2_memory_cues_missing_x_photo_type",
        "Matrix 3: Failure Stage × Workaround": "matrix_3_failure_stage_x_workaround",
        "Matrix 4: Memory Cues Retained × Memory Cues Missing": "matrix_4_memory_cues_retained_x_memory_cues_missing",
    }

    matrix_choice = st.radio(
        "Select Matrix:",
        list(MATRIX_OPTIONS.keys()),
        horizontal=True,
        key="matrix_radio",
    )
    selected_key = MATRIX_OPTIONS[matrix_choice]
    m_data = crosstabs.get(selected_key, {})

    if m_data and "grid" in m_data:
        df_grid = pd.DataFrame.from_dict(m_data["grid"], orient="index")
        df_grid["TOTAL"] = df_grid.sum(axis=1)
        totals_row = df_grid.sum(axis=0)
        totals_row.name = "TOTAL"
        df_display = pd.concat([df_grid, totals_row.to_frame().T])

        non_total_cols = [c for c in df_grid.columns if c != "TOTAL"]
        try:
            styled = df_display.style.background_gradient(
                cmap="Blues",
                subset=pd.IndexSlice[df_grid.index, non_total_cols],
            )
            st.dataframe(styled, use_container_width=True, height=320)
        except Exception:
            st.dataframe(df_display, use_container_width=True, height=320)

        # Quote drill-down
        st.markdown("**Verbatim Quote Drill-Down**")
        dc1, dc2, dc3 = st.columns(3)
        with dc1:
            ds_list = ["All"] + sorted({it["source"] for it in db_items})
            ds_src = st.selectbox("Filter by Source", ds_list, key="drill_source")
        with dc2:
            ds_stage = st.selectbox(
                "Filter by Failure Stage",
                ["All"] + sorted({it["failure_stage"] for it in db_items}),
                key="drill_stage",
            )
        with dc3:
            ds_type = st.selectbox(
                "Filter by Photo Type",
                ["All"] + sorted({it["photo_type"] for it in db_items}),
                key="drill_type",
            )

        drill_items = [
            it for it in db_items
            if (ds_src == "All" or it["source"] == ds_src)
            and (ds_stage == "All" or it["failure_stage"] == ds_stage)
            and (ds_type == "All" or it["photo_type"] == ds_type)
        ]
        st.caption(f"Showing **{min(len(drill_items), 10)}** of **{len(drill_items)}** matching quotes")
        for it in drill_items[:10]:
            rating_str = f" ⭐ {it['rating']}/5" if it.get("rating") else ""
            date_str = f" · {it['date'][:10]}" if it.get("date") else ""
            quote_text = it["quote"] if len(it["quote"]) > 10 else (it["raw_text"][:160] + "…")
            st.markdown(
                f"""
                <div class="quote-card">
                    "{quote_text}"
                    <div class="quote-meta">
                        <strong>{it['citation_label']}</strong> ({it['source']}){rating_str}{date_str}
                        &nbsp;|&nbsp; <code>photo_type: {it['photo_type']}</code>
                        &nbsp;|&nbsp; <code>failure: {it['failure_stage']}</code>
                        &nbsp;|&nbsp; <code>workaround: {it['workaround']}</code>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        if len(drill_items) > 10:
            st.caption(f"*Showing first 10 of {len(drill_items)} matching items.*")
    else:
        st.warning("No cross-tabulation data found. Please run `pipeline/aggregate.py` first.")


# ===========================================================================
# SECTION 7 — METHODOLOGY FOOTER
# ===========================================================================
source_cards_list = []
for s in source_breakdown:
    display_name = s.get("display_name", s.get("source", "")).replace(" Reviews", "")
    total_coll = s.get("total_collected", 0)
    total_rel = s.get("total_relevant", 0)
    rel_rate = s.get("relevance_rate", "—")
    source_cards_list.append(
        f'<div class="source-item-card">'
        f'<div class="source-item-name">{display_name}</div>'
        f'<div class="source-item-counts">'
        f'<span><strong>{total_coll:,}</strong> collected</span>'
        f'<span><strong>{total_rel}</strong> relevant</span>'
        f'<span class="source-item-rate">{rel_rate}</span>'
        f'</div>'
        f'</div>'
    )
source_cards_html = "".join(source_cards_list)

tagging_model = methodology.get("tagging_model", "Groq llama-3.3-70b-versatile (free tier, JSON mode)")
corpus_note = (
    f"{methodology.get('corpus_size', '—'):,} total items tagged · "
    f"{methodology.get('relevant_corpus_size', '—')} relevant ({methodology.get('relevance_percentage', '—')})"
    if isinstance(methodology.get("corpus_size"), int)
    else "See findings.json for full counts."
)

provenance_html = (
    '<div class="provenance-card">'
    '<div class="provenance-title">Corpus Breakdown &amp; Pipeline Provenance</div>'
    '<div class="provenance-subtitle">Audited distribution of public feedback items collected across 6 primary channels.</div>'
    f'<div class="source-grid">{source_cards_html}</div>'
    '<div class="provenance-meta-list">'
    f'<div class="provenance-meta-row"><strong>Analyzed Corpus</strong><span>{corpus_note}</span></div>'
    f'<div class="provenance-meta-row"><strong>Tagging Model</strong><span>{tagging_model}</span></div>'
    '<div class="provenance-meta-row"><strong>Q&amp;A Synthesis Model</strong><span>Groq llama-3.3-70b-versatile via OpenAI-compatible API</span></div>'
    '<div class="provenance-meta-row"><strong>Pipeline Architecture</strong><span>Collection &rarr; AI Tagging &rarr; SQLite Storage &rarr; Aggregation &rarr; Cluster Derivation &rarr; Interface</span></div>'
    '</div>'

    '</div>'
)

st.markdown(provenance_html, unsafe_allow_html=True)
