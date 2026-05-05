"""Auto Deck — single-page Streamlit test harness for the agentic pipeline."""

import io
import time

import pandas as pd
import requests
import streamlit as st

API = "http://127.0.0.1:8000"
V2 = f"{API}/api/v2/agent"

# (label, backend_chart_type) — only includes types known to ppt_agent._CHART_TYPE_lTO_PPT
CHART_TYPES = [
    ("Auto (AI decides)", None),
    ("Bar", "bar"),
    ("Grouped Bar", "grouped_bar"),
    ("Stacked Bar", "stacked_bar"),
    ("Horizontal Bar", "horizontal_bar"),
    ("Line (single)", "line"),
    ("Line (multi)", "multi_line"),
    ("Area", "area"),
    ("Pie", "pie"),
    ("Donut", "donut"),
    ("Combo (bar + line)", "combo"),
    ("Table", "table"),
]
CHART_LABEL_TO_KEY = dict(CHART_TYPES)

st.set_page_config(page_title="Auto Deck", page_icon="📊", layout="wide")

st.markdown("""
<style>
    .block-container { max-width: 1100px; padding-top: 2rem; }
    div[data-testid="stStatusWidget"] { display: none; }
</style>
""", unsafe_allow_html=True)

st.title("📊 Auto Deck — Agent Pipeline Tester")

# ── backend health indicator ─────────────────────────────────────────────────

try:
    _h = requests.get(f"{API}/health", timeout=2)
    if _h.status_code == 200:
        st.caption("✅ Backend connected")
    else:
        st.caption("⚠️ Backend returned non-200")
except Exception:
    st.error(f"❌ Backend not reachable at {API}")
    st.stop()

st.divider()

# ═════════════════════════════════════════════════════════════════════════════
# 1.  PROMPT / INTENT
# ═════════════════════════════════════════════════════════════════════════════

intent = st.text_area(
    "What should the presentation be about?",
    placeholder="e.g. Create a quarterly revenue breakdown by region with trend lines and key insights",
    height=90,
)

# ═════════════════════════════════════════════════════════════════════════════
# 2.  MULTI-FILE UPLOAD  +  PREVIEW
# ═════════════════════════════════════════════════════════════════════════════

st.subheader("Upload your data")
uploads = st.file_uploader(
    "Drop one or more CSV / Excel files",
    type=["csv", "xlsx"],
    accept_multiple_files=True,
)

primary_idx = 0
if uploads:
    tabs = st.tabs([f"📄 {f.name}" for f in uploads])
    for i, (tab, f) in enumerate(zip(tabs, uploads)):
        with tab:
            try:
                raw = f.getvalue()
                if f.name.endswith(".csv"):
                    df = pd.read_csv(io.BytesIO(raw))
                else:
                    df = pd.read_excel(io.BytesIO(raw))
                st.dataframe(df, use_container_width=True, height=240)
                st.caption(f"{len(df)} rows × {len(df.columns)} columns")
            except Exception as e:
                st.warning(f"Could not preview: {e}")

    if len(uploads) > 1:
        primary_idx = st.radio(
            "Primary data source (the pipeline uses ONE — the rest are uploaded for reference):",
            options=range(len(uploads)),
            format_func=lambda i: uploads[i].name,
            horizontal=True,
        )
    st.caption(f"➡️ Primary: **{uploads[primary_idx].name}**")

# ═════════════════════════════════════════════════════════════════════════════
# 3.  MULTI-CHART SELECT  +  OPTIONS
# ═════════════════════════════════════════════════════════════════════════════

st.subheader("Options")

col_left, col_right = st.columns([2, 1])

with col_left:
    chart_picks = st.multiselect(
        "Chart types — pick one or more (one per slide, in order)",
        options=[label for label, _ in CHART_TYPES],
        default=["Auto (AI decides)"],
        help="If you pick 3 charts, slide 1 uses the first, slide 2 uses the second, etc.",
    )
    if chart_picks:
        st.caption("Slide-to-chart mapping: " + " → ".join(
            f"**Slide {i+1}**: {label}" for i, label in enumerate(chart_picks)
        ))

with col_right:
    mode = st.selectbox("Pipeline mode", ["full", "structure_only", "skeleton", "ppt_only"])
    presentation_type = st.text_input("Presentation type", value="financial")
    dry_run = st.checkbox("Dry run (skip LLM)")

# ═════════════════════════════════════════════════════════════════════════════
# 4.  GENERATE
# ═════════════════════════════════════════════════════════════════════════════

