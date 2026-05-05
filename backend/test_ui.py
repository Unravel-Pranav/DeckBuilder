"""AutoDeck Agent Pipeline V2 — Streamlit Test UI."""

import json
import time

import requests
import streamlit as st

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE = "http://localhost:8000"
API_V2 = f"{API_BASE}/api/v2/agent"
MCP_URL = f"{API_BASE}/mcp"

MCP_TOOLS = [
    "recommend_chart_type",
    "generate_structure",
    "list_templates",
    "profile_data",
    "map_columns_to_chart",
    "generate_section_insights",
    "fetch_report_data",
    "fetch_template_summary",
]

# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------

st.set_page_config(page_title="AutoDeck Agent Tester", layout="wide")
st.title("AutoDeck Agent Pipeline — V2 Tester")

# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------

_DEFAULTS = {
    "file_id": None,
    "filename": None,
    "job_id": None,
    "last_poll": 0.0,
    "job_result": None,
}
for key, val in _DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _post(url: str, **kwargs) -> requests.Response | None:
    try:
        resp = requests.post(url, timeout=30, **kwargs)
        resp.raise_for_status()
        return resp
    except requests.RequestException as e:
        st.error(f"POST {url} failed: {e}")
        return None


def _get(url: str) -> requests.Response | None:
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return resp
    except requests.RequestException as e:
        st.error(f"GET {url} failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Sidebar: MCP Tool Tester
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("MCP Tool Tester")
    st.caption("Call individual tools exposed via the /mcp endpoint")

    mcp_tool = st.selectbox("Tool", MCP_TOOLS)
    mcp_input = st.text_area(
        "Input JSON (tool arguments)",
        value='{}',
        height=120,
    )

    if st.button("Call MCP Tool"):
        try:
            args = json.loads(mcp_input)
        except json.JSONDecodeError as e:
            st.error(f"Invalid JSON: {e}")
            args = None

        if args is not None:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": mcp_tool, "arguments": args},
            }
            try:
                resp = requests.post(MCP_URL, json=payload, timeout=60)
                if resp.ok:
                    st.json(resp.json())
                else:
                    st.error(f"MCP returned {resp.status_code}: {resp.text[:500]}")
            except requests.RequestException as e:
                st.error(f"MCP call failed: {e}")

    st.divider()
    if st.button("Reset Session", type="secondary"):
        for key in _DEFAULTS:
            st.session_state[key] = _DEFAULTS[key]
        st.rerun()

# ---------------------------------------------------------------------------
# Section A: File Upload
# ---------------------------------------------------------------------------

st.header("A. File Upload")

uploaded = st.file_uploader(
    "Upload CSV or XLSX to test with",
    type=["csv", "xlsx"],
    help="Optional — uploads via POST /api/v2/agent/upload",
)

if uploaded and st.session_state.file_id is None:
    with st.spinner("Uploading…"):
        resp = _post(
            f"{API_V2}/upload",
            files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type)},
        )
    if resp:
        data = resp.json()
        st.session_state.file_id = data["file_id"]
        st.session_state.filename = data["filename"]
        st.success(f"Uploaded — file_id: `{data['file_id']}`, filename: `{data['filename']}`")

if st.session_state.file_id:
    st.info(f"Using uploaded file: **{st.session_state.filename}** (id: `{st.session_state.file_id}`)")

st.divider()

# ---------------------------------------------------------------------------
# Section B: Generation Request Form
# ---------------------------------------------------------------------------

st.header("B. Generation Request")

col1, col2 = st.columns(2)

with col1:
    intent = st.text_input("Intent", value="Quarterly revenue analysis by region")
    presentation_type = st.text_input("Presentation Type", value="financial")
    audience = st.text_input("Audience", value="stakeholders")

with col2:
    tone = st.text_input("Tone", value="formal")
    mode = st.selectbox("Mode", ["full", "structure_only", "ppt_only", "skeleton"])
    dry_run = st.checkbox("Dry Run (skip actual PPT generation)")

# Data source
st.subheader("Data Source")

if st.session_state.file_id:
    st.success(f"Auto-detected: `csv_upload` from uploaded file **{st.session_state.filename}**")
    ext = (st.session_state.filename or "").rsplit(".", 1)[-1].lower()
    source_type = "xlsx_upload" if ext == "xlsx" else "csv_upload"
    data_source = {
        "source_type": source_type,
        "file_id": st.session_state.file_id,
        "filename": st.session_state.filename,
    }
else:
    ds_choice = st.radio(
        "Data source type",
        ["none", "report_id", "template_id", "inline_json"],
        horizontal=True,
    )
    data_source = None
    if ds_choice == "report_id":
        rid = st.number_input("Report ID", min_value=1, value=1, step=1)
        data_source = {"source_type": "report_id", "report_id": rid}
    elif ds_choice == "template_id":
        tid = st.number_input("Template ID", min_value=1, value=1, step=1)
        data_source = {"source_type": "template_id", "template_id": tid}
    elif ds_choice == "inline_json":
        inline_raw = st.text_area(
            "Inline data (JSON array of objects)",
            value='[{"category": "A", "value": 100}, {"category": "B", "value": 200}]',
            height=100,
        )
        try:
            inline_parsed = json.loads(inline_raw)
            data_source = {"source_type": "inline_json", "inline_data": inline_parsed}
        except json.JSONDecodeError as e:
            st.error(f"Invalid inline JSON: {e}")

