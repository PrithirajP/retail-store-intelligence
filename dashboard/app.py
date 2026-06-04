import os
import time
from typing import Any, Dict, Optional

import pandas as pd
import requests
import streamlit as st


API_BASE_URL = os.getenv("API_BASE_URL", "http://store-api:8000").rstrip("/")
DEFAULT_STORE_OPTIONS = os.getenv("STORE_OPTIONS", "ST1008,STORE_2")


def _get_store_options() -> list[str]:
    stores = [
        item.strip()
        for item in DEFAULT_STORE_OPTIONS.split(",")
        if item.strip()
    ]

    if not stores:
        return ["ST1008", "STORE_2"]

    return stores


def _get_json(path: str, timeout: int = 5) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    url = f"{API_BASE_URL}{path}"

    try:
        response = requests.get(url, timeout=timeout)

        if response.status_code != 200:
            return None, f"HTTP {response.status_code}: {response.text[:300]}"

        return response.json(), None

    except requests.RequestException as exc:
        return None, str(exc)


def _metric_value(data: Optional[dict], key: str, default: Any = 0) -> Any:
    if not isinstance(data, dict):
        return default

    value = data.get(key)

    if value is None:
        return default

    return value


def _render_health(health: Optional[dict], error: Optional[str]):
    st.subheader("System Health")

    if error:
        st.error(f"Health check failed: {error}")
        return

    if not health:
        st.warning("No health response received.")
        return

    status = health.get("status", "unknown")
    database_status = health.get("database", {}).get("status", "unknown")

    col1, col2 = st.columns(2)

    with col1:
        st.metric("API Status", status)

    with col2:
        st.metric("Database", database_status)

    warnings = health.get("warnings") or []

    if warnings:
        st.warning(", ".join(str(item) for item in warnings))

    stores = health.get("stores") or {}

    if stores:
        rows = []

        for store_id, store_info in stores.items():
            rows.append(
                {
                    "store_id": store_id,
                    "feed_status": store_info.get("feed_status"),
                    "last_event_timestamp": store_info.get("last_event_timestamp"),
                    "warnings": ", ".join(store_info.get("warnings") or []),
                }
            )

        st.dataframe(pd.DataFrame(rows), use_container_width=True)
    else:
        st.info("No store event feeds have been received yet.")


def _render_metrics(metrics: Optional[dict], error: Optional[str]):
    st.subheader("North Star and Queue KPIs")

    if error:
        st.error(f"Metrics request failed: {error}")
        return

    if not metrics:
        st.warning("No metrics response received.")
        return

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Visitors", _metric_value(metrics, "total_visitors"))

    with col2:
        st.metric("Converted Visitors", _metric_value(metrics, "converted_visitors"))

    with col3:
        st.metric(
            "Conversion Rate",
            f"{_metric_value(metrics, 'conversion_rate_percentage', 0)}%",
        )

    with col4:
        st.metric("Total Events", _metric_value(metrics, "total_events"))

    col5, col6, col7 = st.columns(3)

    with col5:
        st.metric("Current Queue Depth", _metric_value(metrics, "current_queue_depth"))

    with col6:
        st.metric("Avg Queue Wait", f"{_metric_value(metrics, 'avg_queue_wait_ms', 0)} ms")

    with col7:
        st.metric(
            "Last Event",
            _metric_value(metrics, "last_event_timestamp", "No events"),
        )


def _render_funnel(funnel: Optional[dict], error: Optional[str]):
    st.subheader("Shopper Funnel")

    if error:
        st.error(f"Funnel request failed: {error}")
        return

    if not funnel:
        st.warning("No funnel response received.")
        return

    steps = funnel.get("funnel_steps") or {}

    funnel_rows = [
        {
            "stage": "1. Entered Store",
            "count": steps.get("1_entered_store", 0),
        },
        {
            "stage": "2. Visited Product Zone",
            "count": steps.get("2_visited_zone", 0),
        },
        {
            "stage": "3. Entered Billing Queue",
            "count": steps.get("3_entered_billing_queue", 0),
        },
        {
            "stage": "4. Completed Purchase",
            "count": steps.get("4_completed_purchase", 0),
        },
    ]

    funnel_df = pd.DataFrame(funnel_rows)

    st.dataframe(funnel_df, use_container_width=True)

    if not funnel_df.empty:
        st.bar_chart(funnel_df.set_index("stage"))


def _render_queue_insights(funnel: Optional[dict]):
    st.subheader("Queue Insights")

    if not funnel:
        st.info("No queue insight data available.")
        return

    insights = funnel.get("insights") or {}

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Abandonment Count", insights.get("queue_abandonment_count", 0))

    with col2:
        st.metric(
            "Abandonment Rate",
            f"{insights.get('queue_abandonment_rate', 0.0)}%",
        )

    with col3:
        st.metric("Completed Queue Cycles", insights.get("completed_queue_cycles", 0))

    with col4:
        st.metric("Open Queue Depth", insights.get("current_queue_depth", 0))


