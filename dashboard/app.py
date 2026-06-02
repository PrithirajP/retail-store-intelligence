import os
import time
from typing import Any, Dict, Optional

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import requests
import streamlit as st


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

API_BASE_URL = os.getenv("API_BASE_URL", "http://store-api:8000")
STORE_ID = os.getenv("STORE_ID", "ST1008")
REFRESH_SECONDS = int(os.getenv("DASHBOARD_REFRESH_SECONDS", "5"))


st.set_page_config(
    page_title="Store Intelligence Dashboard",
    page_icon="🛒",
    layout="wide",
)


# ---------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------

def _safe_get(endpoint: str) -> Optional[Dict[str, Any]]:
    """
    Safely call the FastAPI backend.

    Returns:
        dict if request succeeds
        None if API is unavailable or response is invalid
    """

    url = f"{API_BASE_URL}{endpoint}"

    try:
        response = requests.get(url, timeout=3)
        response.raise_for_status()
        return response.json()

    except requests.exceptions.RequestException as exc:
        st.warning(f"Connecting to API... `{exc}`")
        return None

    except ValueError:
        st.warning("API returned an invalid JSON response.")
        return None


@st.cache_data(ttl=2)
def fetch_health() -> Optional[Dict[str, Any]]:
    return _safe_get("/health")


@st.cache_data(ttl=2)
def fetch_metrics() -> Optional[Dict[str, Any]]:
    return _safe_get(f"/stores/{STORE_ID}/metrics")


@st.cache_data(ttl=2)
def fetch_funnel() -> Optional[Dict[str, Any]]:
    return _safe_get(f"/stores/{STORE_ID}/funnel")


@st.cache_data(ttl=2)
def fetch_heatmap() -> Optional[Dict[str, Any]]:
    return _safe_get(f"/stores/{STORE_ID}/heatmap")


@st.cache_data(ttl=2)
def fetch_anomalies() -> Optional[Dict[str, Any]]:
    return _safe_get(f"/stores/{STORE_ID}/anomalies")


# ---------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------

def format_ms(ms_value: Any) -> str:
    """
    Convert milliseconds into a readable value.
    """

    try:
        ms = float(ms_value or 0)
    except (TypeError, ValueError):
        ms = 0.0

    if ms <= 0:
        return "0 sec"

    seconds = ms / 1000

    if seconds < 60:
        return f"{seconds:.1f} sec"

    minutes = seconds / 60
    return f"{minutes:.1f} min"


def render_status_badge(status: str):
    status = (status or "UNKNOWN").upper()

    if status in {"HEALTHY", "OK"}:
        st.success(status)
    elif status == "CRITICAL":
        st.error(status)
    elif status in {"WARN", "WARNING", "DEGRADED", "STALE"}:
        st.warning(status)
    else:
        st.info(status)


# ---------------------------------------------------------------------
# Render functions
# ---------------------------------------------------------------------

def render_header():
    st.title("🛒 Store Intelligence Dashboard")
    st.caption(
        f"Store: `{STORE_ID}` | API: `{API_BASE_URL}` | "
        f"Auto-refresh: every {REFRESH_SECONDS} seconds"
    )


def render_health_panel(health: Optional[Dict[str, Any]]):
    st.subheader("System Health")

    if not health:
        st.warning("Health data unavailable.")
        return

    col1, col2, col3 = st.columns(3)

    api_status = health.get("status", "UNKNOWN")
    database_status = health.get("database", {}).get("status", "UNKNOWN")

    store_health = health.get("stores", {}).get(STORE_ID, {})
    feed_status = store_health.get("feed_status", "NO_EVENTS")
    last_event_timestamp = store_health.get("last_event_timestamp")

    with col1:
        st.metric("API Status", api_status)
        render_status_badge(api_status)

    with col2:
        st.metric("Database", database_status)
        render_status_badge(database_status)

    with col3:
        st.metric("Feed Status", feed_status)
        render_status_badge(feed_status)

    if last_event_timestamp:
        st.info(f"Last event timestamp: `{last_event_timestamp}`")
    else:
        st.info("No event has been received yet.")

    warnings = health.get("warnings", []) + store_health.get("warnings", [])

    if warnings:
        st.warning("Warnings: " + ", ".join(warnings))


def render_metrics_panel(metrics: Optional[Dict[str, Any]]):
    st.subheader("North Star KPIs")

    if not metrics:
        st.warning("Metrics unavailable.")
        return

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Total Unique Visitors",
            metrics.get("total_visitors", 0),
        )

    with col2:
        st.metric(
            "Total Conversions",
            metrics.get("converted_visitors", 0),
        )

    with col3:
        st.metric(
            "Conversion Rate",
            f"{metrics.get('conversion_rate_percentage', 0.0)}%",
        )

    st.subheader("Queue and Event KPIs")

    col4, col5, col6 = st.columns(3)

    with col4:
        st.metric(
            "Current Queue Depth",
            metrics.get("current_queue_depth", 0),
        )

    with col5:
        st.metric(
            "Average Queue Wait",
            format_ms(metrics.get("avg_queue_wait_ms", 0.0)),
        )

    with col6:
        st.metric(
            "Total Events",
            metrics.get("total_events", 0),
        )

    last_event_timestamp = metrics.get("last_event_timestamp")

    if last_event_timestamp:
        st.caption(f"Latest event: `{last_event_timestamp}`")
    else:
        st.caption("No events received yet.")


