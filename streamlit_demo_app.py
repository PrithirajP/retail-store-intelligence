import json
from pathlib import Path

import pandas as pd
import streamlit as st


EVENT_LOG_PATH = Path("event_log.jsonl")


st.set_page_config(
    page_title="Retail Store Intelligence Demo",
    layout="wide",
)


def load_events() -> pd.DataFrame:
    if not EVENT_LOG_PATH.exists():
        st.error("event_log.jsonl not found in the repository.")
        return pd.DataFrame()

    events = []

    with EVENT_LOG_PATH.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()

            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                st.error(f"Invalid JSON at line {line_no}")
                return pd.DataFrame()

            metadata = event.get("metadata") or {}

            events.append(
                {
                    "event_id": event.get("event_id"),
                    "store_id": event.get("store_id"),
                    "camera_id": event.get("camera_id"),
                    "visitor_id": event.get("visitor_id"),
                    "event_type": event.get("event_type"),
                    "timestamp": event.get("timestamp"),
                    "zone_id": event.get("zone_id"),
                    "dwell_ms": event.get("dwell_ms"),
                    "is_staff": event.get("is_staff"),
                    "confidence": event.get("confidence"),
                    "queue_depth": metadata.get("queue_depth"),
                    "sku_zone": metadata.get("sku_zone"),
                    "session_seq": metadata.get("session_seq"),
                }
            )

    df = pd.DataFrame(events)

    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df["dwell_ms"] = pd.to_numeric(df["dwell_ms"], errors="coerce")
        df["queue_depth"] = pd.to_numeric(df["queue_depth"], errors="coerce")
        df["confidence"] = pd.to_numeric(df["confidence"], errors="coerce")

    return df


def product_zone_filter(df: pd.DataFrame) -> pd.Series:
    excluded = {"ENTRY_DOOR", "BILLING_QUEUE", "BEHIND_COUNTER"}
    zone = df["zone_id"].fillna(df["sku_zone"]).fillna("")
    return ~zone.isin(excluded)


def compute_metrics(df: pd.DataFrame) -> dict:
    customer_df = df[df["is_staff"] != True].copy()

    entries = customer_df[customer_df["event_type"] == "ENTRY"]
    reentries = customer_df[customer_df["event_type"] == "REENTRY"]

    total_visitors = entries["visitor_id"].nunique()

    billing_exits = customer_df[customer_df["event_type"] == "BILLING_QUEUE_EXIT"]
    converted_visitors = billing_exits["visitor_id"].nunique()

    conversion_rate = (
        round(converted_visitors / total_visitors * 100, 2)
        if total_visitors > 0
        else 0.0
    )

    queue_joins = customer_df[customer_df["event_type"] == "BILLING_QUEUE_JOIN"]
    queue_exits = customer_df[customer_df["event_type"] == "BILLING_QUEUE_EXIT"]
    queue_abandons = customer_df[customer_df["event_type"] == "BILLING_QUEUE_ABANDON"]

    current_queue_depth = max(
        queue_joins["visitor_id"].nunique()
        - queue_exits["visitor_id"].nunique()
        - queue_abandons["visitor_id"].nunique(),
        0,
    )

    closed_queue_cycles = queue_exits["visitor_id"].nunique() + queue_abandons["visitor_id"].nunique()

    queue_abandonment_rate = (
        round(queue_abandons["visitor_id"].nunique() / closed_queue_cycles * 100, 2)
        if closed_queue_cycles > 0
        else 0.0
    )

    return {
        "total_visitors": total_visitors,
        "reentries": reentries["visitor_id"].nunique(),
        "converted_visitors": converted_visitors,
        "conversion_rate": conversion_rate,
        "current_queue_depth": current_queue_depth,
        "queue_abandonment_rate": queue_abandonment_rate,
        "total_events": len(df),
    }


def render_funnel(df: pd.DataFrame):
    customer_df = df[df["is_staff"] != True].copy()

    entered = customer_df[customer_df["event_type"] == "ENTRY"]["visitor_id"].nunique()

    product_visits = customer_df[
        customer_df["event_type"].isin(["ZONE_ENTER", "ZONE_DWELL"])
        & product_zone_filter(customer_df)
    ]["visitor_id"].nunique()

    queue_joined = customer_df[
        customer_df["event_type"] == "BILLING_QUEUE_JOIN"
    ]["visitor_id"].nunique()

    purchased = customer_df[
        customer_df["event_type"] == "BILLING_QUEUE_EXIT"
    ]["visitor_id"].nunique()

    funnel_df = pd.DataFrame(
        [
            {"stage": "1. Entered Store", "visitors": entered},
            {"stage": "2. Visited Product Zone", "visitors": product_visits},
            {"stage": "3. Entered Billing Queue", "visitors": queue_joined},
            {"stage": "4. Completed Purchase", "visitors": purchased},
        ]
    )

    st.dataframe(funnel_df, use_container_width=True)
    st.bar_chart(funnel_df.set_index("stage"))


