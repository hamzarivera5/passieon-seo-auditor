import streamlit as st
import io
from urllib.parse import urlparse
from passieon_audit import crawl_site, build_report, WORKERS

# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Passieon SEO Auditor",
    page_icon="logo.png",
    layout="wide",
)

# ============================================================
# CUSTOM STYLING
# ============================================================

st.markdown("""
<style>
    .block-container { padding-top: 1rem; max-width: 1100px; }

    /* Header */
    .header-bar {
        background: #0A0A0A;
        padding: 1.5rem 2.5rem;
        border-radius: 14px;
        display: flex;
        align-items: center;
        gap: 1.5rem;
        margin-bottom: 1.8rem;
    }
    .header-logo { height: 48px; }
    .header-text { color: #ffffff; }
    .header-title {
        font-size: 1.6rem;
        font-weight: 700;
        margin: 0;
        color: #FF1493;
    }
    .header-sub {
        font-size: 0.9rem;
        color: #888;
        margin: 0.15rem 0 0 0;
    }

    /* Progress */
    .progress-wrap {
        background: #1a1a2e;
        border-radius: 10px;
        padding: 1.5rem 2rem;
        margin: 1rem 0;
    }
    .progress-label {
        color: #ccc;
        font-size: 0.85rem;
        margin-bottom: 0.5rem;
    }
    .progress-track {
        background: #2a2a3e;
        border-radius: 8px;
        height: 28px;
        overflow: hidden;
        position: relative;
    }
    .progress-fill {
        height: 100%;
        border-radius: 8px;
        background: linear-gradient(90deg, #FF1493, #C71585);
        transition: width 0.3s ease;
        display: flex;
        align-items: center;
        justify-content: flex-end;
        padding-right: 10px;
        min-width: 50px;
    }
    .progress-pct {
        color: white;
        font-size: 0.8rem;
        font-weight: 700;
    }
    .progress-stats {
        display: flex;
        justify-content: space-between;
        margin-top: 0.5rem;
        color: #888;
        font-size: 0.8rem;
    }

    /* Metric cards */
    .metrics-grid {
        display: grid;
        grid-template-columns: repeat(6, 1fr);
        gap: 12px;
        margin: 1.5rem 0;
    }
    .metric-card {
        background: var(--background-secondary, #f7f7f8);
        border-radius: 12px;
        padding: 1.1rem 0.8rem;
        text-align: center;
        border: 1px solid rgba(0,0,0,0.06);
    }
    .metric-value {
        font-size: 2rem;
        font-weight: 700;
        margin: 0;
        line-height: 1.2;
    }
    .metric-label {
        font-size: 0.78rem;
        color: #777;
        margin: 0.25rem 0 0 0;
    }

    /* Issue tags */
    .issue-row {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 8px 12px;
        border-radius: 8px;
        margin-bottom: 4px;
    }
    .issue-row:hover { background: rgba(0,0,0,0.03); }
    .tag {
        font-size: 0.7rem;
        font-weight: 700;
        padding: 3px 10px;
        border-radius: 6px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        min-width: 58px;
        text-align: center;
        display: inline-block;
    }
    .tag-high { background: #FFC7CE; color: #9C0006; }
    .tag-med { background: #FFEB9C; color: #9C6500; }
    .tag-low { background: #C6EFCE; color: #006100; }
    .issue-name { font-weight: 500; font-size: 0.95rem; }
    .issue-count { color: #999; font-size: 0.85rem; margin-left: auto; }

    /* Hide streamlit branding */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    .stDeployButton { display: none; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# HEADER WITH LOGO
# ============================================================

st.markdown("""
<div class="header-bar">
    <img src="data:image/png;base64,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" class="header-logo" />
    <div class="header-text">
        <p class="header-title">Passieon SEO Auditor</p>
        <p class="header-sub">42 technical SEO checks in one click</p>
    </div>
</div>
""", unsafe_allow_html=True)

# ============================================================
# INPUT
# ============================================================

col_input, col_button = st.columns([5, 1])

with col_input:
    url_input = st.text_input(
        "Website URL",
        placeholder="Enter website URL (e.g. https://example.com)",
        label_visibility="collapsed",
    )

with col_button:
    start_clicked = st.button("Audit", type="primary", use_container_width=True)

# ============================================================
# AUDIT
# ============================================================

if start_clicked and url_input:
    url = url_input.strip()
    if not url.startswith("http"):
        url = "https://" + url
    if not url.endswith("/"):
        url = url + "/"

    domain = urlparse(url).netloc

    # --- PROGRESS BAR ---
    progress_placeholder = st.empty()
    log_expander = st.expander("Crawl log", expanded=False)
    log_lines = []

    def render_progress(crawled, remaining, pct):
        progress_placeholder.markdown(f"""
        <div class="progress-wrap">
            <div class="progress-label">Crawling {domain}...</div>
            <div class="progress-track">
                <div class="progress-fill" style="width: {max(pct, 3)}%;">
                    <span class="progress-pct">{pct}%</span>
                </div>
            </div>
            <div class="progress-stats">
                <span>{crawled} pages crawled</span>
                <span>{remaining} pages remaining</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    render_progress(0, 0, 0)

    def on_progress(crawled, remaining, msg):
        total = crawled + remaining
        pct = round((crawled / max(total, 1)) * 100) if total > 0 else 0
        pct = min(pct, 99)
        render_progress(crawled, remaining, pct)
        log_lines.append(msg)
        with log_expander:
            st.code("\n".join(log_lines[-15:]), language=None)

    # --- CRAWL ---
    pages, issues, elapsed = crawl_site(url, workers=WORKERS, on_progress=on_progress)

    if not pages:
        render_progress(0, 0, 0)
        st.error("No pages were crawled. The site may be blocking cloud crawlers, the URL may be wrong, or the site may be down.")
        st.info("Tip: Sites behind Cloudflare or aggressive bot protection may block cloud-based crawlers. Use the local CLI version instead: `py passieon_audit.py`")
        st.stop()

    # Show 100%
    render_progress(len(pages), 0, 100)

    # --- BUILD REPORT ---
    with st.spinner("Building report..."):
        wb = build_report(pages, issues, domain, elapsed)
        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)

    # --- METRICS DASHBOARD ---
    st.markdown("---")

    pages_with_issues = len(set(i["url"] for i in issues))
    pages_clean = len(pages) - pages_with_issues
    health = round((pages_clean / max(len(pages), 1)) * 100)
    high = sum(1 for i in issues if i["priority"] == "High")
    medium = sum(1 for i in issues if i["priority"] == "Medium")
    low = sum(1 for i in issues if i["priority"] == "Low")

    health_color = "#006100" if health >= 70 else "#9C6500" if health >= 40 else "#9C0006"

    st.markdown(f"""
    <div class="metrics-grid">
        <div class="metric-card">
            <p class="metric-value" style="color:{health_color};">{health}%</p>
            <p class="metric-label">Health score</p>
        </div>
        <div class="metric-card">
            <p class="metric-value">{len(pages)}</p>
            <p class="metric-label">Pages crawled</p>
        </div>
        <div class="metric-card">
            <p class="metric-value">{len(issues)}</p>
            <p class="metric-label">Total issues</p>
        </div>
        <div class="metric-card">
            <p class="metric-value" style="color:#9C0006;">{high}</p>
            <p class="metric-label">High priority</p>
        </div>
        <div class="metric-card">
            <p class="metric-value" style="color:#9C6500;">{medium}</p>
            <p class="metric-label">Medium priority</p>
        </div>
        <div class="metric-card">
            <p class="metric-value" style="color:#006100;">{low}</p>
            <p class="metric-label">Low priority</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # --- DOWNLOAD ---
    col_dl, col_time = st.columns([1, 3])
    with col_dl:
        st.download_button(
            label="Download full report (.xlsx)",
            data=buffer.getvalue(),
            file_name=f"audit_{domain.replace('.', '_')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True,
        )
    with col_time:
        sheet_count = len(set(i["issue"] for i in issues))
        st.caption(f"Completed in {elapsed}s -- {sheet_count} issue tabs -- {len(pages)} pages analyzed")

    # --- ISSUE BREAKDOWN ---
    st.markdown("#### Issues breakdown")

    issue_types = {}
    issue_priority_map = {}
    for i in issues:
        issue_types[i["issue"]] = issue_types.get(i["issue"], 0) + 1
        issue_priority_map[i["issue"]] = i["priority"]

    priority_order = {"High": 0, "Medium": 1, "Low": 2}
    sorted_types = sorted(
        issue_types.items(),
        key=lambda x: (priority_order.get(issue_priority_map.get(x[0], "Low"), 3), -x[1]),
    )

    for issue_type, count in sorted_types:
        priority = issue_priority_map.get(issue_type, "")
        tag_class = "tag-high" if priority == "High" else "tag-med" if priority == "Medium" else "tag-low"
        st.markdown(
            f'<div class="issue-row">'
            f'<span class="tag {tag_class}">{priority}</span>'
            f'<span class="issue-name">{issue_type}</span>'
            f'<span class="issue-count">{count} pages</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # --- DETAIL TABLE ---
    st.markdown("#### All issues")

    sorted_issues = sorted(issues, key=lambda x: (priority_order.get(x["priority"], 3), x["issue"]))

    display_data = []
    for i in sorted_issues:
        display_data.append({
            "Priority": i["priority"],
            "Issue": i["issue"],
            "URL": i["url"],
            "Details": i["details"][:150],
        })

    st.dataframe(
        display_data,
        use_container_width=True,
        height=420,
        column_config={
            "URL": st.column_config.TextColumn("URL", width="large"),
            "Details": st.column_config.TextColumn("Details", width="large"),
        },
    )

    # --- FOOTER ---
    st.markdown("---")
    st.caption("Built by Passieon -- passieon.com")

elif start_clicked and not url_input:
    st.warning("Enter a website URL to start the audit.")
