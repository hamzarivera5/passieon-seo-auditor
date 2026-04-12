import streamlit as st
import io
import time
from urllib.parse import urlparse
from passieon_audit import crawl_site, build_report, WORKERS

# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Passieon SEO Auditor",
    page_icon="https://passieon.com/favicon.ico",
    layout="wide",
)

# ============================================================
# CUSTOM STYLING
# ============================================================

st.markdown("""
<style>
    .block-container { padding-top: 2rem; }
    .metric-card {
        background: #F8F7FF;
        border-radius: 12px;
        padding: 1.2rem;
        text-align: center;
        border: 1px solid #E8E6F0;
    }
    .metric-value {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1B2A4A;
        margin: 0;
    }
    .metric-label {
        font-size: 0.85rem;
        color: #666;
        margin: 0;
    }
    .high-tag { background: #FFC7CE; color: #9C0006; padding: 3px 10px; border-radius: 6px; font-weight: 600; font-size: 0.85rem; }
    .med-tag { background: #FFEB9C; color: #9C6500; padding: 3px 10px; border-radius: 6px; font-weight: 600; font-size: 0.85rem; }
    .low-tag { background: #C6EFCE; color: #006100; padding: 3px 10px; border-radius: 6px; font-weight: 600; font-size: 0.85rem; }
    .brand-header {
        background: linear-gradient(135deg, #1B2A4A 0%, #3D2066 100%);
        padding: 2rem 2.5rem;
        border-radius: 16px;
        margin-bottom: 2rem;
    }
    .brand-title { color: white; font-size: 2rem; font-weight: 700; margin: 0; }
    .brand-sub { color: #B8B0D0; font-size: 1rem; margin: 0.3rem 0 0 0; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# HEADER
# ============================================================

st.markdown("""
<div class="brand-header">
    <p class="brand-title">Passieon SEO Auditor</p>
    <p class="brand-sub">42 technical SEO checks -- powered by your local machine</p>
</div>
""", unsafe_allow_html=True)

# ============================================================
# INPUT SECTION
# ============================================================

col_input, col_button = st.columns([4, 1])

with col_input:
    url_input = st.text_input(
        "Website URL",
        placeholder="https://example.com",
        label_visibility="collapsed",
    )

with col_button:
    start_clicked = st.button("Start Audit", type="primary", use_container_width=True)

# ============================================================
# AUDIT LOGIC
# ============================================================

if start_clicked and url_input:
    url = url_input.strip()
    if not url.startswith("http"):
        url = "https://" + url
    if not url.endswith("/"):
        url = url + "/"

    domain = urlparse(url).netloc

    # --- CRAWL PHASE ---
    crawl_log = st.empty()
    progress_bar = st.progress(0, text=f"Starting crawl of {domain}...")
    status_container = st.status(f"Crawling {domain}...", expanded=True)

    crawl_messages = []

    def on_progress(count, message):
        crawl_messages.append(message)
        progress_bar.progress(min(count / 100, 0.99), text=f"Crawled {count} pages...")
        status_container.write(f"`{message}`")

    with status_container:
        st.write(f"Target: **{domain}**")
        st.write(f"Threads: **{WORKERS}**")
        pages, issues, elapsed = crawl_site(url, workers=WORKERS, on_progress=on_progress)

    if not pages:
        progress_bar.empty()
        status_container.update(label="Crawl failed", state="error")
        st.error("No pages were crawled. Check that the URL is correct and the site is accessible.")
        st.stop()

    progress_bar.progress(1.0, text="Crawl complete!")
    status_container.update(label=f"Crawled {len(pages)} pages in {elapsed}s", state="complete")

    # --- BUILD REPORT ---
    with st.spinner("Building Excel report..."):
        wb = build_report(pages, issues, domain, elapsed)
        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)

    # --- RESULTS DASHBOARD ---
    st.markdown("---")

    pages_with_issues = len(set(i["url"] for i in issues))
    pages_clean = len(pages) - pages_with_issues
    health = round((pages_clean / max(len(pages), 1)) * 100)
    high = sum(1 for i in issues if i["priority"] == "High")
    medium = sum(1 for i in issues if i["priority"] == "Medium")
    low = sum(1 for i in issues if i["priority"] == "Low")

    # Metric cards
    c1, c2, c3, c4, c5, c6 = st.columns(6)

    with c1:
        st.markdown(f"""
        <div class="metric-card">
            <p class="metric-value">{health}%</p>
            <p class="metric-label">Health Score</p>
        </div>""", unsafe_allow_html=True)

    with c2:
        st.markdown(f"""
        <div class="metric-card">
            <p class="metric-value">{len(pages)}</p>
            <p class="metric-label">Pages Crawled</p>
        </div>""", unsafe_allow_html=True)

    with c3:
        st.markdown(f"""
        <div class="metric-card">
            <p class="metric-value">{len(issues)}</p>
            <p class="metric-label">Total Issues</p>
        </div>""", unsafe_allow_html=True)

    with c4:
        st.markdown(f"""
        <div class="metric-card">
            <p class="metric-value" style="color:#9C0006;">{high}</p>
            <p class="metric-label">High Priority</p>
        </div>""", unsafe_allow_html=True)

    with c5:
        st.markdown(f"""
        <div class="metric-card">
            <p class="metric-value" style="color:#9C6500;">{medium}</p>
            <p class="metric-label">Medium Priority</p>
        </div>""", unsafe_allow_html=True)

    with c6:
        st.markdown(f"""
        <div class="metric-card">
            <p class="metric-value" style="color:#006100;">{low}</p>
            <p class="metric-label">Low Priority</p>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # --- DOWNLOAD BUTTON ---
    col_dl, col_info = st.columns([1, 3])
    with col_dl:
        st.download_button(
            label="Download Full Report (.xlsx)",
            data=buffer.getvalue(),
            file_name=f"audit_{domain.replace('.', '_')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True,
        )
    with col_info:
        st.info(f"Completed in **{elapsed}s** -- report has **{len(set(i['issue'] for i in issues))} issue tabs** with per-page details and recommendations.")

    # --- ISSUE BREAKDOWN TABLE ---
    st.markdown("### Issues found")

    issue_types = {}
    issue_priority_map = {}
    for i in issues:
        issue_types[i["issue"]] = issue_types.get(i["issue"], 0) + 1
        issue_priority_map[i["issue"]] = i["priority"]

    priority_order = {"High": 0, "Medium": 1, "Low": 2}
    sorted_types = sorted(issue_types.items(), key=lambda x: (priority_order.get(issue_priority_map.get(x[0], "Low"), 3), -x[1]))

    for issue_type, count in sorted_types:
        priority = issue_priority_map.get(issue_type, "")
        if priority == "High":
            tag = '<span class="high-tag">HIGH</span>'
        elif priority == "Medium":
            tag = '<span class="med-tag">MEDIUM</span>'
        else:
            tag = '<span class="low-tag">LOW</span>'

        st.markdown(f"{tag} &nbsp; **{issue_type}** -- {count} pages affected", unsafe_allow_html=True)

    # --- ALL ISSUES DETAIL ---
    st.markdown("### All issues detail")

    sorted_issues = sorted(issues, key=lambda x: (priority_order.get(x["priority"], 3), x["issue"]))

    display_data = []
    for i in sorted_issues:
        display_data.append({
            "Priority": i["priority"],
            "Issue": i["issue"],
            "URL": i["url"],
            "Details": i["details"][:120],
        })

    st.dataframe(
        display_data,
        use_container_width=True,
        height=400,
        column_config={
            "URL": st.column_config.TextColumn("URL", width="large"),
            "Details": st.column_config.TextColumn("Details", width="large"),
        },
    )

elif start_clicked and not url_input:
    st.warning("Enter a URL to audit.")