st.divider()

if st.button("🚀 Generate Presentation", type="primary", use_container_width=True):
    if not intent.strip():
        st.warning("Please enter a prompt / intent first.")
        st.stop()

    # ── Step 1: upload all files ────────────────────────────────────────
    uploaded_meta: list[dict] = []
    if uploads:
        with st.spinner(f"Uploading {len(uploads)} file(s)…"):
            for f in uploads:
                f.seek(0)
                try:
                    r = requests.post(
                        f"{V2}/upload",
                        files={"file": (f.name, f.getvalue(), f.type or "text/csv")},
                        timeout=30,
                    )
                    if r.status_code != 200:
                        st.error(f"Upload failed for {f.name} ({r.status_code}): {r.text}")
                        st.stop()
                    uploaded_meta.append(r.json())
                except Exception as e:
                    st.error(f"Upload error for {f.name}: {e}")
                    st.stop()

        with st.expander(f"Uploaded {len(uploaded_meta)} file(s)"):
            for m in uploaded_meta:
                st.code(f"{m['filename']}  →  file_id={m['file_id']}")

    # ── Step 2: build request body ──────────────────────────────────────
    body: dict = {
        "intent": intent.strip(),
        "mode": mode,
        "presentation_type": presentation_type,
        "dry_run": dry_run,
    }

    if uploaded_meta:
        primary = uploaded_meta[primary_idx]
        ext = primary["filename"].rsplit(".", 1)[-1].lower()
        body["data_source"] = {
            "source_type": "csv_upload" if ext == "csv" else "xlsx_upload",
            "file_id": primary["file_id"],
            "filename": primary["filename"],
        }

    # ── overrides: chart_layout (per-section) or chart_type (global) ─────
    overrides: dict = {}
    chart_keys = [CHART_LABEL_TO_KEY[label] for label in chart_picks]
    chart_keys = [k for k in chart_keys if k]  # drop "Auto" entries

    if len(chart_keys) == 1:
        overrides["chart_type"] = chart_keys[0]
    elif len(chart_keys) > 1:
        overrides["chart_layout"] = chart_keys

    if overrides:
        body["overrides"] = overrides

    with st.expander("Request payload"):
        st.json(body)

    # ── Step 3: submit job ──────────────────────────────────────────────
    with st.spinner("Submitting to agent pipeline…"):
        try:
            r = requests.post(f"{V2}/generate", json=body, timeout=15)
            if r.status_code != 200:
                st.error(f"Generate failed ({r.status_code}): {r.text}")
                st.stop()
            job_id = r.json()["job_id"]
        except Exception as e:
            st.error(f"Request error: {e}")
            st.stop()

    st.info(f"Job **{job_id}** submitted — polling for results…")

    # ── Step 4: poll until done ─────────────────────────────────────────
    progress = st.progress(0, text="Waiting for pipeline…")
    status_box = st.empty()
    max_polls = 60
    final_data = None

    for i in range(max_polls):
        time.sleep(5)
        try:
            r = requests.get(f"{V2}/jobs/{job_id}", timeout=10)
            data = r.json()
            status = data.get("status", "unknown")
            progress.progress(
                min((i + 1) / max_polls, 0.95),
                text=f"Status: **{status}** — poll {i+1}",
            )

            if status == "completed":
                progress.progress(1.0, text="✅ Completed!")
                final_data = data
                break
            elif status == "failed":
                progress.progress(1.0, text="❌ Failed")
                st.error("Pipeline failed")
                with st.expander("Error details", expanded=True):
                    st.json(data)
                st.stop()
        except Exception as e:
            status_box.warning(f"Poll error: {e}")

    if final_data is None:
        st.warning("Timed out waiting for the job to finish (5 min).")
        st.stop()

    # ── Step 5: results + download ───────────────────────────────────────
    st.success("Presentation generated!")

    with st.expander("Pipeline result", expanded=False):
        st.json(final_data)

    if final_data.get("ppt_file_path") or final_data.get("result", {}).get("ppt_download_url"):
        try:
            dl = requests.get(f"{V2}/jobs/{job_id}/download", timeout=30)
            if dl.status_code == 200:
                st.download_button(
                    "⬇️  Download .pptx",
                    data=dl.content,
                    file_name=f"autodeck_{job_id}.pptx",
                    mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    type="primary",
                    use_container_width=True,
                )
            else:
                st.warning(f"Download not available ({dl.status_code})")
        except Exception as e:
            st.warning(f"Download error: {e}")
