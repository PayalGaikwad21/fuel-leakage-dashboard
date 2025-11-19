# ==== SECTION 1: SETUP & IMPORTS ====
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from supabase import create_client, Client
from flask import Flask, request, jsonify
from threading import Thread
import json
import os
import time

# python -m streamlit run fuel_leakage_dashboard.py

def load_custom_css():
    with open("styles/custom_theme.css") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

load_custom_css()


# ==== SECTION 1A: FLASK SERVER FOR N8N ALERTS ====
app = Flask(__name__)
latest_alert = None  # global variable to store the newest alert

@app.route('/new_alert', methods=['POST'])
def new_alert():
    global latest_alert
    data = request.json
    latest_alert = data

    # ✅ Save the latest alert locally
    with open("latest_alert.json", "w") as f:
        json.dump(data, f, indent=2)

    print("🚨 New alert received from n8n:", data)
    return jsonify({"success": True, "message": "Alert received by Streamlit"}), 200

def run_flask():
    # run Flask in background so it doesn’t block Streamlit
    app.run(host="0.0.0.0", port=8506, debug=False)

# Start Flask in a background thread
flask_thread = Thread(target=run_flask)
flask_thread.daemon = True
flask_thread.start()


# ==== SECTION 2: STREAMLIT DASHBOARD ====
st.set_page_config(
    page_title="⛽ Fuel Leakage Detection Dashboard",
    page_icon="⛽",
    layout="wide"
)

st.title("⛽ Fuel Leakage Detection & Efficiency Dashboard")
st.caption("Analyze truck fuel efficiency, detect possible leakage, and monitor driver performance in real time.")


# ==== SECTION 3: FETCH DATA FROM SUPABASE ====
st.sidebar.header("📦 Data Source")

SUPABASE_URL = "https://vugjrcjbifbloxcvhydi.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ1Z2pyY2piaWZibG94Y3ZoeWRpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjI3NjI5NzMsImV4cCI6MjA3ODMzODk3M30.BUZR9b8Pm1GbzWY6lThHdhsWRHWSSa6TouKlpd2lazE"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@st.cache_data
def load_data():
    response = supabase.table("trips").select("*").execute()
    df = pd.DataFrame(response.data)
    return df

try:
    df = load_data()
    st.success("✅ Data fetched successfully from Supabase!")
except Exception as e:
    st.error(f"Failed to fetch from Supabase: {e}")
    st.stop()

st.dataframe(df.head(10), use_container_width=True)


# ==== SECTION 4: KPI CARDS ====
total_trips = len(df)
avg_variance = round(df["variance_pct"].mean(), 2)
total_leakage = round(df["leakage_liters"].sum(), 2)
total_leakage_cost = round(df["leakage_cost_inr"].sum(), 2)
percent_leak_trips = round((df["leakage_flag"] == "Leakage Suspected").sum() / total_trips * 100, 2)

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total Trips", total_trips)
col2.metric("Avg Variance (%)", avg_variance)
col3.metric("Total Leakage (L)", total_leakage)
col4.metric("Leakage Cost (₹)", total_leakage_cost)
col5.metric("% Trips with Leakage", percent_leak_trips)


# ==== SECTION 5: LIVE LEAKAGE ALERT SYSTEM ====
st.subheader("⚠️ Live Leakage Alerts")

# ---- Auto-refresh setup ----
REFRESH_INTERVAL = 10  # seconds
if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = time.time()
if time.time() - st.session_state.last_refresh > REFRESH_INTERVAL:
    st.session_state.last_refresh = time.time()
    st.rerun()

st.caption(f"🔄 Auto-refresh every {REFRESH_INTERVAL}s | Last refresh: {time.strftime('%H:%M:%S', time.localtime(st.session_state.last_refresh))}")

# ---- Fetch latest alerts from Supabase ----
try:
    response = supabase.table("leakage_alerts").select("*").order("id", desc=True).limit(10).execute()
    alerts = response.data

    if alerts:
        total_alerts = len(alerts)
        total_loss = sum(a.get("leakage_cost_inr", 0) for a in alerts)
        st.warning(f"🚨 {total_alerts} active alerts | Total loss ₹{total_loss:,.2f}")

        for alert in alerts:
            trip = alert.get("trip_id", "Unknown")
            truck = alert.get("truck_id", "Unknown")
            driver = alert.get("driver_id", "Unknown")
            loss = alert.get("leakage_cost_inr", 0)
            msg = alert.get("alert_message", f"⚠️ Truck {truck} possible fuel leakage!")

            with st.expander(f"🚨 Trip {trip} | Truck {truck} | ₹{loss:,.2f}", expanded=False):
                st.error(msg)
                c1, c2, c3 = st.columns(3)
                c1.metric("Trip ID", trip)
                c2.metric("Driver ID", driver)
                c3.metric("Loss (₹)", f"{loss:,.2f}")
    else:
        st.success("✅ No fuel leakage alerts currently. System running normally.")