# Overrides
with st.expander("Advanced Overrides"):
    ov_chart_type = st.text_input("Chart type (global override)", placeholder="bar, line, pie…")
    ov_chart_layout = st.text_input("Chart layout (comma-separated per section)", placeholder="bar,line,pie")
    ov_skip_viz = st.checkbox("Skip visualization step")
    ov_skip_insights = st.checkbox("Skip insights step")

overrides: dict | None = None
if any([ov_chart_type, ov_chart_layout, ov_skip_viz, ov_skip_insights]):
    overrides = {
        "skip_viz": ov_skip_viz,
        "skip_insights": ov_skip_insights,
    }
    if ov_chart_type:
        overrides["chart_type"] = ov_chart_type
    if ov_chart_layout:
        overrides["chart_layout"] = [x.strip() or None for x in ov_chart_layout.split(",")]

# Generate button
st.divider()

if st.button("Generate", type="primary", use_container_width=True):
    payload = {
        "intent": intent,
        "presentation_type": presentation_type,
        "audience": audience,
        "tone": tone,
        "mode": mode,
        "dry_run": dry_run,
    }
    if data_source:
        payload["data_source"] = data_source
    if overrides:
        payload["overrides"] = overrides

    with st.spinner("Submitting generation request…"):
        resp = _post(f"{API_V2}/generate", json=payload)

    if resp:
        result = resp.json()
        st.session_state.job_id = result["job_id"]
        st.session_state.job_result = None
        st.success(f"Job submitted — `{result['job_id']}` (status: {result['status']})")
        st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Section C: Job Status
# ---------------------------------------------------------------------------

st.header("C. Job Status")

if not st.session_state.job_id:
    st.info("No job submitted yet. Fill in the form above and click **Generate**.")
else:
    job_id = st.session_state.job_id
    st.write(f"**Job ID:** `{job_id}`")

    resp = _get(f"{API_V2}/jobs/{job_id}")
    if resp:
        job_data = resp.json()
        status = job_data.get("status", "unknown")

        status_colors = {
            "pending": "🟡",
            "running": "🔵",
            "completed": "🟢",
            "failed": "🔴",
        }
        st.write(f"**Status:** {status_colors.get(status, '⚪')} {status.upper()}")

        if job_data.get("created_at") and job_data.get("updated_at"):
            st.caption(f"Created: {job_data['created_at']} | Updated: {job_data['updated_at']}")

        # Show steps from result if available
        result_payload = job_data.get("result")
        if result_payload and isinstance(result_payload, dict):
            steps = result_payload.get("steps_completed", [])
            if steps:
                st.write("**Steps completed:**")
                for step in steps:
                    st.write(f"  - {step}")
            st.session_state.job_result = result_payload

        # Auto-refresh while pending/running
        if status in ("pending", "running"):
            time.sleep(2)
            st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Section D: Results
# ---------------------------------------------------------------------------

st.header("D. Results")

result_data = st.session_state.job_result
if not result_data:
    st.info("Waiting for job to complete…")
else:
    res_status = result_data.get("status", "unknown")

    # Metrics table
    metrics = result_data.get("metrics", {})
    if metrics:
        st.subheader("Step Metrics")
        rows = []
        for step_name, m in metrics.items():
            rows.append({
                "Step": step_name,
                "Duration (ms)": round(m.get("duration_ms") or 0, 1),
                "Status": m.get("status", "—"),
                "Error": m.get("error") or "",
            })
        st.dataframe(rows, use_container_width=True)

    # Errors
    errors = result_data.get("errors", [])
    if errors:
        st.subheader("Errors")
        for err in errors:
            st.error(f"**[{err.get('step', '?')}]** {err.get('message', 'Unknown error')}")

    # Structure preview
    structure = result_data.get("structure")
    if structure:
        with st.expander("Structure (JSON)", expanded=False):
            st.json(structure)

    # Data contracts (skeleton mode)
    contracts = result_data.get("data_contracts")
    if contracts:
        st.subheader("Data Contracts")
        for i, contract in enumerate(contracts):
            with st.expander(f"Contract #{i + 1}: {contract.get('section_name', 'Unnamed')}"):
                st.json(contract)

    # Download PPT
    ppt_url = result_data.get("ppt_download_url")
    if ppt_url and st.session_state.job_id:
        st.subheader("Download Presentation")
        dl_resp = _get(f"{API_V2}/jobs/{st.session_state.job_id}/download")
        if dl_resp:
            st.download_button(
                label="Download PPTX",
                data=dl_resp.content,
                file_name=f"autodeck_{st.session_state.job_id}.pptx",
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )
    elif res_status == "completed" and not ppt_url:
        st.info("No PPT file produced (dry_run or structure_only mode).")
