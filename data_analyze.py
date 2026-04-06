import streamlit as st
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text

# =========================
# 1. MYSQL CONNECTION
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
# 2. LOAD STOCK DATA
# =========================
query = """
SELECT ticker, trade_date, close_price
FROM stock_prices
ORDER BY ticker, trade_date
"""

df = pd.read_sql(query, engine)

df["trade_date"] = pd.to_datetime(df["trade_date"])
df = df.sort_values(["ticker", "trade_date"]).reset_index(drop=True)

# =========================
# 3. RSI FUNCTION (SMOOTHER VERSION)
# =========================
def calculate_rsi(series, period=14):
    delta = series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    return rsi

# =========================
# 4. CALCULATE INDICATORS
# =========================
df["ma10"] = df.groupby("ticker")["close_price"].transform(lambda x: x.rolling(10).mean())
df["ma50"] = df.groupby("ticker")["close_price"].transform(lambda x: x.rolling(50).mean())
df["daily_return"] = df.groupby("ticker")["close_price"].pct_change()
df["volatility"] = df.groupby("ticker")["daily_return"].transform(lambda x: x.rolling(10).std())
df["rsi"] = df.groupby("ticker")["close_price"].transform(calculate_rsi)

# =========================
# 5. KEEP LATEST ROW PER STOCK
# =========================
latest_df = df.groupby("ticker").tail(1).copy()

# =========================
# 6. DECISION RULES (SCORE-BASED)
# =========================
def make_decision(row):
    ma10 = row["ma10"]
    ma50 = row["ma50"]
    rsi = row["rsi"]
    volatility = row["volatility"]
    close_price = row["close_price"]

    if pd.isna(ma10) or pd.isna(ma50) or pd.isna(rsi) or pd.isna(volatility):
        return (
            "Insufficient Data",
            "Not enough historical data to calculate indicators.",
            "At least 50 trading days are needed for MA50, 10 trading days for volatility, and 14 trading days for RSI.",
            0
        )

    score = 0
    signals = []

    # -------------------------
    # Trend
    # -------------------------
    if ma10 > ma50:
        score += 2
        signals.append(
            f"MA10 ({ma10:.2f}) is above MA50 ({ma50:.2f}), which suggests the short-term trend is stronger than the long-term trend."
        )
    else:
        score -= 2
        signals.append(
            f"MA10 ({ma10:.2f}) is below MA50 ({ma50:.2f}), which suggests the recent trend is weaker than the longer-term trend."
        )

    # -------------------------
    # Price confirmation
    # -------------------------
    if close_price > ma10:
        score += 1
        signals.append(
            f"Close price ({close_price:.2f}) is above MA10, confirming short-term price strength."
        )
    else:
        score -= 1
        signals.append(
            f"Close price ({close_price:.2f}) is below MA10, showing short-term weakness."
        )

    # -------------------------
    # RSI momentum
    # -------------------------
    if 40 <= rsi <= 65:
        score += 2
        signals.append(
            f"RSI is {rsi:.2f}, which is in a healthy bullish range and not yet overbought."
        )
    elif 65 < rsi < 70:
        score += 1
        signals.append(
            f"RSI is {rsi:.2f}, which is still bullish but getting close to overbought territory."
        )
    elif 70 <= rsi <= 80:
        score -= 1
        signals.append(
            f"RSI is {rsi:.2f}, which suggests the stock may be overbought."
        )
    elif rsi < 30:
        score -= 1
        signals.append(
            f"RSI is {rsi:.2f}, which indicates oversold conditions and possible weakness."
        )
    else:
        signals.append(
            f"RSI is {rsi:.2f}, which suggests neutral to weak momentum."
        )

    # -------------------------
    # Volatility risk
    # -------------------------
    if volatility < 0.02:
        score += 1
        signals.append(
            f"10-day volatility is {volatility:.4f}, which is relatively low and implies lower short-term risk."
        )
    elif 0.02 <= volatility <= 0.04:
        signals.append(
            f"10-day volatility is {volatility:.4f}, which is moderate and acceptable."
        )
    else:
        score -= 2
        signals.append(
            f"10-day volatility is {volatility:.4f}, which is high and increases risk."
        )

    # -------------------------
    # Final decision
    # -------------------------
    if score >= 5:
        action = "Strong Buy"
        reason = "Trend, momentum, and risk conditions are strongly supportive."
    elif score >= 3:
        action = "Buy"
        reason = "Most indicators support upside potential."
    elif score >= 1:
        action = "Hold"
        reason = "Signals are somewhat positive but not strong enough for a buy."
    elif score >= -1:
        action = "Sell"
        reason = "Weakness is appearing in the trend and momentum."
    else:
        action = "Avoid"
        reason = "Risk is high or the trend is too weak."

    justification = " ".join(signals) + f" Final score = {score}."

    return action, reason, justification, score

latest_df[["action", "reason", "justification", "score"]] = latest_df.apply(
    lambda row: pd.Series(make_decision(row)),
    axis=1
)

# =========================
# 7. PREPARE RECOMMENDATIONS
# =========================
recommendations = latest_df[
    [
        "ticker",
        "trade_date",
        "close_price",
        "ma10",
        "ma50",
        "rsi",
        "volatility",
        "score",
        "action",
        "reason",
        "justification"
    ]
].copy()

recommendations = recommendations.rename(columns={"trade_date": "recommendation_date"})

print(recommendations)

# =========================
# 8. OPTIONAL: REMOVE TODAY'S OLD RECOMMENDATIONS
# =========================
# This prevents duplicate entries if you run the script multiple times in one day.
with engine.begin() as conn:
    conn.execute(text("""
        DELETE FROM stock_recommendations
        WHERE recommendation_date IN (
            SELECT latest_date FROM (
                SELECT MAX(DATE(recommendation_date)) AS latest_date
                FROM stock_recommendations
            ) AS temp
        )
    """))

# =========================
# 9. SAVE TO MYSQL
# =========================
recommendations.to_sql(
    name="stock_recommendations",
    con=engine,
    if_exists="append",
    index=False
)

print("Recommendations saved successfully.")