except Exception as e:
    st.error(f"⚠️ Could not load alerts: {e}")

# ---- Show toast if latest_alert.json exists ----
if os.path.exists("latest_alert.json"):
    with open("latest_alert.json", "r") as f:
        latest_alert = json.load(f)
        st.toast(f"🚨 New alert: Truck {latest_alert.get('truck_id')} | ₹{latest_alert.get('leakage_cost_inr')}", icon="🚛")

st.divider()
if st.button("🔄 Refresh Now"):
    st.session_state.last_refresh = time.time()
    st.rerun()


# ==== SECTION 6: CHARTS ====
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Variance Distribution", 
    "Fuel Comparison", 
    "Leakage Cost per Driver", 
    "Distance vs Fuel", 
    "ECU Idling Correlation"
])

with tab1:
    fig = px.histogram(df, x="variance_pct", nbins=40, title="Variance % Distribution")
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    top_trips = df.sort_values("leakage_liters", ascending=False).head(20)
    fig2 = px.bar(top_trips, x="trip_id", y=["expected_fuel_liters", "actual_fuel_liters"], barmode="group",
                  title="Expected vs Actual Fuel (Top 20 Trips)")
    fig2.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig2, use_container_width=True)

with tab3:
    driver_summary = df.groupby("driver_id").agg(total_leakage_cost_inr=("leakage_cost_inr", "sum")).reset_index()
    fig3 = px.bar(driver_summary.sort_values("total_leakage_cost_inr", ascending=False).head(15),
                  x="driver_id", y="total_leakage_cost_inr", title="Leakage Cost per Driver (Top 15)")
    st.plotly_chart(fig3, use_container_width=True)

with tab4:
    fig4 = px.scatter(df, x="distance_km", y="actual_fuel_liters", color="leakage_flag",
                      hover_data=["trip_id", "driver_id", "truck_id"],
                      title="Distance vs Actual Fuel (Colored by Flag)")
    st.plotly_chart(fig4, use_container_width=True)

with tab5:
    fig5 = px.scatter(df, x="ecu_idling_hours", y="variance_pct", color="leakage_flag",
                      title="ECU Idling vs Variance (%)")
    st.plotly_chart(fig5, use_container_width=True)


# ==== SECTION 7: DRIVER PERFORMANCE TABLE ====
st.subheader("👨‍🔧 Driver Performance Summary")

driver_summary = df.groupby("driver_id").agg(
    total_trips=("trip_id", "count"),
    avg_variance_pct=("variance_pct", "mean"),
    leakage_freq_pct=("leakage_flag", lambda s: round((s == "Leakage Suspected").sum() / s.count() * 100, 2)),
    total_leakage_liters=("leakage_liters", "sum"),
    total_leakage_cost_inr=("leakage_cost_inr", "sum")
).reset_index().sort_values("total_leakage_cost_inr", ascending=False)

st.dataframe(driver_summary, use_container_width=True)


# ==== SECTION 8: TRIP-LEVEL DETAIL VIEW ====
st.subheader("🧾 Trip-Level Detailed Data")

drivers = ["All"] + sorted(df["driver_id"].unique().tolist())
trucks = ["All"] + sorted(df["truck_id"].unique().tolist())
driver_filter = st.selectbox("Select Driver", drivers)
truck_filter = st.selectbox("Select Truck", trucks)
flag_filter = st.checkbox("Show only suspected leakage trips")

filtered_df = df.copy()
if driver_filter != "All":
    filtered_df = filtered_df[filtered_df["driver_id"] == driver_filter]
if truck_filter != "All":
    filtered_df = filtered_df[filtered_df["truck_id"] == truck_filter]
if flag_filter:
    filtered_df = filtered_df[filtered_df["leakage_flag"] == "Leakage Suspected"]

st.dataframe(filtered_df, use_container_width=True)


# ==== SECTION 9: INSIGHTS + DOWNLOAD REPORT ====
st.subheader("🧠 Auto-Generated Insights")

total_cost = round(filtered_df["leakage_cost_inr"].sum(), 2)
most_loss_driver = filtered_df.groupby("driver_id")["leakage_cost_inr"].sum().idxmax()
st.write(f"💬 Driver **{most_loss_driver}** caused the highest fuel loss worth ₹{total_cost:.2f}.")
st.write(f"🛣️ Average variance across all trips: {avg_variance}%.")
st.write(f"⚠️ Total suspected leakage cost this month: ₹{total_leakage_cost}.")

csv = filtered_df.to_csv(index=False).encode("utf-8")
st.download_button(
    label="📥 Download Leakage Report (CSV)",
    data=csv,
    file_name="leakage_report.csv",
    mime="text/csv"
)
