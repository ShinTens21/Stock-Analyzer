import yfinance as yf
import pandas as pd
from sqlalchemy import create_engine
from datetime import datetime

# =========================
# 1. SETTINGS
# =========================
tickers = ["AAPL", "MSFT", "NVDA", "TSLA","GOOGL", "AMZN", "META", "PLTR", "NFLX", "V", "JPM", "C", "WMT"]
start_date = "2010-01-01"
end_date = datetime.today().strftime("%Y-%m-%d")

mysql_user = "root"
mysql_password = "Az14gamer123%"
mysql_host = "localhost"
mysql_port = "3306"
mysql_database = "stocks_database"

# =========================
# 2. DOWNLOAD DATA
# =========================
raw_data = yf.download(
    tickers=tickers,
    start=start_date,
    end=end_date,
    auto_adjust=False,
    group_by="ticker"
)

# =========================
# 3. RESHAPE DATA
# =========================
all_data = []

for ticker in tickers:
    temp = raw_data[ticker].copy()
    temp["ticker"] = ticker
    temp = temp.reset_index()
    all_data.append(temp)

df = pd.concat(all_data, ignore_index=True)

# Rename columns to match MySQL table
df = df.rename(columns={
    "Date": "trade_date",
    "Open": "open_price",
    "High": "high_price",
    "Low": "low_price",
    "Close": "close_price",
    "Adj Close": "adj_close_price",
    "Volume": "volume"
})

# Keep only needed columns
df = df[
    [
        "ticker",
        "trade_date",
        "open_price",
        "high_price",
        "low_price",
        "close_price",
        "adj_close_price",
        "volume"
    ]
]

# Remove rows with missing values
df = df.dropna()

# =========================
# 4. CONNECT TO MYSQL
# =========================
engine = create_engine(
    f"mysql+pymysql://{mysql_user}:{mysql_password}@{mysql_host}:{mysql_port}/{mysql_database}"
)

# =========================
# 5. INSERT INTO MYSQL
# =========================
df.to_sql(
    name="stock_prices",
    con=engine,
    if_exists="replace",
    index=False
)

print("Stock data inserted into MySQL successfully.")
print(df.head())
#=========================
# 6. ANALYZE DATA
#=========================
