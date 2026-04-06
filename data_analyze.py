import os
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from datetime import datetime

# =========================
# 1. MYSQL CONNECTION
# =========================
MYSQLHOST = os.getenv("MYSQLHOST")
MYSQLPORT = os.getenv("MYSQLPORT", "3306")
MYSQLUSER = os.getenv("MYSQLUSER")
MYSQLPASSWORD = os.getenv("MYSQLPASSWORD")
MYSQLDATABASE = os.getenv("MYSQLDATABASE")

required_vars = {
    "MYSQLHOST": MYSQLHOST,
    "MYSQLUSER": MYSQLUSER,
    "MYSQLPASSWORD": MYSQLPASSWORD,
    "MYSQLDATABASE": MYSQLDATABASE,
}
missing = [k for k, v in required_vars.items() if not v]
if missing:
    raise ValueError(f"Missing environment variables: {', '.join(missing)}")

engine = create_engine(
    f"mysql+pymysql://{MYSQLUSER}:{MYSQLPASSWORD}@{MYSQLHOST}:{MYSQLPORT}/{MYSQLDATABASE}"
)

# =========================
# 2. LOAD PRICE DATA
# =========================
query = """
SELECT ticker, trade_date, close_price
FROM stock_prices
ORDER BY ticker, trade_date
"""

df = pd.read_sql(query, engine)
df["trade_date"] = pd.to_datetime(df["trade_date"])
df = df.sort_values(["ticker", "trade_date"]).reset_index(drop=True)

if df.empty:
    raise ValueError("stock_prices table is empty")

print("Latest stock_prices date:", df["trade_date"].max())

# =========================
# 3. RSI FUNCTION
# =========================
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi

# =========================
# 4. BUILD INDICATORS
# =========================
df["ma10"] = df.groupby("ticker")["close_price"].transform(
    lambda x: x.rolling(10).mean()
)
df["ma50"] = df.groupby("ticker")["close_price"].transform(
    lambda x: x.rolling(50).mean()
)
df["rsi"] = df.groupby("ticker")["close_price"].transform(calculate_rsi)

df["daily_return"] = df.groupby("ticker")["close_price"].pct_change()
df["volatility_10"] = df.groupby("ticker")["daily_return"].transform(
    lambda x: x.rolling(10).std()
)

# keep latest row per ticker
latest = df.groupby("ticker", as_index=False).tail(1).copy()

if latest.empty:
    raise ValueError("No latest rows found per ticker")

print("Latest rows being analyzed:")
print(latest[["ticker", "trade_date", "close_price", "ma10", "ma50", "rsi"]])

# =========================
# 5. RECOMMENDATION LOGIC
# =========================
def get_action(row):
    if pd.isna(row["ma10"]) or pd.isna(row["ma50"]) or pd.isna(row["rsi"]):
        return "Hold"

    if row["ma10"] > row["ma50"] and row["rsi"] < 70:
        return "Buy"
    elif row["ma10"] < row["ma50"]:
        return "Sell"
    else:
        return "Hold"

def get_reason(row):
    if pd.isna(row["ma10"]) or pd.isna(row["ma50"]) or pd.isna(row["rsi"]):
        return "Not enough data to generate a full signal."

    if row["ma10"] > row["ma50"] and row["rsi"] < 70:
        return "Short-term momentum is stronger than long-term trend and RSI is not overbought."
    elif row["ma10"] < row["ma50"]:
        return "Short-term momentum is weaker than long-term trend."
    else:
        return "Momentum is mixed and no strong signal is present."

def get_justification(row):
    if pd.isna(row["ma10"]) or pd.isna(row["ma50"]) or pd.isna(row["rsi"]):
        return (
            f"Insufficient data for full indicator calculation. "
            f"MA10={row['ma10']}, MA50={row['ma50']}, RSI={row['rsi']}"
        )

    if row["ma10"] > row["ma50"] and row["rsi"] < 70:
        return (
            f"MA10 is {row['ma10']:.2f} while MA50 is {row['ma50']:.2f}, "
            f"so recent momentum is stronger than the broader trend. "
            f"RSI is {row['rsi']:.2f}, which is below 70 and suggests the stock is not overbought."
        )
    elif row["ma10"] < row["ma50"]:
        return (
            f"MA10 is {row['ma10']:.2f} while MA50 is {row['ma50']:.2f}. "
            f"Because the 10-day moving average is below the 50-day moving average, "
            f"short-term momentum is weaker than the longer-term trend. "
            f"RSI is {row['rsi']:.2f}."
        )
    else:
        return (
            f"MA10 is {row['ma10']:.2f} and MA50 is {row['ma50']:.2f}, "
            f"while RSI is {row['rsi']:.2f}. These signals do not show a strong directional edge."
        )

latest["action"] = latest.apply(get_action, axis=1)
latest["reason"] = latest.apply(get_reason, axis=1)
latest["justification"] = latest.apply(get_justification, axis=1)

# IMPORTANT:
# use the latest market date from stock_prices, not datetime.today()
latest["recommendation_date"] = latest["trade_date"]

recommendations = latest[
    ["ticker", "recommendation_date", "action", "reason", "justification"]
].copy()

print("Recommendations to insert:")
print(recommendations)

if recommendations.empty:
    raise ValueError("Recommendations DataFrame is empty")

# =========================
# 6. WRITE TO DATABASE
# =========================
with engine.begin() as conn:
    # remove old recommendation rows for the same recommendation date
    rec_date = recommendations["recommendation_date"].max()

    conn.execute(
        text("DELETE FROM recommendations WHERE recommendation_date = :rec_date"),
        {"rec_date": rec_date.to_pydatetime()}
    )

recommendations.to_sql("recommendations", engine, if_exists="append", index=False)
print(f"Inserted {len(recommendations)} rows into recommendations")

# =========================
# 7. VERIFY INSERT
# =========================
with engine.connect() as conn:
    latest_db_date = conn.execute(
        text("SELECT MAX(recommendation_date) FROM recommendations")
    ).scalar()
    total_rows = conn.execute(
        text("SELECT COUNT(*) FROM recommendations")
    ).scalar()

print("Latest recommendation_date in DB:", latest_db_date)
print("Total recommendation rows in DB:", total_rows)
