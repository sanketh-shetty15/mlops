"""
dashboard/app.py
-----------------
Traffic Accident Severity Analytics — Redesigned Dashboard
Clean professional light theme with improved layout and charts.

Run with:
    streamlit run dashboard/app.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Traffic Accident Severity Analytics",
    page_icon="🚦",
    layout="wide",
    initial_sidebar_state="expanded",
)

from dashboard import queries, charts
from dashboard.database import table_exists


# ── Custom CSS — forced light theme, all text visible ─────────────────────────
st.markdown("""
<style>
    /* ── Force light background on EVERYTHING ── */
    .stApp,
    .stApp > div,
    .block-container,
    [data-testid="stAppViewContainer"],
    [data-testid="stVerticalBlock"],
    [data-testid="column"] {
        background-color: #f4f6f9 !important;
        color: #1a1a2e !important;
    }

    /* ── All text elements → dark (but not inside dark containers) ── */
    p, label, h2, h3, h4, li {
        color: #1a1a2e !important;
    }

    /* ── Page headings dark, but header banner headings stay white ── */
    h1 { color: #1a1a2e !important; }
    .dashboard-header h1,
    .dashboard-header h1 * { color: #ffffff !important; }
    .dashboard-header p,
    .dashboard-header p * { color: #a8b8d8 !important; }

    /* ── Part2 banner — dark bg, white text ── */
    .part2-banner { 
        background: linear-gradient(135deg, #1a1a2e, #0f3460);
        padding: 20px 28px; border-radius: 12px; margin: 8px 0 20px 0;
    }
    .part2-banner .part2-title { 
        font-size: 1.4rem; font-weight: 800; color: #ffffff !important;
    }
    .part2-banner .part2-sub { 
        font-size: 0.88rem; color: #a8b8d8 !important; margin-top: 6px;
    }

    /* ── Streamlit default text overrides ── */
    .stMarkdown, .stText, .stCaption {
        color: #1a1a2e !important;
    }

    /* ── Form inputs: white background, dark text ── */
    .stSelectbox > div > div > div,
    .stMultiSelect > div > div,
    .stNumberInput > div > div > input,
    input[type="text"], input[type="number"], select, textarea {
        background-color: #ffffff !important;
        color: #1a1a2e !important;
        border: 1px solid #dee2e6 !important;
        border-radius: 6px !important;
    }

    /* ── ALL baseweb select boxes — white bg, dark text everywhere ── */
    [data-baseweb="select"],
    [data-baseweb="select"] > div,
    [data-baseweb="select"] div,
    [data-baseweb="select"] span {
        background-color: #ffffff !important;
        color: #1a1a2e !important;
    }
    [data-baseweb="select"] svg { color: #1a1a2e !important; }

    /* ── Sidebar selects override back to dark ── */
    section[data-testid="stSidebar"] [data-baseweb="select"],
    section[data-testid="stSidebar"] [data-baseweb="select"] > div,
    section[data-testid="stSidebar"] [data-baseweb="select"] div,
    section[data-testid="stSidebar"] [data-baseweb="select"] span {
        background-color: #16213e !important;
        color: #e0e6f0 !important;
    }

    /* ── Dropdown menu options ── */
    [data-baseweb="menu"],
    [data-baseweb="menu"] ul,
    [data-baseweb="option"] {
        background-color: #ffffff !important;
        color: #1a1a2e !important;
    }

    /* ── Number input ── */
    [data-testid="stNumberInputField"],
    [data-testid="stNumberInputField"] input {
        background-color: #ffffff !important;
        color: #1a1a2e !important;
    }

    /* ── Spinner: no dark background ── */
    [data-testid="stSpinner"] > div {
        background-color: transparent !important;
    }
    /* ── Spinner wrapper that shows as dark box ── */
    [data-testid="stSpinner"] {
        background-color: transparent !important;
    }
    div[data-testid="stSpinner"] > div > div {
        background-color: transparent !important;
    }

    /* ── MLflow "View experiments" dark button inside chart-card ── */
    .mlflow-btn {
        background: #0f3460;
        color: #ffffff !important;
        padding: 10px;
        border-radius: 8px;
        font-size: 0.8rem;
        text-align: center;
        margin-top: 12px;
    }
    .mlflow-btn * { color: #ffffff !important; }

    /* ── Form container: white bg, force dark text on all children ── */
    [data-testid="stForm"] {
        background-color: #ffffff !important;
        border: 1px solid #e9ecef !important;
        border-radius: 12px !important;
        padding: 20px !important;
    }
    [data-testid="stForm"] [data-baseweb="select"] > div {
        background-color: #ffffff !important;
        color: #1a1a2e !important;
    }

    /* ── Metric values ── */
    [data-testid="stMetricValue"],
    [data-testid="stMetricLabel"],
    [data-testid="stMetricDelta"] {
        color: #1a1a2e !important;
    }
    [data-testid="metric-container"] {
        background-color: #ffffff !important;
        border-radius: 10px !important;
        padding: 12px !important;
        border: 1px solid #dee2e6 !important;
        display: block !important;
    }

    /* ── Dataframe / table ── */
    .stDataFrame, [data-testid="stDataFrame"] {
        background-color: #ffffff !important;
    }
    .stDataFrame td {
        color: #1a1a2e !important;
        background-color: #ffffff !important;
    }
    .stDataFrame th {
        color: #ffffff !important;
        background-color: #0f3460 !important;
    }

    /* ── Inline HTML tables inside chart-card keep their own colours ── */
    .chart-card table td { color: #1a1a2e !important; }
    .chart-card table th { color: #ffffff !important; }

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab-list"] {
        background-color: #e9ecef !important;
        border-radius: 8px !important;
        padding: 4px !important;
    }
    .stTabs [data-baseweb="tab"] {
        color: #495057 !important;
        background-color: transparent !important;
        border-radius: 6px !important;
        font-weight: 600 !important;
        font-size: 0.82rem !important;
    }
    .stTabs [aria-selected="true"] {
        background-color: #0f3460 !important;
        color: white !important;
    }

    /* ── Buttons ── */
    .stButton > button {
        background-color: #0f3460 !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
    }
    .stButton > button:hover {
        background-color: #1a4a7a !important;
    }
    [data-testid="baseButton-primary"] {
        background-color: #e63946 !important;
        color: white !important;
    }

    /* ── Spinners, captions ── */
    .stCaption, .stCaption p {
        color: #6c757d !important;
        font-size: 0.78rem !important;
    }

    /* ── Alert / info / warning boxes ── */
    .stAlert {
        background-color: #ffffff !important;
        color: #1a1a2e !important;
    }
    [data-testid="stNotification"] {
        color: #1a1a2e !important;
    }

    /* ── Divider ── */
    hr {
        border: none !important;
        border-top: 1px solid #dee2e6 !important;
        margin: 20px 0 !important;
    }

    /* ── Header banner ── */
    .dashboard-header {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        padding: 28px 36px;
        border-radius: 14px;
        margin-bottom: 24px;
    }
    .dashboard-header h1 {
        font-size: 2.2rem; font-weight: 700;
        margin: 0; color: #ffffff !important;
    }
    .dashboard-header p {
        font-size: 0.95rem; color: #a8b8d8 !important;
        margin: 6px 0 0 0;
    }

    /* ── Section titles ── */
    .section-title {
        font-size: 1.05rem !important;
        font-weight: 700 !important;
        color: #1a1a2e !important;
        padding: 10px 0 6px 0;
        border-bottom: 3px solid #0f3460;
        margin-bottom: 16px;
    }

    /* ── KPI cards ── */
    .kpi-card {
        background: white;
        border-radius: 12px;
        padding: 20px 18px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.07);
        border-left: 5px solid #0f3460;
        text-align: center;
    }
    .kpi-card.fatal   { border-left-color: #e63946; }
    .kpi-card.serious { border-left-color: #f4a261; }
    .kpi-card.slight  { border-left-color: #2ec4b6; }
    .kpi-card.cas     { border-left-color: #9467bd; }
    .kpi-card.veh     { border-left-color: #1f77b4; }
    .kpi-label { font-size: 0.75rem; font-weight: 600;
                 color: #6c757d !important; text-transform: uppercase;
                 letter-spacing: 0.8px; margin-bottom: 8px; }
    .kpi-value { font-size: 2rem; font-weight: 800;
                 color: #1a1a2e !important; line-height: 1; }
    .kpi-sub   { font-size: 0.72rem; color: #adb5bd !important; margin-top: 5px; }

    /* ── Chart / content cards ── */
    .chart-card {
        background: white !important;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        margin-bottom: 20px;
        color: #1a1a2e !important;
    }
    .chart-card p, .chart-card b, .chart-card li {
        color: #1a1a2e !important;
    }
    /* table cells inside chart-card — td dark, th white on dark bg */
    .chart-card table td { color: #1a1a2e !important; }
    .chart-card table th { color: #ffffff !important; }
    /* dark-bg spans inside chart-card (e.g. MLflow button) keep white */
    .chart-card span[style*="color:white"],
    .chart-card span[style*="color: white"] { color: #ffffff !important; }

    /* ── Info badge ── */
    .info-badge {
        display: inline-block;
        background: #e8f4fd;
        color: #0f3460 !important;
        border-radius: 20px;
        padding: 4px 14px;
        font-size: 0.78rem;
        font-weight: 600;
        margin-bottom: 16px;
    }

    /* ── Sidebar stays dark ── */
    section[data-testid="stSidebar"] {
        background-color: #1a1a2e !important;
    }
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] div,
    section[data-testid="stSidebar"] label {
        color: #e0e6f0 !important;
    }
    section[data-testid="stSidebar"] [data-baseweb="select"] div {
        background-color: #16213e !important;
        color: #e0e6f0 !important;
        border: 1px solid #0f3460 !important;
    }
    section[data-testid="stSidebar"] [data-baseweb="tag"] {
        background-color: #0f3460 !important;
        color: #e0e6f0 !important;
    }
</style>
""", unsafe_allow_html=True)


# ── DB guard ──────────────────────────────────────────────────────────────────
def _check_db_ready():
    if not table_exists("accident_analytics_mart"):
        st.error(
            "**Analytics table not found.**\n\n"
            "Run the pipeline first:\n```\npython scripts/run_pipeline.py\n```"
        )
        st.stop()


# ── KPI card HTML ─────────────────────────────────────────────────────────────
def _kpi_card(label, value, sub="", css_class=""):
    return f"""
    <div class="kpi-card {css_class}">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value}</div>
        <div class="kpi-sub">{sub}</div>
    </div>
    """


# ── Sidebar ───────────────────────────────────────────────────────────────────
def _build_sidebar() -> dict:
    st.sidebar.markdown("""
    <div style="padding:20px 10px 10px 10px;">
        <div style="font-size:1.3rem;font-weight:800;color:#fff;margin-bottom:4px;">
            🚦 Filters
        </div>
        <div style="font-size:0.78rem;color:#a8b8d8;margin-bottom:20px;">
            UK Road Safety 2023
        </div>
    </div>
    """, unsafe_allow_html=True)

    with st.sidebar:
        with st.spinner(""):
            opts = queries.get_filter_options()

    filters = {}

    st.sidebar.markdown(
        "<div style='font-size:0.72rem;font-weight:700;color:#a8b8d8;"
        "text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;'>"
        "Year</div>", unsafe_allow_html=True
    )
    if opts.get("years"):
        sel_years = st.sidebar.multiselect(
            "Year", options=opts["years"], default=opts["years"],
            key="yr", label_visibility="collapsed"
        )
        if sel_years and len(sel_years) < len(opts["years"]):
            filters["years"] = sel_years

    st.sidebar.markdown(
        "<div style='font-size:0.72rem;font-weight:700;color:#a8b8d8;"
        "text-transform:uppercase;letter-spacing:1px;margin:14px 0 6px 0;'>"
        "Severity</div>", unsafe_allow_html=True
    )
    if opts.get("severity"):
        sel_sev = st.sidebar.multiselect(
            "Severity", options=opts["severity"], default=opts["severity"],
            key="sev", label_visibility="collapsed"
        )
        if sel_sev and len(sel_sev) < len(opts["severity"]):
            filters["severity"] = sel_sev

    st.sidebar.markdown(
        "<div style='font-size:0.72rem;font-weight:700;color:#a8b8d8;"
        "text-transform:uppercase;letter-spacing:1px;margin:14px 0 6px 0;'>"
        "Road Type</div>", unsafe_allow_html=True
    )
    if opts.get("road_types"):
        sel_road = st.sidebar.multiselect(
            "Road Type", options=opts["road_types"], default=opts["road_types"],
            key="road", label_visibility="collapsed"
        )
        if sel_road and len(sel_road) < len(opts["road_types"]):
            filters["road_types"] = sel_road

    st.sidebar.markdown(
        "<div style='font-size:0.72rem;font-weight:700;color:#a8b8d8;"
        "text-transform:uppercase;letter-spacing:1px;margin:14px 0 6px 0;'>"
        "Weather</div>", unsafe_allow_html=True
    )
    if opts.get("weather_conditions"):
        sel_wx = st.sidebar.multiselect(
            "Weather Condition", options=opts["weather_conditions"],
            default=opts["weather_conditions"],
            key="wx", label_visibility="collapsed"
        )
        if sel_wx and len(sel_wx) < len(opts["weather_conditions"]):
            filters["weather_conditions"] = sel_wx

    st.sidebar.markdown("<hr style='border-color:#0f3460;margin:20px 0;'>",
                        unsafe_allow_html=True)
    st.sidebar.markdown(
        "<div style='font-size:0.72rem;color:#a8b8d8;line-height:1.6;padding:0 4px;'>"
        "📌 Data: UK STATS19 (DfT)<br>"
        "🌤️ Weather: Open-Meteo API<br>"
        "🗄️ DB: PostgreSQL / Neon<br>"
        "📊 Charts: Plotly<br>"
        "⚡ App: Streamlit"
        "</div>", unsafe_allow_html=True
    )

    return filters


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    _check_db_ready()
    filters = _build_sidebar()

    # ── HEADER ────────────────────────────────────────────────────────────────
    st.markdown("""
    <div class="dashboard-header">
        <h1 style="color:white !important;">🚦 Traffic Accident Severity Analytics</h1>
        <p>
            UK Road Safety Open Data (STATS19) 2023 •
            Enriched with Open-Meteo Historical Weather •
            104,246 Accidents • Great Britain
        </p>
    </div>
    """, unsafe_allow_html=True)

    # ── SECTION 1: KPI CARDS ──────────────────────────────────────────────────
    st.markdown('<div class="section-title">📊 Key Performance Indicators</div>',
                unsafe_allow_html=True)

    with st.spinner(""):
        kpi = queries.get_kpi_summary(
            years=filters.get("years"),
            severity=filters.get("severity"),
            road_types=filters.get("road_types"),
            weather_conditions=filters.get("weather_conditions"),
        )

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        st.markdown(_kpi_card(
            "Total Accidents",
            f"{kpi['total_accidents']:,}",
            "All severities combined"
        ), unsafe_allow_html=True)
    with c2:
        st.markdown(_kpi_card(
            "Fatal",
            f"{kpi['fatal_count']:,}",
            f"{100*kpi['fatal_count']/max(kpi['total_accidents'],1):.1f}% of total",
            "fatal"
        ), unsafe_allow_html=True)
    with c3:
        st.markdown(_kpi_card(
            "Serious",
            f"{kpi['serious_count']:,}",
            f"{100*kpi['serious_count']/max(kpi['total_accidents'],1):.1f}% of total",
            "serious"
        ), unsafe_allow_html=True)
    with c4:
        st.markdown(_kpi_card(
            "Slight",
            f"{kpi['slight_count']:,}",
            f"{100*kpi['slight_count']/max(kpi['total_accidents'],1):.1f}% of total",
            "slight"
        ), unsafe_allow_html=True)
    with c5:
        st.markdown(_kpi_card(
            "Total Casualties",
            f"{kpi['total_casualties']:,}",
            "People injured or killed",
            "cas"
        ), unsafe_allow_html=True)
    with c6:
        st.markdown(_kpi_card(
            "Avg Vehicles",
            f"{kpi['avg_vehicles']:.2f}",
            "Per accident",
            "veh"
        ), unsafe_allow_html=True)

    if kpi.get("weather_matched_pct", 0) > 0:
        st.markdown(
            f"<div class='info-badge'>✅ Weather data matched for "
            f"{kpi['weather_matched_pct']:.1f}% of accidents</div>",
            unsafe_allow_html=True
        )

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── SECTION 2 (was 4): WEATHER vs SEVERITY ────────────────────────────────
    st.markdown('<div class="section-title">🌦️ Weather Conditions vs Accident Severity</div>',
                unsafe_allow_html=True)

    st.markdown(
        "<div class='info-badge'>ℹ️ Higher counts in clear weather reflect traffic "
        "exposure — not lower risk. Fog & rain show higher severity proportion.</div>",
        unsafe_allow_html=True
    )

    st.markdown('<div class="chart-card">', unsafe_allow_html=True)
    with st.spinner(""):
        df_wx = queries.get_weather_vs_severity(
            years=filters.get("years"),
            road_types=filters.get("road_types"),
        )
    wx1, wx2 = st.tabs(["🟥 Heatmap", "📊 Stacked Bar"])
    with wx1:
        st.plotly_chart(
            charts.chart_weather_severity_heatmap(df_wx),
            width="stretch")
    with wx2:
        st.plotly_chart(
            charts.chart_weather_severity_stacked_bar(df_wx),
            width="stretch")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── SECTION 3 (was 3): WEEKDAY ────────────────────────────────────────────
    st.markdown('<div class="section-title">📅 Weekly Accident Patterns</div>',
                unsafe_allow_html=True)

    st.markdown('<div class="chart-card">', unsafe_allow_html=True)
    with st.spinner(""):
        df_weekday = queries.get_accidents_by_weekday(
            years=filters.get("years"),
            severity=filters.get("severity"),
        )
    st.plotly_chart(
        charts.chart_accidents_by_weekday(df_weekday),
        width="stretch")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── SECTION 4 (was 2): SEVERITY + HOURLY (side by side) ──────────────────
    st.markdown('<div class="section-title">📈 Severity Distribution & Hourly Patterns</div>',
                unsafe_allow_html=True)

    col_a, col_b = st.columns([1, 1], gap="large")

    with col_a:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        with st.spinner(""):
            df_sev = queries.get_severity_distribution(
                years=filters.get("years"),
                road_types=filters.get("road_types"),
                weather_conditions=filters.get("weather_conditions"),
            )
        t1, t2 = st.tabs(["🍩 Donut", "📊 Bar"])
        with t1:
            st.plotly_chart(
                charts.chart_severity_donut(df_sev),
                width="stretch")
        with t2:
            st.plotly_chart(
                charts.chart_severity_bar(df_sev),
                width="stretch")
        st.markdown('</div>', unsafe_allow_html=True)

    with col_b:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        with st.spinner(""):
            df_hour = queries.get_accidents_by_hour(
                years=filters.get("years"),
                severity=filters.get("severity"),
                road_types=filters.get("road_types"),
            )
        st.plotly_chart(
            charts.chart_accidents_by_hour(df_hour),
            width="stretch")
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── SECTION 5 (was 5): MAP ────────────────────────────────────────────────
    st.markdown('<div class="section-title">🗺️ Accident Location Map — Great Britain</div>',
                unsafe_allow_html=True)

    map_col, ctrl_col = st.columns([5, 1])
    with ctrl_col:
        st.markdown("<br>", unsafe_allow_html=True)
        map_limit = st.slider(
            "Max Points", 500, 10000, 3000, 500,
            help="More points = slower render"
        )
        st.markdown(
            "<div style='font-size:0.72rem;color:#6c757d;margin-top:8px;'>"
            "🔴 Fatal<br>🟠 Serious<br>🟢 Slight</div>",
            unsafe_allow_html=True
        )

    with map_col:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        with st.spinner("Loading map..."):
            df_map = queries.get_hotspot_map_data(
                years=filters.get("years"),
                severity=filters.get("severity"),
                limit=map_limit,
            )
        if not df_map.empty:
            st.plotly_chart(
                charts.chart_hotspot_map(df_map),
                width="stretch")
            st.caption(f"Showing {len(df_map):,} accident locations")
        else:
            st.info("No location data available for selected filters.")
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── SECTION 6 (was 6): ROAD TYPE ──────────────────────────────────────────
    st.markdown('<div class="section-title">🛣️ Road Type vs Accident Severity</div>',
                unsafe_allow_html=True)

    st.markdown('<div class="chart-card">', unsafe_allow_html=True)
    with st.spinner(""):
        df_road = queries.get_road_type_vs_severity(
            years=filters.get("years"),
            severity=filters.get("severity"),
        )
    st.plotly_chart(
        charts.chart_road_type_severity(df_road),
        width="stretch")
    st.markdown('</div>', unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    # PART 2 — MLOps: Severity Prediction
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown("""
    <div class="part2-banner">
        <div class="part2-title">🤖 Part 2 — MLOps: Severity Prediction</div>
        <div class="part2-sub">
            Random Forest · XGBoost · LightGBM  |
            MLflow Experiment Tracking  |
            FastAPI Inference  |
            Drift Monitoring
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── P2 Section 1: Model Training Results ─────────────────────────────────
    st.markdown('<div class="section-title">📊 Model Training Results (MLflow)</div>',
                unsafe_allow_html=True)

    import json
    from pathlib import Path
    _MODELS_DIR = Path(__file__).resolve().parent.parent / "models"

    # Load training summary
    summary_path = _MODELS_DIR / "training_summary.json"
    comparison_path = _MODELS_DIR / "model_comparison.csv"

    if summary_path.exists():
        with open(summary_path) as f:
            summary = json.load(f)

        champion = summary.get("champion_model", "rf").upper()
        metrics  = summary.get("metrics", {})

        # Model comparison table — champion only, white bg, black text
        if comparison_path.exists():
            import pandas as pd
            df_cmp = pd.read_csv(comparison_path)
            df_cmp.columns = [c.replace("_", " ").title() for c in df_cmp.columns]
            champion_model = summary.get("champion_model", "").lower()
            # Keep only the champion row
            df_champ = df_cmp[df_cmp["Name"].str.lower() == champion_model]

            st.markdown("**Champion Model — Validation Set Performance:**")

            if not df_champ.empty:
                row = df_champ.iloc[0]
                cols_to_show = [c for c in df_champ.columns if c != "Name"]
                header_html = "".join(
                    f'<th style="padding:10px 16px;text-align:left;'
                    f'background:#0f3460;color:#ffffff;">{c}</th>'
                    for c in cols_to_show
                )
                cell_html = "".join(
                    f'<td style="padding:10px 16px;color:#000000;'
                    f'background:#ffffff;">{row[c]:.4f}</td>'
                    for c in cols_to_show
                )
                st.markdown(f"""
                <table style="width:100%;border-collapse:collapse;
                              font-size:0.88rem;border:1px solid #dee2e6;">
                  <thead><tr>{header_html}</tr></thead>
                  <tbody>
                    <tr style="font-weight:600;">{cell_html}</tr>
                  </tbody>
                </table>
                """, unsafe_allow_html=True)

        # Champion confusion matrix only
        st.markdown("<br>**Confusion Matrix:**", unsafe_allow_html=True)
        champion_model = summary.get("champion_model", "rf")
        cm_path = _MODELS_DIR / f"confusion_matrix_{champion_model}.png"
        if cm_path.exists():
            display_name = {"rf": "Random Forest", "xgb": "XGBoost",
                            "lgbm": "LightGBM"}.get(champion_model, champion_model)
            col_img, col_pad = st.columns([1, 2])
            with col_img:
                st.image(str(cm_path), caption=f"🏆 {display_name}", width=400)
    else:
        st.info("No training results found. Run: `python scripts/run_ml_pipeline.py`")

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── P2 Section 2: Live Severity Predictor ─────────────────────────────────

    st.markdown(
        '<div class="section-title">🎯 Live Severity Predictor (FastAPI)</div>',
        unsafe_allow_html=True,
    )

    st.caption(
        "Enter accident features below and get a real-time severity prediction "
        "from the trained model via the FastAPI service at http://localhost:8000"
    )

    # Make select-box fields and dropdown options readable
    st.markdown(
        """
        <style>
        [data-testid="stSelectbox"] [data-baseweb="select"] > div {
            background-color: #ffffff !important;
            color: #172033 !important;
            border: 1px solid #cbd5e1 !important;
        }

        [data-testid="stSelectbox"] [data-baseweb="select"] * {
            color: #172033 !important;
        }

        [data-baseweb="popover"],
        [data-baseweb="popover"] *,
        [data-baseweb="menu"],
        [data-baseweb="menu"] *,
        [role="listbox"],
        [role="listbox"] *,
        [role="option"],
        [role="option"] * {
            background-color: #ffffff !important;
            color: #172033 !important;
        }

        [role="option"]:hover,
        [aria-selected="true"] {
            background-color: #e8f1fb !important;
            color: #172033 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.form("prediction_form"):
        st.markdown("**Accident Details**")

        p1, p2, p3 = st.columns(3)

        with p1:
            p_hour = st.slider("Hour of Day", 0, 23, 8)
            p_month = st.slider("Month", 1, 12, 1)
            p_wday = st.selectbox(
                "Day of Week",
                options=[0, 1, 2, 3, 4, 5, 6],
                format_func=lambda x: [
                    "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"
                ][x],
            )

        with p2:
            p_road = st.selectbox(
                "Road Type",
                options=[1, 2, 3, 6, 7, 9],
                format_func=lambda x: {
                    1: "Roundabout",
                    2: "One way",
                    3: "Dual carriageway",
                    6: "Single carriageway",
                    7: "Slip road",
                    9: "Unknown",
                }.get(x, str(x)),
            )
            p_speed = st.selectbox(
                "Speed Limit (mph)",
                [20, 30, 40, 50, 60, 70],
            )
            p_light = st.selectbox(
                "Light Conditions",
                options=[1, 4, 5, 6, 7],
                format_func=lambda x: {
                    1: "Daylight",
                    4: "Dark (street lit)",
                    5: "Dark (no lighting)",
                    6: "Dark (lit unknown)",
                    7: "Darkness",
                }.get(x, str(x)),
            )

        with p3:
            p_temp = st.number_input(
                "Temperature (°C)", -15.0, 40.0, 12.0, step=0.5
            )
            p_precip = st.number_input(
                "Precipitation (mm)", 0.0, 50.0, 0.0, step=0.5
            )
            p_wind = st.number_input(
                "Wind Speed (mph)", 0.0, 80.0, 10.0, step=1.0
            )
            p_veh = st.number_input(
                "Vehicles Involved", 1, 10, 2, step=1
            )

        predict_btn = st.form_submit_button(
            "🔮 Predict Severity",
            type="primary",
        )

    if predict_btn:
        import httpx

        payload = {
            "accident_hour": p_hour,
            "weekday_num": p_wday,
            "accident_month": p_month,
            "road_type": p_road,
            "speed_limit": p_speed,
            "light_conditions": p_light,
            "temperature_2m": p_temp,
            "precipitation": p_precip,
            "wind_speed_10m": p_wind,
            "number_of_vehicles": p_veh,
            "road_surface_conditions": 1,
            "urban_or_rural_area": 1,
        }

        try:
            resp = httpx.post(
                "http://localhost:8000/predict/severity",
                json=payload,
                timeout=10,
            )

            if resp.status_code == 200:
                result = resp.json()
                sev = result["severity_label"]
                conf = result["confidence"] * 100
                probs = result["probabilities"]
                lat_ms = result.get("latency_ms", 0)

                colour = {
                    "Fatal": "#e63946",
                    "Serious": "#f4a261",
                    "Slight": "#2ec4b6",
                }.get(sev, "#888888")

                icon = {
                    "Fatal": "🔴",
                    "Serious": "🟠",
                    "Slight": "🟢",
                }.get(sev, "⚪")

                st.markdown(
                    f"""
                    <div style="
                        background:{colour}18;
                        border:2px solid {colour};
                        border-radius:12px;
                        padding:20px 24px;
                        margin-top:12px;
                    ">
                        <div style="
                            font-size:1.6rem;
                            font-weight:800;
                            color:{colour} !important;
                        ">
                            {icon} Predicted Severity: {sev}
                        </div>
                        <div style="
                            font-size:0.9rem;
                            color:#333333 !important;
                            margin-top:6px;
                        ">
                            Confidence: <b>{conf:.1f}%</b> &nbsp;|&nbsp;
                            Latency: <b>{lat_ms:.0f} ms</b> &nbsp;|&nbsp;
                            Model: <b>{result['champion_model'].upper()}</b>
                        </div>
                        <div style="
                            margin-top:14px;
                            color:#1a1a2e !important;
                        ">
                            <b>Class Probabilities:</b><br>
                            🔴 Fatal: <b>{probs['Fatal'] * 100:.1f}%</b> &nbsp;
                            🟠 Serious: <b>{probs['Serious'] * 100:.1f}%</b> &nbsp;
                            🟢 Slight: <b>{probs['Slight'] * 100:.1f}%</b>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.error(
                    f"API error {resp.status_code}: {resp.text}"
                )

        except Exception as exc:
            st.warning(
                f"Cannot reach FastAPI at localhost:8000 ({exc})\n\n"
                "Start it with: `uvicorn api.main:app --port 8000`"
            )

    st.markdown("<hr>", unsafe_allow_html=True)
    
    # st.markdown('<div class="section-title">🎯 Live Severity Predictor (FastAPI)</div>',
    #             unsafe_allow_html=True)

    # st.caption(
    #     "Enter accident features below and get a real-time severity prediction "
    #     "from the trained model via the FastAPI service at http://localhost:8000"
    # )

    # with st.form("prediction_form"):
    #     st.markdown("**Accident Details**")
    #     p1, p2, p3 = st.columns(3)
    #     with p1:
    #         p_hour  = st.slider("Hour of Day",        0, 23, 8)
    #         p_month = st.slider("Month",              1, 12, 1)
    #         p_wday  = st.selectbox("Day of Week",
    #                                options=[0,1,2,3,4,5,6],
    #                                format_func=lambda x: ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][x])
    #     with p2:
    #         p_road  = st.selectbox("Road Type",
    #                                options=[1,2,3,6,7,9],
    #                                format_func=lambda x: {
    #                                    1:"Roundabout",2:"One way",
    #                                    3:"Dual carriageway",6:"Single carriageway",
    #                                    7:"Slip road",9:"Unknown"
    #                                }.get(x,str(x)))
    #         p_speed = st.selectbox("Speed Limit (mph)", [20,30,40,50,60,70])
    #         p_light = st.selectbox("Light Conditions",
    #                                options=[1,4,5,6,7],
    #                                format_func=lambda x: {
    #                                    1:"Daylight",4:"Dark (street lit)",
    #                                    5:"Dark (no lighting)",6:"Dark (lit unknown)",
    #                                    7:"Darkness"
    #                                }.get(x,str(x)))
    #     with p3:
    #         p_temp  = st.number_input("Temperature (°C)", -15.0, 40.0, 12.0, step=0.5)
    #         p_precip= st.number_input("Precipitation (mm)", 0.0, 50.0, 0.0, step=0.5)
    #         p_wind  = st.number_input("Wind Speed (mph)", 0.0, 80.0, 10.0, step=1.0)
    #         p_veh   = st.number_input("Vehicles Involved", 1, 10, 2, step=1)

    #     predict_btn = st.form_submit_button("🔮 Predict Severity", type="primary")

    # if predict_btn:
    #     import httpx
    #     payload = {
    #         "accident_hour":           p_hour,
    #         "weekday_num":             p_wday,
    #         "accident_month":          p_month,
    #         "road_type":               p_road,
    #         "speed_limit":             p_speed,
    #         "light_conditions":        p_light,
    #         "temperature_2m":          p_temp,
    #         "precipitation":           p_precip,
    #         "wind_speed_10m":          p_wind,
    #         "number_of_vehicles":      p_veh,
    #         "road_surface_conditions": 1,
    #         "urban_or_rural_area":     1,
    #     }
    #     try:
    #         resp = httpx.post(
    #             "http://localhost:8000/predict/severity",
    #             json=payload, timeout=10
    #         )
    #         if resp.status_code == 200:
    #             result = resp.json()
    #             sev   = result["severity_label"]
    #             conf  = result["confidence"] * 100
    #             probs = result["probabilities"]
    #             lat_ms = result.get("latency_ms", 0)

    #             colour = {"Fatal": "#e63946", "Serious": "#f4a261",
    #                       "Slight": "#2ec4b6"}.get(sev, "#888")
    #             icon   = {"Fatal": "🔴", "Serious": "🟠",
    #                       "Slight": "🟢"}.get(sev, "⚪")

    #             st.markdown(f"""
    #             <div style="background:{colour}18;border:2px solid {colour};
    #                         border-radius:12px;padding:20px 24px;margin-top:12px;">
    #                 <div style="font-size:1.6rem;font-weight:800;color:{colour} !important;">
    #                     {icon} Predicted Severity: {sev}
    #                 </div>
    #                 <div style="font-size:0.9rem;color:#333 !important;margin-top:6px;">
    #                     Confidence: <b>{conf:.1f}%</b> &nbsp;|&nbsp;
    #                     Latency: <b>{lat_ms:.0f} ms</b> &nbsp;|&nbsp;
    #                     Model: <b>{result['champion_model'].upper()}</b>
    #                 </div>
    #                 <div style="margin-top:14px;color:#1a1a2e !important;">
    #                     <b>Class Probabilities:</b><br>
    #                     🔴 Fatal: <b>{probs['Fatal']*100:.1f}%</b> &nbsp;
    #                     🟠 Serious: <b>{probs['Serious']*100:.1f}%</b> &nbsp;
    #                     🟢 Slight: <b>{probs['Slight']*100:.1f}%</b>
    #                 </div>
    #             </div>
    #             """, unsafe_allow_html=True)
    #         else:
    #             st.error(f"API error {resp.status_code}: {resp.text}")
    #     except Exception as exc:
    #         st.warning(
    #             f"Cannot reach FastAPI at localhost:8000 ({exc})\n\n"
    #             "Start it with: `uvicorn api.main:app --port 8000`"
    #         )

    # st.markdown("<hr>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
