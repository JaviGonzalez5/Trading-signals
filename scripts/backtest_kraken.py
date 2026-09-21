"""
Paso 1 del plan (validar la estrategia) — corrido desde Railway porque el
sandbox de desarrollo no tiene salida a APIs financieras (ver README).
Descarga ~2 años de velas 1h de Kraken (misma fuente que usa el worker en
producción) para BTC, ETH y el proxy PAXG del oro, y corre el backtest
real (strategy/core.py + backtest/engine.py, sin reimplementar nada) sobre
datos históricos de verdad.

Script de un solo uso — no forma parte del sistema en marcha.
"""

import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from backtest.engine import simulate_trades, summarize
from strategy.core import generate_signals
from worker.data_sources import fetch_kraken_klines

ASSETS = {
    "BTC": "XBTUSD",
    "ETH": "ETHUSD",
    "XAUUSD (proxy PAXG)": "PAXGUSD",
}

YEARS_BACK = 2
INTERVAL = "1h"


def fetch_full_history(pair: str) -> pd.DataFrame:
    since = int(datetime.now(timezone.utc).timestamp()) - YEARS_BACK * 365 * 24 * 3600
    frames = []
    last_since = None

    while True:
        df = fetch_kraken_klines(pair, interval=INTERVAL, since=since)
        if df.empty:
            break
        frames.append(df)

        new_since = int(df.index[-1].timestamp())
        if last_since is not None and new_since <= last_since:
            break  # sin progreso, evita bucle infinito
        last_since = new_since
        since = new_since

        if new_since >= int(datetime.now(timezone.utc).timestamp()) - 3600:
            break  # ya llegamos casi al presente

        time.sleep(1)  # respeta el rate limit público de Kraken

    if not frames:
        return pd.DataFrame()

    full = pd.concat(frames)
    full = full[~full.index.duplicated(keep="first")].sort_index()
    return full


def run() -> None:
    for name, pair in ASSETS.items():
        print(f"\n{'=' * 50}")
        print(f"  {name} ({pair})")
        print(f"{'=' * 50}")

        df = fetch_full_history(pair)
        if df.empty:
            print("  Sin datos disponibles.")
            continue

        print(f"  Velas: {len(df)} | {df.index[0]} -> {df.index[-1]}")

        df = generate_signals(df)
        trades = simulate_trades(df)
        stats = summarize(trades)
        for k, v in stats.items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    run()
