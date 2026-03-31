import pandas as pd
import numpy as np
from sqlalchemy import create_engine

# =========================
# 1. MYSQL CONNECTION
# =========================
mysql_user = "root"
mysql_password = "Az14gamer123%"
mysql_host = "localhost"
mysql_port = "3306"
mysql_database = "stocks_database"

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
# 3. RSI FUNCTION
# =========================
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss
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
# 6. DECISION RULES
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
            "At least 50 trading days are needed for MA50 and 14 trading days for RSI."
        )

    if volatility > 0.04:
        return (
            "Avoid",
            "Volatility is too high.",
            f"10-day volatility is {volatility:.4f}, which is above the 0.04 threshold. This suggests price swings are unusually large and risk is elevated."
        )

    if ma10 > ma50 and rsi < 70:
        return (
            "Buy",
            "Short-term momentum is stronger than long-term trend and RSI is not overbought.",
            f"MA10 is {ma10:.2f} while MA50 is {ma50:.2f}, so recent momentum is stronger than the broader trend. RSI is {rsi:.2f}, which is below 70, so the stock is not overbought."
        )

    if ma10 < ma50:
        return (
            "Sell",
            "Short-term momentum is weaker than long-term trend.",
            f"MA10 is {ma10:.2f} while MA50 is {ma50:.2f}. Because the 10-day moving average is below the 50-day moving average, the recent trend is weaker than the longer-term trend, which supports a sell signal."
        )

    if ma10 > ma50 and rsi >= 70:
        return (
            "Hold",
            "Trend is positive but RSI suggests the stock may be overbought.",
            f"MA10 is {ma10:.2f} and MA50 is {ma50:.2f}, which supports an upward trend. However, RSI is {rsi:.2f}, at or above 70, which suggests overbought conditions."
        )

    return (
        "Hold",
        "No strong buy or sell signal.",
        f"Indicators are mixed: MA10 = {ma10:.2f}, MA50 = {ma50:.2f}, RSI = {rsi:.2f}, volatility = {volatility:.4f}."
    )

latest_df[["action", "reason", "justification"]] = latest_df.apply(
    lambda row: pd.Series(make_decision(row)),
    axis=1
)

recommendations = latest_df[
    ["ticker", "trade_date", "action", "reason", "justification"]
].copy()

recommendations = recommendations.rename(columns={"trade_date": "recommendation_date"})

print(recommendations)

# =========================
# 8. SAVE TO MYSQL
# =========================
recommendations.to_sql(
    name="stock_recommendations",
    con=engine,
    if_exists="append",
    index=False
)

print("Recommendations saved successfully.")