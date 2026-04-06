import os
import pandas as pd
import yfinance as yf
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta

MYSQLHOST = os.getenv("MYSQLHOST")
MYSQLPORT = os.getenv("MYSQLPORT", "3306")
MYSQLUSER = os.getenv("MYSQLUSER")
MYSQLPASSWORD = os.getenv("MYSQLPASSWORD")
MYSQLDATABASE = os.getenv("MYSQLDATABASE")

engine = create_engine(
    f"mysql+pymysql://{MYSQLUSER}:{MYSQLPASSWORD}@{MYSQLHOST}:{MYSQLPORT}/{MYSQLDATABASE}"
)

TICKERS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "NFLX", "JPM", "PLTR"]

def update_prices():
    end = datetime.utcnow().date() + timedelta(days=1)
    start = datetime.utcnow().date() - timedelta(days=30)

    data = yf.download(
        TICKERS,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        auto_adjust=False,
        group_by="ticker",
        progress=False,
    )

    rows = []
    for ticker in TICKERS:
        if ticker not in data:
            continue

        df_t = data[ticker].reset_index()

        for _, r in df_t.iterrows():
            rows.append({
                "ticker": ticker,
                "trade_date": pd.to_datetime(r["Date"]).to_pydatetime(),
                "open_price": float(r["Open"]) if pd.notna(r["Open"]) else None,
                "high_price": float(r["High"]) if pd.notna(r["High"]) else None,
                "low_price": float(r["Low"]) if pd.notna(r["Low"]) else None,
                "close_price": float(r["Close"]) if pd.notna(r["Close"]) else None,
                "adj_close_price": float(r["Adj Close"]) if "Adj Close" in r and pd.notna(r["Adj Close"]) else None,
                "volume": float(r["Volume"]) if pd.notna(r["Volume"]) else None,
            })

    out = pd.DataFrame(rows)
    if out.empty:
        print("No price rows downloaded.")
        return

    # simple overlap cleanup
    min_date = out["trade_date"].min()
    max_date = out["trade_date"].max()

    with engine.begin() as conn:
        conn.execute(
            text("""
                DELETE FROM stock_prices
                WHERE trade_date BETWEEN :min_date AND :max_date
            """),
            {"min_date": min_date, "max_date": max_date}
        )

    out.to_sql("stock_prices", engine, if_exists="append", index=False)
    print(f"Inserted {len(out)} rows into stock_prices")

if __name__ == "__main__":
    update_prices()
