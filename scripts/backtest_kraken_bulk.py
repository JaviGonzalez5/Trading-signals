"""
Paso 1 del plan (validar la estrategia) — versión con histórico real de 2
años. La API pública de OHLC de Kraken (backtest_kraken.py) resultó estar
limitada a los últimos ~30 días pese a pedir `since` más atrás (Kraken no
garantiza profundidad histórica ahí). Kraken sí publica trimestralmente
archivos ZIP oficiales con histórico completo OHLCVT por par — este script
descarga los últimos ~8 trimestres, extrae solo el CSV de velas de 60 min
(1h) del par que interesa, y corre el backtest real
(strategy/core.py + backtest/engine.py, sin reimplementar nada).

Script de un solo uso — no forma parte del sistema en marcha.
"""

import io
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import requests

from backtest.engine import simulate_trades, summarize
from strategy.core import generate_signals

# Últimos ~8 trimestres (~2 años) hacia atrás desde ahora (2026-09).
QUARTERS = [
    "2024Q4", "2025Q1", "2025Q2", "2025Q3", "2025Q4", "2026Q1", "2026Q2", "2026Q3",
]
BASE_URL = "https://assets.kraken.com/marketing/institutions/Kraken_OHLCVT_{q}.zip"

PAIRS = {
    "BTC": "XBTUSD",
    "ETH": "ETHUSD",
    "XAUUSD (proxy PAXG)": "PAXGUSD",
}


def download_quarter_pair(quarter: str, pair_prefix: str) -> pd.DataFrame | None:
    url = BASE_URL.format(q=quarter)
    try:
        resp = requests.get(url, timeout=180)
    except Exception as e:
        print(f"  {quarter}: error de red: {e}", flush=True)
        return None
    if resp.status_code != 200:
        print(f"  {quarter}: HTTP {resp.status_code} (puede que ese trimestre no exista todavía)", flush=True)
        return None

    try:
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
    except Exception as e:
        print(f"  {quarter}: zip inválido ({e})", flush=True)
        return None

    candidates = [n for n in zf.namelist() if n.startswith(f"{pair_prefix}_60") and n.endswith(".csv")]
    if not candidates:
        print(f"  {quarter}: sin archivo de 60min para {pair_prefix}", flush=True)
        return None

    with zf.open(candidates[0]) as f:
        df = pd.read_csv(f, header=None, names=["ts", "Open", "High", "Low", "Close", "Volume", "trades"])
    df.index = pd.to_datetime(df["ts"], unit="s", utc=True)
    print(f"  {quarter}: {len(df)} velas", flush=True)
    return df[["Open", "High", "Low", "Close", "Volume"]]


def fetch_full_history(pair_prefix: str) -> pd.DataFrame:
    frames = []
    for q in QUARTERS:
        df = download_quarter_pair(q, pair_prefix)
        if df is not None and not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    full = pd.concat(frames)
    full = full[~full.index.duplicated(keep="first")].sort_index()
    return full


def run() -> None:
    for name, pair in PAIRS.items():
        print(f"\n{'=' * 50}", flush=True)
        print(f"  {name} ({pair})", flush=True)
        print(f"{'=' * 50}", flush=True)

        df = fetch_full_history(pair)
        if df.empty:
            print("  Sin datos disponibles.", flush=True)
            continue

        print(f"  Velas totales: {len(df)} | {df.index[0]} -> {df.index[-1]}", flush=True)

        df = generate_signals(df)
        trades = simulate_trades(df)
        stats = summarize(trades)
        for k, v in stats.items():
            print(f"  {k}: {v}", flush=True)


if __name__ == "__main__":
    run()
