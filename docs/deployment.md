# Deployment Guide — Streamlit Community Cloud

This guide provides instructions for deploying the **Google Photos Discovery Engine** dashboard to **Streamlit Community Cloud** so evaluators and mentors can access and interact with the findings.

---

## 1. Prerequisites

1. **GitHub Repository:** Ensure this codebase is pushed to a GitHub repository (e.g. `your-username/google-photos-discovery-engine`).
2. **Streamlit Account:** Free account at [share.streamlit.io](https://share.streamlit.io).
3. **Groq API Key:** A free API key from [console.groq.com](https://console.groq.com) (free tier, 14,400 req/day).

---

## 2. One-Click Deployment Steps

1. Log in to [Streamlit Community Cloud](https://share.streamlit.io).
2. Click **"Create app"** (or **"New app"**).
3. Connect your GitHub account and select your repository:
   - **Repository:** `your-username/google-photos-discovery-engine`
   - **Branch:** `main`
   - **Main file path:** `app.py` (or `discovery-engine/app.py`)
   - **App URL:** (Optional custom subdomain, e.g. `google-photos-discovery-engine`)

4. Click **"Advanced settings..."** before deploying:
   - **Python version:** `3.12` (or `3.11`)
   - **Secrets (TOML format):**
     ```toml
     GROQ_API_KEY = "gsk_your_groq_api_key_here"
     ```
   *(Note: The app also allows evaluators to input their own Groq key directly in the sidebar if needed).*

5. Click **"Deploy!"**.
   Streamlit will automatically install dependencies from `discovery-engine/requirements.txt` and launch the app.

---

## 3. Local Verification

To run the application locally in Windows PowerShell:

```powershell
# Navigate to the discovery engine directory
cd "c:\AI Discovery Engine\discovery-engine"

# Run Streamlit using the virtual environment
.\venv\Scripts\streamlit.exe run app.py
```

Or run from the workspace root:

```powershell
cd "c:\AI Discovery Engine"
.\discovery-engine\venv\Scripts\streamlit.exe run app.py
```

The browser will open at `http://localhost:8501`.

---

## 4. Evaluator Feature Checklist

When evaluators review the deployment, verify the following three primary views:

1. **📊 Cross-Tab Exploration View:**
   - [x] Switch between all 4 cross-tab matrices using the radio selector.
   - [x] Inspect cell counts and background heat gradient.
   - [x] Use filters (Source, Failure Stage, Photo Type) to view verbatim quotes with rating and platform tags.
   - [x] Expand "View raw feedback text" to verify authenticity.

2. **🎯 Derived Opportunity Clusters View:**
   - [x] Review the 5 algorithmically derived failure clusters.
   - [x] Verify metric percentages and "The Behavioral Gap" explanations.
   - [x] Review authentic user quotes and actionable PM product recommendations.

3. **💬 Cited Q&A Panel View:**
   - [x] Click preset questions (e.g. *Zero-Yield Failure*, *Face Recognition Issues*).
   - [x] Submit custom research questions.
   - [x] Verify that synthesized answers include inline bracket citations (e.g. `[Community #468729533:0]`, `[Reddit #1wi9thz]`).
   - [x] Expand "Inspect Grounded Evidence Items" to audit the exact source rows retrieved from SQLite.
