
import pandas as pd
import schedule
import time
from datetime import datetime
import os
import threading
# import winsound
from smartapi_login import SmartAPIHelper

import streamlit as st

# ========== CONFIGURATION ==========
API_KEY = "8CVmnWvW"
CLIENT_ID = "CNBC3363"
MPIN = "3588"  # Replace with your MPIN
TOTP_SECRET = "SZASE7JAJLAKEVDTYPZQSDFIPM"  # Replace with your TOTP secret
CSV_FILE = "nifty_oi_log.csv"
SPIKE_THRESHOLD = 50000  # OI change threshold to trigger alert

# ========== LOGIN ==========
api = SmartAPIHelper()
api.login(api_key_hist="", api_key_trading=API_KEY, uid=CLIENT_ID, mpin=MPIN, totp=TOTP_SECRET)

# ========== EXPIRY DETECTION ==========
def get_nearest_expiry():
    option_chain = api.get_option_chain("NIFTY")
    if option_chain:
        expiries = sorted({item['expiry'] for item in option_chain})
        return expiries[0].replace("-", "").upper()[2:]  # e.g., 25JUN27
    return datetime.now().strftime("%y%b").upper() + "27"

# ========== OI TRACKER FUNCTION ==========
def fetch_oi_data():
    nifty_ltp = api.get_ltp("NSE:NIFTY")
    if nifty_ltp is None:
        print("❌ Failed to get Nifty LTP")
        return

    atm = int(round(nifty_ltp, -2))
    strikes = [atm, atm + 50, atm - 50]
    expiry = get_nearest_expiry()

    row = {"Time": datetime.now().strftime("%H:%M:%S")}
    for strike in strikes:
        for opt_type in ["CE", "PE"]:
            symbol = f"NIFTY{expiry}{strike:05d}{opt_type}"
            try:
                oi_data = api.get_ltp(f"NFO:{symbol}")
                row[f"{strike}_{opt_type}_OI"] = oi_data.get("openInterest", None)
            except Exception as e:
                print(f"Error fetching {symbol}: {e}")
                row[f"{strike}_{opt_type}_OI"] = None

    df = pd.DataFrame([row])
    if not os.path.exists(CSV_FILE):
        df.to_csv(CSV_FILE, index=False)
    else:
        prev = pd.read_csv(CSV_FILE)
        prev = pd.concat([prev, df], ignore_index=True)
        for col in df.columns[1:]:
            chg_col = f"{col}_chg"
            prev[chg_col] = prev[col].diff()
            if not pd.isna(prev[chg_col].iloc[-1]) and abs(prev[chg_col].iloc[-1]) > SPIKE_THRESHOLD:
                print(f"🔔 OI Spike Detected in {col}: Δ {int(prev[chg_col].iloc[-1])}")
                print("🔔 OI spike alert!")
        prev.to_csv(CSV_FILE, index=False)

    print(f"[{row['Time']}] ✅ OI data logged.")

def run_scheduler():
    schedule.every(1).minutes.do(fetch_oi_data)
    while True:
        schedule.run_pending()
        time.sleep(1)

# ========== STREAMLIT DASHBOARD ==========
def run_dashboard():
    st.set_page_config(page_title="Nifty OI Tracker", layout="wide")
    st.title("📊 Nifty OI Trend Dashboard")

    try:
        df = pd.read_csv(CSV_FILE)
        df['Time'] = pd.to_datetime(df['Time'], format='%H:%M:%S')
    except:
        st.warning("Waiting for CSV data...")
        return

    latest_row = df.iloc[-1]
    st.markdown(f"### Latest Snapshot: {latest_row['Time'].time()}")
    oi_cols = [col for col in df.columns if col.endswith('_OI')]
    chart_data = df.set_index('Time')[oi_cols]
    st.line_chart(chart_data)

    spike_cols = [col for col in df.columns if '_chg' in col]
    if spike_cols:
        st.markdown("### OI Spike Monitor")
        spike_df = df[['Time'] + spike_cols].tail(5)
        st.dataframe(spike_df, use_container_width=True)

    st.caption("Auto-refreshes every minute. Keep this page open while script runs.")

# ========== START EVERYTHING ==========
if __name__ == "__main__":
    t = threading.Thread(target=run_scheduler, daemon=True)
    t.start()
    run_dashboard()
