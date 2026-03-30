import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import plotly.graph_objects as go

# =========================
# PAGE SETTINGS
# =========================
st.set_page_config(page_title="Automated Stock Decision Engine", layout="wide")

# =========================
# CUSTOM CSS
# =========================
st.markdown("""
<style>
    .stApp {
        background: linear-gradient(135deg, #050816, #0b1020, #111827);
        color: #ffffff;
    }

    h1 {
        color: #7dd3fc !important;
        text-shadow: 0 0 12px rgba(125, 211, 252, 0.6);
        font-weight: 800;
    }

    h2, h3 {
        color: #c084fc !important;
        font-weight: 700;
    }

    p, div, span, label {
        color: #e5e7eb !important;
    }

    .stDataFrame, .stTable {
        background-color: rgba(17, 24, 39, 0.85) !important;
        border-radius: 14px !important;
        border: 1px solid rgba(125, 211, 252, 0.25) !important;
        box-shadow: 0 0 16px rgba(56, 189, 248, 0.15);
        padding: 8px;
    }

    div[data-baseweb="notification"] {
        border-radius: 14px !important;
    }

    div[data-baseweb="select"] > div {
        background-color: rgba(17, 24, 39, 0.95) !important;
        border: 1px solid #38bdf8 !important;
        border-radius: 12px !important;
        color: white !important;
        box-shadow: 0 0 10px rgba(56, 189, 248, 0.15);
    }

    details {
        background-color: rgba(17, 24, 39, 0.85) !important;
        border: 1px solid rgba(192, 132, 252, 0.25) !important;
        border-radius: 12px !important;
        padding: 8px;
    }

    .stButton>button {
        background: linear-gradient(90deg, #06b6d4, #8b5cf6);
        color: white;
        border: none;
        border-radius: 12px;
        padding: 0.6rem 1.2rem;
        font-weight: 600;
        box-shadow: 0 0 12px rgba(139, 92, 246, 0.35);
    }

    .stButton>button:hover {
        transform: scale(1.02);
        transition: 0.2s ease-in-out;
    }
</style>
""", unsafe_allow_html=True)

# =========================
# HEADER
# =========================
st.markdown("""
<div style="
    padding: 1.2rem 1.5rem;
    border-radius: 18px;
    background: rgba(15, 23, 42, 0.75);
    border: 1px solid rgba(125, 211, 252, 0.25);
    box-shadow: 0 0 22px rgba(56, 189, 248, 0.18);
    margin-bottom: 1.2rem;
">
    <h1 style="margin-bottom:0.3rem;">Automated Stock Decision Engine</h1>
    <p style="font-size:1.05rem; color:#cbd5e1;">
        AI-powered stock monitoring dashboard with price trends, technical signals, and recommendation justifications.
    </p>
</div>
""", unsafe_allow_html=True)

# =========================
# MYSQL CONNECTION
# =========================
mysql_user = st.secrets["mysql_user"]
mysql_password = st.secrets["mysql_password"]
mysql_host = st.secrets["mysql_host"]
mysql_port = st.secrets["mysql_port"]
mysql_database = st.secrets["mysql_database"]

engine = create_engine(
    f"mysql+pymysql://{mysql_user}:{mysql_password}@{mysql_host}:{mysql_port}/{mysql_database}"
)

# =========================
# LOAD PRICE DATA
# =========================
price_query = """
SELECT ticker, trade_date, close_price
FROM stock_prices
ORDER BY ticker, trade_date
"""

df = pd.read_sql(price_query, engine)
df["trade_date"] = pd.to_datetime(df["trade_date"])
df = df.sort_values(["ticker", "trade_date"]).reset_index(drop=True)

df["ma10"] = df.groupby("ticker")["close_price"].transform(lambda x: x.rolling(10).mean())
df["ma50"] = df.groupby("ticker")["close_price"].transform(lambda x: x.rolling(50).mean())

# =========================
# LOAD RECOMMENDATIONS
# =========================
rec_query = """
SELECT ticker, recommendation_date, action, reason, justification
FROM stock_recommendations
ORDER BY recommendation_date DESC
"""

try:
    rec_df = pd.read_sql(rec_query, engine)
    rec_df["recommendation_date"] = pd.to_datetime(rec_df["recommendation_date"])

    for col in ["ticker", "action", "reason", "justification"]:
        rec_df[col] = rec_df[col].fillna("").astype(str).str.strip()

except Exception as e:
    st.error(f"Error loading recommendations: {e}")
    rec_df = pd.DataFrame(
        columns=["ticker", "recommendation_date", "action", "reason", "justification"]
    )

