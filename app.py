import os
import sqlite3

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="PS15 Edge IoT Monitor", page_icon="📟", layout="wide")

TIMEZONE = "Asia/Kolkata"   # change to your timezone, e.g. "UTC"
LOCAL_DB = "sensor_data.db"


def get_secret(name):
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return os.getenv(name, "")


SUPABASE_URL = get_secret("SUPABASE_URL").rstrip("/")
SUPABASE_KEY = get_secret("SUPABASE_KEY")          # the public "anon" key (read-only)
USE_CLOUD = bool(SUPABASE_URL and SUPABASE_KEY)

STATUS_NAME = {0: "SAFE", 1: "WARNING", 2: "DANGER"}
FLAG_TEXT = {1: "Smoke / gas high (MQ-2)", 2: "Air quality poor (MQ-135)",
             4: "Object too close", 8: "Vibration detected", 16: "High temperature"}
NUM_COLS = ["temperature", "humidity", "distance", "mq2", "mq135", "flags", "status", "relay", "warmup"]


def decode(flags):
    return ", ".join(text for bit, text in FLAG_TEXT.items() if int(flags) & bit) or "-"


@st.cache_data(ttl=2)
def load(limit, use_cloud):
    if use_cloud:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/readings",
            params={"select": "*", "order": "id.desc", "limit": limit},
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            timeout=8)
        r.raise_for_status()
        df = pd.DataFrame(r.json())
    else:
        try:
            con = sqlite3.connect(LOCAL_DB)
            df = pd.read_sql_query("SELECT * FROM readings ORDER BY id DESC LIMIT ?", con, params=(limit,))
            con.close()
        except Exception:
            return pd.DataFrame()
    if df.empty:
        return df
    df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(TIMEZONE)
    for c in NUM_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values("ts").reset_index(drop=True)


st.title("📟 PS15 Edge IoT Monitor")
limit = st.sidebar.slider("Readings to show", 50, 2000, 300, step=50)
st.sidebar.caption(f"Data source: {'Supabase cloud' if USE_CLOUD else 'local SQLite (sensor_data.db)'}")
st.sidebar.caption("Auto-refreshes every 2 seconds")

try:
    _df = load(limit, USE_CLOUD)
    if not _df.empty:
        st.sidebar.download_button("⬇️ Download CSV", _df.to_csv(index=False).encode(),
                                   "ps15_sensor_data.csv", "text/csv")
except Exception:
    pass


@st.fragment(run_every=2)
def dashboard():
    try:
        df = load(limit, USE_CLOUD)
    except Exception as e:
        st.error(f"Could not load data: {e}")
        return
    if df.empty:
        st.info("No data yet. Plug in the Arduino and run `python bridge.py`.")
        return

    last = df.iloc[-1]
    status = int(last.status)
    age = (pd.Timestamp.now(tz=TIMEZONE) - last.ts).total_seconds()

    # --- status banner ---
    msg = f"{STATUS_NAME[status]}  -  {decode(last.flags)}" if status else "SAFE  -  all readings normal"
    (st.success, st.warning, st.error)[status](f"### {msg}")
    if last.warmup:
        st.info("Gas sensors are warming up (about 60 s). Gas alerts are paused.")
    if age > 30:
        st.warning(f"No new data for {int(age)} s. Is the Arduino plugged in and bridge.py running?")

    # --- live readings ---
    c = st.columns(6)
    c[0].metric("🌡️ Temperature", f"{last.temperature:.1f} °C")
    c[1].metric("💧 Humidity", f"{last.humidity:.1f} %")
    c[2].metric("📏 Distance", "-" if pd.isna(last.distance) else f"{last.distance:.1f} cm")
    c[3].metric("🔥 Smoke/LPG (MQ-2)", f"{int(last.mq2)}", help="Relative level, not calibrated ppm")
    c[4].metric("🌫️ Air quality (MQ-135)", f"{int(last.mq135)}", help="Relative level, not calibrated ppm")
    c[5].metric("📳 Vibration", "DETECTED" if int(last.flags) & 8 else "None")

    # --- device status ---
    st.subheader("Device status")
    d = st.columns(4)
    d[0].markdown(f"**Green LED**  {'🟢 ON' if status == 0 else '⚪ OFF'}")
    d[1].markdown(f"**Red LED**  {'🔴 ON' if status >= 1 else '⚪ OFF'}")
    d[2].markdown(f"**Buzzer**  {'🔊 ON' if status == 2 else '⚪ OFF'}")
    d[3].markdown(f"**Relay**  {'⚡ ON' if int(last.relay) else '⚪ OFF'}")

    # --- charts ---
    p = df.set_index("ts")
    a, b = st.columns(2)
    a.subheader("Temperature & humidity")
    a.line_chart(p[["temperature", "humidity"]])
    b.subheader("Gas sensors (relative)")
    b.line_chart(p[["mq2", "mq135"]])
    st.subheader("Distance (cm)")
    st.line_chart(p["distance"])

    # --- event log ---
    st.subheader("Event log")
    prev = df["flags"].shift().fillna(0)
    ev = df[(df["flags"] != 0) & (df["flags"] != prev)].copy()
    if ev.empty:
        st.caption("No events in this period.")
    else:
        ev["Event"] = ev["flags"].apply(decode)
        ev["Level"] = ev["status"].map(STATUS_NAME)
        ev["Time"] = ev["ts"].dt.strftime("%Y-%m-%d %H:%M:%S")
        st.dataframe(ev[["Time", "Level", "Event"]].iloc[::-1], use_container_width=True, hide_index=True)

    # --- stats + raw data ---
    with st.expander("Statistics for this period"):
        st.dataframe(df[["temperature", "humidity", "distance", "mq2", "mq135"]]
                     .describe().loc[["min", "max", "mean"]].round(1), use_container_width=True)
    with st.expander("Raw data"):
        st.dataframe(df.iloc[::-1], use_container_width=True, hide_index=True)


dashboard()