def render_funnel_panel(funnel: Optional[Dict[str, Any]]):
    st.subheader("Shopper Funnel")

    if not funnel:
        st.warning("Funnel data unavailable.")
        return

    funnel_steps = funnel.get("funnel_steps", {})
    insights = funnel.get("insights", {})

    labels = [
        "Entered Store",
        "Joined Billing Queue",
        "Completed Purchase",
    ]

    values = [
        funnel_steps.get("1_entered_store", 0),
        funnel_steps.get("2_entered_billing_queue", 0),
        funnel_steps.get("3_completed_purchase", 0),
    ]

    fig = go.Figure(
        go.Funnel(
            y=labels,
            x=values,
            textinfo="value+percent initial",
        )
    )

    fig.update_layout(
        height=420,
        margin=dict(l=20, r=20, t=30, b=20),
    )

    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Queue Insights")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Queue Abandonment Count",
            insights.get("queue_abandonment_count", 0),
        )

    with col2:
        st.metric(
            "Queue Abandonment Rate",
            f"{insights.get('queue_abandonment_rate', 0.0)}%",
        )

    with col3:
        st.metric(
            "Completed Queue Cycles",
            insights.get("completed_queue_cycles", 0),
        )

    with col4:
        st.metric(
            "Queue Data Source",
            insights.get("queue_data_source", "unknown"),
        )

    st.caption(
        f"Average queue wait: "
        f"{format_ms(insights.get('avg_queue_wait_ms', 0.0))}"
    )


def render_heatmap_panel(heatmap: Optional[Dict[str, Any]]):
    st.subheader("Zone Heatmap")

    if not heatmap:
        st.warning("Heatmap data unavailable.")
        return

    data_confidence = heatmap.get("data_confidence", "UNKNOWN")
    zones = heatmap.get("zones", [])

    st.caption(f"Heatmap type: `{heatmap.get('heatmap_type', 'zone_level')}`")
    st.caption(f"Data confidence: `{data_confidence}`")

    if not zones:
        st.info("No zone-level heatmap data available yet.")
        return

    df = pd.DataFrame(zones)

    expected_columns = [
        "zone_id",
        "visit_count",
        "avg_dwell_ms",
        "heat_score",
    ]

    for col in expected_columns:
        if col not in df.columns:
            df[col] = None

    df = df[expected_columns]

    st.dataframe(df, use_container_width=True)

    chart_df = df.copy()
    chart_df["heat_score"] = pd.to_numeric(
        chart_df["heat_score"],
        errors="coerce",
    ).fillna(0)

    fig = px.bar(
        chart_df,
        x="zone_id",
        y="heat_score",
        text="heat_score",
        title="Zone Heat Score",
    )

    fig.update_layout(
        height=380,
        xaxis_title="Zone",
        yaxis_title="Heat Score",
        margin=dict(l=20, r=20, t=50, b=20),
    )

    st.plotly_chart(fig, use_container_width=True)


def render_anomalies_panel(anomalies_response: Optional[Dict[str, Any]]):
    st.subheader("Active Anomalies")

    if not anomalies_response:
        st.warning("Anomaly data unavailable.")
        return

    status = anomalies_response.get("status", "UNKNOWN")
    anomalies = anomalies_response.get("anomalies", [])

    render_status_badge(status)

    if not anomalies:
        st.success("No active anomalies detected.")
        return

    for anomaly in anomalies:
        severity = anomaly.get("severity", "INFO")
        anomaly_type = anomaly.get("type", "UNKNOWN")
        message = anomaly.get("message", "")
        suggested_action = anomaly.get("suggested_action", "")
        evidence = anomaly.get("evidence", {})

        title = f"{severity}: {anomaly_type}"

        if severity == "CRITICAL":
            st.error(title)
        elif severity == "WARN":
            st.warning(title)
        else:
            st.info(title)

        with st.expander(f"Details - {anomaly_type}", expanded=True):
            st.write(message)

            if suggested_action:
                st.markdown("**Suggested Action:**")
                st.write(suggested_action)

            if evidence:
                st.markdown("**Evidence:**")
                st.json(evidence)


def render_dwell_summary(metrics: Optional[Dict[str, Any]]):
    st.subheader("Average Product-Zone Dwell")

    if not metrics:
        st.warning("Dwell data unavailable.")
        return

    dwell_map = metrics.get("avg_dwell_ms_by_zone", {})

    if not dwell_map:
        st.info("No dwell events available yet.")
        return

    rows = [
        {
            "zone_id": zone_id,
            "avg_dwell": format_ms(avg_ms),
            "avg_dwell_ms": avg_ms,
        }
        for zone_id, avg_ms in dwell_map.items()
    ]

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True)


# ---------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------

def main():
    render_header()

    health = fetch_health()
    metrics = fetch_metrics()
    funnel = fetch_funnel()
    heatmap = fetch_heatmap()
    anomalies = fetch_anomalies()

    with st.container():
        render_health_panel(health)

    st.divider()

    with st.container():
        render_metrics_panel(metrics)

    st.divider()

    left_col, right_col = st.columns([1.2, 1])

    with left_col:
        render_funnel_panel(funnel)

    with right_col:
        render_anomalies_panel(anomalies)

    st.divider()

    heatmap_col, dwell_col = st.columns([1.2, 1])

    with heatmap_col:
        render_heatmap_panel(heatmap)

    with dwell_col:
        render_dwell_summary(metrics)

    st.divider()

    st.caption(
        "Dashboard auto-refreshes. Keep the CV pipeline running in a second terminal "
        "to see live updates."
    )

    time.sleep(REFRESH_SECONDS)

    try:
        st.rerun()
    except AttributeError:
        st.experimental_rerun()


if __name__ == "__main__":
    main()