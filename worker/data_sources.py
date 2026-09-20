"""
Descarga de velas por activo, normalizadas al mismo formato que usa
strategy/core.py (columnas Open/High/Low/Close/Volume, index de fechas UTC)
— así generate_signals() funciona igual aquí que en el backtest.
"""

import pandas as pd
import requests
import yfinance as yf

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
BINANCE_KLINES_LIMIT = 500  # suficiente para EMA200 + margen


def fetch_binance_klines(ticker: str, interval: str = "1h") -> pd.DataFrame:
    resp = requests.get(
        BINANCE_KLINES_URL,
        params={"symbol": ticker, "interval": interval, "limit": BINANCE_KLINES_LIMIT},
        timeout=15,
    )
    resp.raise_for_status()
    raw = resp.json()
    if not raw:
        return pd.DataFrame()

    df = pd.DataFrame(raw, columns=[
        "open_time", "Open", "High", "Low", "Close", "Volume",
        "close_time", "quote_asset_volume", "num_trades",
        "taker_buy_base", "taker_buy_quote", "ignore",
    ])
    df[["Open", "High", "Low", "Close", "Volume"]] = df[
        ["Open", "High", "Low", "Close", "Volume"]
    ].astype(float)
    df.index = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    return df[["Open", "High", "Low", "Close", "Volume"]]


def fetch_yfinance_klines(ticker: str, interval: str = "1h") -> pd.DataFrame:
    # 60d es el máximo que yfinance permite para velas de 1h.
    df = yf.download(ticker, period="60d", interval=interval, progress=False, auto_adjust=True)
    if df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.index = pd.to_datetime(df.index, utc=True)
    return df[["Open", "High", "Low", "Close", "Volume"]]


def fetch_candles(asset: dict) -> pd.DataFrame:
    """asset viene de la tabla `assets`: symbol, data_source, source_ticker, timeframe."""
    source = asset["data_source"]
    ticker = asset.get("source_ticker") or asset["symbol"]
    timeframe = asset.get("timeframe") or "1h"

    if source == "binance":
        return fetch_binance_klines(ticker, interval=timeframe)
    if source == "yfinance":
        return fetch_yfinance_klines(ticker, interval=timeframe)

    raise ValueError(
        f"Fuente de datos '{source}' no soportada todavía "
        f"(activo {asset['symbol']}) — pendiente de decidir (p.ej. Interactive Brokers)."
    )
