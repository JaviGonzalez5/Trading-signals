"""
Diagnóstico del backtest: no solo "cuánto gana/pierde" sino POR QUÉ.
Reutiliza la descarga de histórico de backtest_kraken_bulk.py (duplicada
aquí a propósito para que este script siga siendo autocontenido, mismo
criterio que los demás scripts/ de un solo uso) y desglosa cada backtest
por dirección, por RSI de entrada, por mes (¿pierde en meses concretos o
de forma constante?) y por rachas de pérdidas seguidas — para saber si el
problema es la estrategia en sí o un régimen de mercado concreto.

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
        return None
    try:
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
    except Exception:
        return None
    candidates = [n for n in zf.namelist() if n.startswith(f"{pair_prefix}_60") and n.endswith(".csv")]
    if not candidates:
        return None
    with zf.open(candidates[0]) as f:
        df = pd.read_csv(f, header=None, names=["ts", "Open", "High", "Low", "Close", "Volume", "trades"])
    df.index = pd.to_datetime(df["ts"], unit="s", utc=True)
    return df[["Open", "High", "Low", "Close", "Volume"]]


def fetch_full_history(pair_prefix: str) -> pd.DataFrame:
    frames = [download_quarter_pair(q, pair_prefix) for q in QUARTERS]
    frames = [f for f in frames if f is not None and not f.empty]
    if not frames:
        return pd.DataFrame()
    full = pd.concat(frames)
    return full[~full.index.duplicated(keep="first")].sort_index()


def diagnose(df: pd.DataFrame, trades: pd.DataFrame) -> None:
    if trades.empty:
        print("  Sin operaciones que diagnosticar.", flush=True)
        return

    trades = trades.copy()
    trades["rsi_at_entry"] = trades["entry_date"].map(df["rsi"])
    trades["month"] = pd.to_datetime(trades["entry_date"]).dt.to_period("M")
    trades = trades.sort_values("entry_date")

    print("\n  -- Por dirección --", flush=True)
    for direction in ["LONG", "SHORT"]:
        sub = trades[trades["direction"] == direction]
        if sub.empty:
            continue
        wins = (sub["outcome"] == "TP").sum()
        print(
            f"  {direction}: {len(sub)} trades, {wins}/{len(sub)} ganadas "
            f"({wins / len(sub) * 100:.1f}%), R total {sub['r_multiple'].sum():+.2f}",
            flush=True,
        )

    print("\n  -- Por RSI al entrar --", flush=True)
    bins = [0, 40, 50, 55, 60, 65, 100]
    labels = ["<40", "40-50", "50-55", "55-60", "60-65", ">65"]
    trades["rsi_bucket"] = pd.cut(trades["rsi_at_entry"], bins=bins, labels=labels)
    for bucket in labels:
        sub = trades[trades["rsi_bucket"] == bucket]
        if sub.empty:
            continue
        wins = (sub["outcome"] == "TP").sum()
        print(
            f"  RSI {bucket}: {len(sub)} trades, {wins}/{len(sub)} "
            f"({wins / len(sub) * 100:.1f}%), R total {sub['r_multiple'].sum():+.2f}",
            flush=True,
        )

    print("\n  -- Por mes --", flush=True)
    for month, sub in trades.groupby("month"):
        wins = (sub["outcome"] == "TP").sum()
        print(
            f"  {month}: {len(sub)} trades, {wins}/{len(sub)} "
            f"({wins / len(sub) * 100:.1f}%), R total {sub['r_multiple'].sum():+.2f}",
            flush=True,
        )

    print("\n  -- Rachas de pérdidas seguidas --", flush=True)
    max_streak = cur = 0
    for outcome in trades["outcome"]:
        if outcome == "SL":
            cur += 1
            max_streak = max(max_streak, cur)
        else:
            cur = 0
    print(f"  Racha máxima: {max_streak} pérdidas seguidas", flush=True)

    print("\n  -- Duración media de la operación (velas hasta resolverse) --", flush=True)
    wins_df = trades[trades["outcome"] == "TP"]
    losses_df = trades[trades["outcome"] == "SL"]
    if not wins_df.empty:
        print(f"  Ganadoras: {wins_df['bars_held'].mean():.1f} velas de media", flush=True)
    if not losses_df.empty:
        print(f"  Perdedoras: {losses_df['bars_held'].mean():.1f} velas de media", flush=True)


def run() -> None:
    for name, pair in PAIRS.items():
        print(f"\n{'=' * 60}", flush=True)
        print(f"  {name} ({pair})", flush=True)
        print(f"{'=' * 60}", flush=True)

        raw = fetch_full_history(pair)
        if raw.empty:
            print("  Sin datos disponibles.", flush=True)
            continue

        print(f"  Velas: {len(raw)} | {raw.index[0]} -> {raw.index[-1]}", flush=True)

        df = generate_signals(raw)
        trades = simulate_trades(df)
        stats = summarize(trades)
        print(f"  Resumen: {stats}", flush=True)

        diagnose(df, trades)


if __name__ == "__main__":
    run()
