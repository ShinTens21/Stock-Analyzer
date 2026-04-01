import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import plotly.graph_objects as go

# =========================
# PAGE SETTINGS
# =========================
st.set_page_config(page_title="Automated Stock Decision Engine", layout="wide")

st.title("Automated Stock Decision Engine")
st.write(
    "This app displays stock price data, automated Buy / Hold / Sell recommendations, "
    "and supporting indicator analysis."
)

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

# =========================
# CALCULATE INDICATORS
# =========================
df["ma10"] = df.groupby("ticker")["close_price"].transform(lambda x: x.rolling(10).mean())
df["ma50"] = df.groupby("ticker")["close_price"].transform(lambda x: x.rolling(50).mean())

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

df["daily_return"] = df.groupby("ticker")["close_price"].pct_change()
df["volatility"] = df.groupby("ticker")["daily_return"].transform(lambda x: x.rolling(10).std())
df["rsi"] = df.groupby("ticker")["close_price"].transform(lambda x: calculate_rsi(x, 14))

# =========================
# LOAD RECOMMENDATIONS
# =========================
rec_query = """
SELECT id, ticker, recommendation_date, action, reason, justification
FROM stock_recommendations
ORDER BY id DESC
"""

try:
    rec_df = pd.read_sql(rec_query, engine)
    rec_df["recommendation_date"] = pd.to_datetime(rec_df["recommendation_date"])
except Exception:
    rec_df = pd.DataFrame(
        columns=["id", "ticker", "recommendation_date", "action", "reason", "justification"]
    )

# =========================
# SHOW LATEST RECOMMENDATIONS
# =========================
st.subheader("Latest Recommendations")

if not rec_df.empty:
    latest_rec = rec_df.sort_values("id", ascending=False)
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
st.subheader("Stock Price Chart")

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
    template="plotly_white",
    height=500
)

st.plotly_chart(fig, use_container_width=True)

# =========================
# RSI + VOLATILITY ANALYSIS
# =========================
st.subheader("RSI and Volatility Analysis")

indicator_df = ticker_df[["trade_date", "close_price", "rsi", "volatility"]].copy()
indicator_df = indicator_df.sort_values("trade_date", ascending=False)

latest_indicator = indicator_df.dropna().iloc[0] if not indicator_df.dropna().empty else None

if latest_indicator is not None:
    m1, m2 = st.columns(2)
    m1.metric("Latest RSI", f"{latest_indicator['rsi']:.2f}")
    m2.metric("Latest 10-Day Volatility", f"{latest_indicator['volatility']:.4f}")

col1, col2 = st.columns(2)

with col1:
    st.markdown("### RSI Table")
    rsi_table = indicator_df[["trade_date", "close_price", "rsi"]].copy()
    rsi_table["trade_date"] = rsi_table["trade_date"].dt.date
    rsi_table["close_price"] = rsi_table["close_price"].round(2)
    rsi_table["rsi"] = rsi_table["rsi"].round(2)
    st.dataframe(rsi_table.head(15), use_container_width=True)

with col2:
    st.markdown("### Volatility Table")
    vol_table = indicator_df[["trade_date", "close_price", "volatility"]].copy()
    vol_table["trade_date"] = vol_table["trade_date"].dt.date
    vol_table["close_price"] = vol_table["close_price"].round(2)
    vol_table["volatility"] = vol_table["volatility"].round(4)
    st.dataframe(vol_table.head(15), use_container_width=True)

# =========================
# SHOW LATEST SIGNAL FOR SELECTED STOCK
# =========================
st.subheader("Latest Signal for Selected Stock")

if not rec_df.empty:
    selected_rec = rec_df[rec_df["ticker"] == selected_ticker].sort_values(
        "id", ascending=False
    )

    if not selected_rec.empty:
        latest = selected_rec.iloc[0]

        st.markdown(f"**Ticker:** {latest['ticker']}")
        st.markdown(f"**Recommendation Date:** {latest['recommendation_date'].date()}")
        st.markdown(f"**Action:** {latest['action']}")
        st.markdown(f"**Reason:** {latest['reason']}")

        st.markdown("**Justification:**")
        if pd.notna(latest["justification"]):
            st.info(latest["justification"])
        else:
            st.warning("No justification available for this row yet.")
    else:
        st.info("No recommendation found for this stock yet.")
else:
    st.info("No recommendation data available.")

# =========================
# RAW DATA
# =========================
with st.expander("Show Raw Price Data"):
    raw_display = ticker_df.copy()
    raw_display["trade_date"] = raw_display["trade_date"].dt.date
    st.dataframe(raw_display, use_container_width=True)
