import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import time

# Use the Docker service name 'store-api'
API_BASE_URL = "http://store-api:8000"
STORE_ID = "ST1008"

st.set_page_config(page_title="Apex Retail Intelligence", layout="wide")

st.title("📊 Apex Retail Intelligence")
st.markdown(f"**Live Dashboard for Store:** `{STORE_ID}`")

def fetch_metrics():
    try:
        res = requests.get(f"{API_BASE_URL}/stores/{STORE_ID}/metrics", timeout=2)
        return res.json() if res.status_code == 200 else None
    except:
        return None

def fetch_funnel():
    try:
        res = requests.get(f"{API_BASE_URL}/stores/{STORE_ID}/funnel", timeout=2)
        return res.json() if res.status_code == 200 else None
    except:
        return None

# --- Main Dashboard Logic ---
metrics = fetch_metrics()
funnel = fetch_funnel()

if not metrics or not funnel:
    st.warning("⏳ Waiting for API data... Ensure the CV pipeline is running and sending events.")
else:
    # Top Level Metrics
    st.subheader("North Star Metrics")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(label="Total Unique Visitors", value=metrics["total_visitors"])
    with col2:
        st.metric(label="Total Conversions (Purchases)", value=metrics["converted_visitors"])
    with col3:
        st.metric(label="Conversion Rate", value=f"{metrics['conversion_rate_percentage']}%")

    st.divider()

    # Funnel Visualization
    st.subheader("Shopper Funnel")
    col_chart, col_insights = st.columns([2, 1])

    with col_chart:
        steps = ["Entered Store", "Joined Billing Queue", "Completed Purchase"]
        values = [
            funnel["funnel_steps"]["1_entered_store"],
            funnel["funnel_steps"]["2_entered_billing_queue"],
            funnel["funnel_steps"]["3_completed_purchase"]
        ]

        fig = go.Figure(go.Funnel(
            y=steps,
            x=values,
            textinfo="value+percent initial",
            marker={"color": ["#1f77b4", "#ff7f0e", "#2ca02c"]}
        ))
        fig.update_layout(margin={"t": 0, "b": 0})
        st.plotly_chart(fig, use_container_width=True)

    with col_insights:
        st.markdown("### Funnel Insights")
        abandon_count = funnel["insights"]["queue_abandonment_count"]
        abandon_rate = funnel["insights"]["queue_abandonment_rate"]
        
        st.info(f"**Queue Abandonment:** {abandon_count} shoppers left the queue without buying.")
        st.error(f"**Abandonment Rate:** {abandon_rate}% of the queue was lost.")
        
        if abandon_rate > 20:
            st.markdown("🚨 **Alert:** Severe bottleneck at checkout. Recommend opening another register.")

# Auto-refresh mechanism (simulates real-time updates)
time.sleep(5)
st.rerun()