def render_heatmap(df: pd.DataFrame):
    customer_df = df[df["is_staff"] != True].copy()
    zone_df = customer_df[
        customer_df["event_type"].isin(["ZONE_ENTER", "ZONE_DWELL"])
        & product_zone_filter(customer_df)
    ].copy()

    if zone_df.empty:
        st.info("No product-zone activity available.")
        return

    zone_df["zone_key"] = zone_df["zone_id"].fillna(zone_df["sku_zone"]).fillna("UNKNOWN")

    summary = (
        zone_df.groupby("zone_key")
        .agg(
            visit_count=("event_id", "count"),
            unique_visitors=("visitor_id", "nunique"),
            avg_dwell_ms=("dwell_ms", "mean"),
        )
        .reset_index()
    )

    summary["avg_dwell_ms"] = summary["avg_dwell_ms"].fillna(0).round(2)

    max_visits = max(summary["visit_count"].max(), 1)
    max_dwell = max(summary["avg_dwell_ms"].max(), 1)

    summary["heat_score"] = (
        0.6 * (summary["visit_count"] / max_visits)
        + 0.4 * (summary["avg_dwell_ms"] / max_dwell)
    ).round(3)

    st.dataframe(summary, use_container_width=True)
    st.bar_chart(summary.set_index("zone_key")[["heat_score"]])


def render_anomalies(metrics: dict, df: pd.DataFrame):
    anomalies = []

    if metrics["current_queue_depth"] >= 5:
        anomalies.append(
            {
                "type": "BILLING_QUEUE_SPIKE",
                "severity": "WARN",
                "message": "Current billing queue depth is high.",
            }
        )

    if metrics["total_visitors"] >= 5 and metrics["conversion_rate"] < 10:
        anomalies.append(
            {
                "type": "CONVERSION_DROP",
                "severity": "WARN",
                "message": "Conversion rate is low compared with visitor traffic.",
            }
        )

    product_events = df[
        df["event_type"].isin(["ZONE_ENTER", "ZONE_DWELL"])
        & product_zone_filter(df)
    ]

    if metrics["total_events"] > 20 and product_events.empty:
        anomalies.append(
            {
                "type": "DEAD_ZONE",
                "severity": "INFO",
                "message": "No product-zone activity detected in the event log.",
            }
        )

    if not anomalies:
        st.success("No active demo anomalies detected.")
        return

    for item in anomalies:
        if item["severity"] == "WARN":
            st.warning(f"{item['type']}: {item['message']}")
        else:
            st.info(f"{item['type']}: {item['message']}")


def main():
    st.title("Retail Store Intelligence — Working Demo")

    st.caption(
        "This hosted demo reads from the submitted event_log.jsonl file. "
        "The full CCTV-to-API pipeline is available in the GitHub repository."
    )

    df = load_events()

    if df.empty:
        st.stop()

    stores = sorted(df["store_id"].dropna().unique().tolist())

    selected_store = st.sidebar.selectbox("Select Store", stores)

    store_df = df[df["store_id"] == selected_store].copy()

    st.sidebar.metric("Loaded Events", len(store_df))
    st.sidebar.caption("Source: event_log.jsonl")

    metrics = compute_metrics(store_df)

    st.subheader("Key Metrics")

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total Visitors", metrics["total_visitors"])
    col2.metric("Converted Visitors", metrics["converted_visitors"])
    col3.metric("Conversion Rate", f"{metrics['conversion_rate']}%")
    col4.metric("Total Events", metrics["total_events"])

    col5, col6, col7 = st.columns(3)

    col5.metric("Re-entries", metrics["reentries"])
    col6.metric("Queue Depth", metrics["current_queue_depth"])
    col7.metric("Queue Abandonment", f"{metrics['queue_abandonment_rate']}%")

    st.divider()

    st.subheader("Shopper Funnel")
    render_funnel(store_df)

    st.divider()

    st.subheader("Zone Heatmap")
    render_heatmap(store_df)

    st.divider()

    st.subheader("Operational Anomalies")
    render_anomalies(metrics, store_df)

    st.divider()

    st.subheader("Event Log Preview")
    st.dataframe(store_df.sort_values("timestamp").tail(200), use_container_width=True)


if __name__ == "__main__":
    main()