# =========================
# TOP METRICS
# =========================
if not rec_df.empty:
    latest_rec_all = rec_df.sort_values("recommendation_date", ascending=False)
    latest_rec_all = latest_rec_all.drop_duplicates(subset=["ticker"], keep="first")

    buy_count = (latest_rec_all["action"].str.lower() == "buy").sum()
    sell_count = (latest_rec_all["action"].str.lower() == "sell").sum()
    hold_count = (latest_rec_all["action"].str.lower() == "hold").sum()

    col1, col2, col3 = st.columns(3)
    col1.metric("Buy Signals", buy_count)
    col2.metric("Sell Signals", sell_count)
    col3.metric("Hold Signals", hold_count)

# =========================
# LATEST RECOMMENDATIONS TABLE
# =========================
st.markdown("## Latest AI Recommendations")

if not rec_df.empty:
    latest_rec = rec_df.sort_values("recommendation_date", ascending=False)
    latest_rec = latest_rec.drop_duplicates(subset=["ticker"], keep="first")
    latest_rec = latest_rec[
        ["ticker", "recommendation_date", "action", "reason", "justification"]
    ]
    st.dataframe(latest_rec, use_container_width=True)
else:
    st.warning("No recommendations found yet. Run your decision engine script first.")

# =========================
# STOCK SELECTOR
# =========================
st.markdown("## Market Signal Visualization")

tickers = sorted(df["ticker"].unique().tolist())
selected_ticker = st.selectbox("Select a stock", tickers)

ticker_df = df[df["ticker"] == selected_ticker].copy()

# =========================
# PRICE CHART
# =========================
fig = go.Figure()

fig.add_trace(go.Scatter(
    x=ticker_df["trade_date"],
    y=ticker_df["close_price"],
    mode="lines",
    name="Close Price"
))

fig.add_trace(go.Scatter(
    x=ticker_df["trade_date"],
    y=ticker_df["ma10"],
    mode="lines",
    name="MA10"
))

fig.add_trace(go.Scatter(
    x=ticker_df["trade_date"],
    y=ticker_df["ma50"],
    mode="lines",
    name="MA50"
))

fig.update_layout(
    title=f"{selected_ticker} Price and Moving Averages",
    xaxis_title="Date",
    yaxis_title="Price",
    template="plotly_dark",
    height=500,
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(15,23,42,0.85)",
    font=dict(color="white"),
    title_font=dict(size=22, color="#7dd3fc"),
    xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.08)"),
    yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.08)"),
    legend=dict(
        bgcolor="rgba(0,0,0,0)",
        bordercolor="rgba(255,255,255,0.1)",
        borderwidth=1
    )
)

st.plotly_chart(fig, use_container_width=True)

# =========================
# LATEST SIGNAL FOR SELECTED STOCK
# =========================
st.markdown("## Latest Signal for Selected Stock")

if not rec_df.empty:
    selected_rec = rec_df[rec_df["ticker"] == selected_ticker].sort_values(
        "recommendation_date", ascending=False
    )

    if not selected_rec.empty:
        latest = selected_rec.iloc[0]

        action_lower = latest["action"].lower()
        if action_lower == "buy":
            action_color = "#22c55e"
        elif action_lower == "sell":
            action_color = "#ef4444"
        else:
            action_color = "#facc15"

        justification_text = latest["justification"] if latest["justification"] else "No justification available."

        st.markdown(f"""
        <div style="
            padding: 1.4rem;
            border-radius: 18px;
            background: rgba(15, 23, 42, 0.85);
            border: 1px solid rgba(192, 132, 252, 0.25);
            box-shadow: 0 0 20px rgba(139, 92, 246, 0.18);
            margin-top: 1rem;
        ">
            <h3 style="margin-top:0; color:#7dd3fc;">Latest Signal for {latest['ticker']}</h3>
            <p><b>Ticker:</b> {latest['ticker']}</p>
            <p><b>Recommendation Date:</b> {latest['recommendation_date'].date()}</p>
            <p><b>Action:</b> <span style="color:{action_color}; font-weight:700;">{latest['action']}</span></p>
            <p><b>Reason:</b> {latest['reason']}</p>
            <p><b>Justification:</b> {justification_text}</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.info("No recommendation found for this stock yet.")
else:
    st.info("No recommendation data available.")

# =========================
# RAW DATA
# =========================
with st.expander("Show Raw Price Data"):
    st.dataframe(ticker_df, use_container_width=True)
