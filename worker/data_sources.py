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

KRAKEN_OHLC_URL = "https://api.kraken.com/0/public/OHLC"
# minutos por vela que acepta Kraken: 1,5,15,30,60,240,1440,10080,21600
KRAKEN_INTERVAL_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440}


def fetch_kraken_klines(pair: str, interval: str = "1h", since: int | None = None) -> pd.DataFrame:
    minutes = KRAKEN_INTERVAL_MINUTES.get(interval)
    if minutes is None:
        raise ValueError(f"Kraken no soporta el timeframe '{interval}'")

    params = {"pair": pair, "interval": minutes}
    if since is not None:
        params["since"] = since  # unix seconds; Kraken devuelve velas posteriores a esto

    resp = requests.get(KRAKEN_OHLC_URL, params=params, timeout=15)
    resp.raise_for_status()
    body = resp.json()
    if body.get("error"):
        raise RuntimeError(f"Kraken devolvió error para {pair}: {body['error']}")

    result = body.get("result", {})
    # La clave del par en la respuesta no siempre coincide con el pair pedido
    # (Kraken normaliza nombres, p.ej. XBTUSD -> XXBTZUSD) — cogemos la única
    # clave que no sea "last".
    rows = next((v for k, v in result.items() if k != "last"), None)
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=[
        "time", "Open", "High", "Low", "Close", "vwap", "Volume", "count",
    ])
    df[["Open", "High", "Low", "Close", "Volume"]] = df[
        ["Open", "High", "Low", "Close", "Volume"]
    ].astype(float)
    df.index = pd.to_datetime(df["time"], unit="s", utc=True)
    return df[["Open", "High", "Low", "Close", "Volume"]]


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

    if source == "kraken":
        return fetch_kraken_klines(ticker, interval=timeframe)
    if source == "binance":
        # Binance devuelve 451 desde IPs de proveedores cloud (Railway
        # incluido) — se deja el código por si algún día hace falta desde
        # otro entorno, pero ningún activo activo lo usa ahora mismo.
        return fetch_binance_klines(ticker, interval=timeframe)
    if source == "yfinance":
        # Observado colgándose sin error desde Railway (mismo bloqueo
        # anti-scraping de Yahoo que en el sandbox de desarrollo) — sin
        # timeout fiable disponible en yf.download(). No usar en producción
        # hasta resolverlo; sustituido por Kraken/IB según el activo.
        return fetch_yfinance_klines(ticker, interval=timeframe)

    raise ValueError(
        f"Fuente de datos '{source}' no soportada todavía "
        f"(activo {asset['symbol']}) — pendiente de decidir (p.ej. Interactive Brokers)."
    )


def fetch_htf_candles(asset: dict, interval: str = "4h") -> pd.DataFrame:
    """Velas de marco temporal superior para el filtro de tendencia (ver
    strategy/core.py::generate_signals, parámetro htf_df) — mismo activo,
    timeframe mayor. Solo Kraken por ahora (única fuente en producción)."""
    source = asset["data_source"]
    ticker = asset.get("source_ticker") or asset["symbol"]
    if source == "kraken":
        return fetch_kraken_klines(ticker, interval=interval)
    raise ValueError(f"fetch_htf_candles no soportado todavía para la fuente '{source}'")


def fetch_candles_since(asset: dict, since_ts) -> pd.DataFrame:
    """Velas posteriores a `since_ts` (datetime) — para revisar si una señal
    pasada ya tocó TP/SL. Solo soportado para Kraken por ahora (única fuente
    en producción)."""
    source = asset["data_source"]
    ticker = asset.get("source_ticker") or asset["symbol"]
    timeframe = asset.get("timeframe") or "1h"
    since_unix = int(pd.Timestamp(since_ts).timestamp())

    if source == "kraken":
        return fetch_kraken_klines(ticker, interval=timeframe, since=since_unix)

    raise ValueError(f"fetch_candles_since no soportado todavía para la fuente '{source}'")