def _render_anomalies(anomalies: Optional[dict], error: Optional[str]):
    st.subheader("Operational Anomalies")

    if error:
        st.error(f"Anomalies request failed: {error}")
        return

    if not anomalies:
        st.warning("No anomaly response received.")
        return

    status = anomalies.get("status", "UNKNOWN")
    st.metric("Anomaly Status", status)

    anomaly_items = anomalies.get("anomalies") or []

    if not anomaly_items:
        st.success("No active anomalies.")
        return

    for item in anomaly_items:
        severity = item.get("severity", "INFO")
        message = item.get("message", "No message")
        anomaly_type = item.get("type", "UNKNOWN")

        if severity == "CRITICAL":
            st.error(f"{anomaly_type}: {message}")
        elif severity == "WARN":
            st.warning(f"{anomaly_type}: {message}")
        else:
            st.info(f"{anomaly_type}: {message}")

        suggested_action = item.get("suggested_action")
        if suggested_action:
            st.caption(f"Suggested action: {suggested_action}")

        evidence = item.get("evidence")
        if isinstance(evidence, dict) and evidence:
            with st.expander("Evidence"):
                st.json(evidence)


def _render_heatmap(heatmap: Optional[dict], error: Optional[str]):
    st.subheader("Zone Heatmap")

    if error:
        st.error(f"Heatmap request failed: {error}")
        return

    if not heatmap:
        st.warning("No heatmap response received.")
        return

    st.caption(f"Data confidence: {heatmap.get('data_confidence', 'UNKNOWN')}")

    zones = heatmap.get("zones") or []

    if not zones:
        st.info("No product-zone activity available yet.")
        return

    zone_df = pd.DataFrame(zones)

    st.dataframe(zone_df, use_container_width=True)

    if "zone_id" in zone_df.columns and "heat_score" in zone_df.columns:
        chart_df = zone_df[["zone_id", "heat_score"]].set_index("zone_id")
        st.bar_chart(chart_df)


def _render_dwell_summary(metrics: Optional[dict]):
    st.subheader("Average Product-Zone Dwell")

    if not metrics:
        st.info("No dwell metrics available.")
        return

    dwell_by_zone = metrics.get("avg_dwell_ms_by_zone") or {}

    if not dwell_by_zone:
        st.info("No dwell data available yet.")
        return

    rows = [
        {
            "zone_id": zone_id,
            "avg_dwell_ms": avg_dwell_ms,
        }
        for zone_id, avg_dwell_ms in dwell_by_zone.items()
    ]

    dwell_df = pd.DataFrame(rows)

    st.dataframe(dwell_df, use_container_width=True)

    if not dwell_df.empty:
        st.bar_chart(dwell_df.set_index("zone_id"))


def main():
    st.set_page_config(
        page_title="Retail Store Intelligence",
        layout="wide",
    )

    st.title("Retail Store Intelligence Dashboard")

    st.sidebar.header("Controls")

    store_options = _get_store_options()

    selected_store = st.sidebar.selectbox(
        "Store",
        options=store_options,
        index=0,
    )

    auto_refresh = st.sidebar.checkbox("Auto-refresh", value=False)
    refresh_seconds = st.sidebar.slider(
        "Refresh interval seconds",
        min_value=5,
        max_value=60,
        value=15,
        step=5,
    )

    if st.sidebar.button("Refresh now"):
        st.rerun()

    st.sidebar.caption(f"API: {API_BASE_URL}")

    health, health_error = _get_json("/health")
    metrics, metrics_error = _get_json(f"/stores/{selected_store}/metrics")
    funnel, funnel_error = _get_json(f"/stores/{selected_store}/funnel")
    heatmap, heatmap_error = _get_json(f"/stores/{selected_store}/heatmap")
    anomalies, anomalies_error = _get_json(f"/stores/{selected_store}/anomalies")

    st.caption(f"Selected store: `{selected_store}`")

    _render_health(health, health_error)

    st.divider()

    _render_metrics(metrics, metrics_error)

    st.divider()

    left_col, right_col = st.columns(2)

    with left_col:
        _render_funnel(funnel, funnel_error)

    with right_col:
        _render_queue_insights(funnel)

    st.divider()

    _render_anomalies(anomalies, anomalies_error)

    st.divider()

    left_col, right_col = st.columns(2)

    with left_col:
        _render_heatmap(heatmap, heatmap_error)

    with right_col:
        _render_dwell_summary(metrics)

    if auto_refresh:
        time.sleep(refresh_seconds)
        st.rerun()


if __name__ == "__main__":
    main()