"""
Valida el cierre parcial (TP original + resto con salida Turtle) contra la
preocupación real del usuario: con la salida Turtle pura el win rate cae
mucho (BTC 48%->33%, XAUUSD 50%->35-42%). Prueba 30/50/70% de cierre
parcial en BTC (canal 20) y XAUUSD (horario real + canal 10) — las dos
combinaciones que ya mejoraban limpio con salida Turtle pura — para ver
cuánto sube el win rate y cuánto retorno se sacrifica a cambio.

Script de un solo uso — no forma parte del sistema en marcha.
"""

import io
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import requests

import strategy.core as core
from backtest.engine import apply_circuit_breaker, filter_non_overlapping, simulate_trades, summarize

QUARTERS = [
    "2024Q4", "2025Q1", "2025Q2", "2025Q3", "2025Q4", "2026Q1", "2026Q2", "2026Q3",
]
BASE_URL = "https://assets.kraken.com/marketing/institutions/Kraken_OHLCVT_{q}.zip"


def download_quarter_pair(quarter: str, pair_prefix: str, minute_suffix: str) -> pd.DataFrame | None:
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
    candidates = [n for n in zf.namelist() if n.startswith(f"{pair_prefix}_{minute_suffix}") and n.endswith(".csv")]
    if not candidates:
        return None
    with zf.open(candidates[0]) as f:
        df = pd.read_csv(f, header=None, names=["ts", "Open", "High", "Low", "Close", "Volume", "trades"])
    df.index = pd.to_datetime(df["ts"], unit="s", utc=True)
    return df[["Open", "High", "Low", "Close", "Volume"]]


def fetch_full_history(pair_prefix: str, minute_suffix: str) -> pd.DataFrame:
    frames = [download_quarter_pair(q, pair_prefix, minute_suffix) for q in QUARTERS]
    frames = [f for f in frames if f is not None and not f.empty]
    if not frames:
        return pd.DataFrame()
    full = pd.concat(frames)
    return full[~full.index.duplicated(keep="first")].sort_index()


def realistic_stats(df: pd.DataFrame, max_bars_forward: int, trailing_exit_lookback=None, partial_tp_at=None) -> dict:
    trades = simulate_trades(
        df, max_bars_forward=max_bars_forward,
        trailing_exit_lookback=trailing_exit_lookback, partial_tp_at=partial_tp_at,
    )
    trades = filter_non_overlapping(trades)
    trades = apply_circuit_breaker(trades)
    return summarize(trades)


def run() -> None:
    print(f"\n{'=' * 60}", flush=True)
    print("  BTC (XBTUSD) — TP fijo vs Turtle-20 vs Turtle-20 + parcial", flush=True)
    print(f"{'=' * 60}", flush=True)
    raw_btc = fetch_full_history("XBTUSD", "60")
    stats_fixed = realistic_stats(raw_btc.pipe(core.generate_signals), 200)
    print(f"  [TP fijo] {stats_fixed}", flush=True)
    df_btc = core.generate_signals(raw_btc.copy())
    stats_trail = realistic_stats(df_btc, 200, trailing_exit_lookback=20)
    print(f"  [Turtle-20 puro] {stats_trail}", flush=True)
    for frac in (0.3, 0.5, 0.7):
        stats = realistic_stats(df_btc, 200, trailing_exit_lookback=20, partial_tp_at=frac)
        print(f"  [Turtle-20 + parcial {int(frac*100)}%] {stats}", flush=True)

    print(f"\n{'=' * 60}", flush=True)
    print("  XAUUSD (PAXGUSD) — TP fijo vs horario+Turtle-10 vs +parcial", flush=True)
    print(f"{'=' * 60}", flush=True)
    raw_xau = fetch_full_history("PAXGUSD", "60")
    raw_xau_4h = fetch_full_history("PAXGUSD", "240")
    df_xau_fixed = core.generate_signals(raw_xau.copy(), htf_df=raw_xau_4h)
    stats_fixed = realistic_stats(df_xau_fixed, 200)
    print(f"  [TP fijo] {stats_fixed}", flush=True)
    df_xau = core.generate_signals(raw_xau.copy(), htf_df=raw_xau_4h, exclude_gold_market_closed=True)
    stats_trail = realistic_stats(df_xau, 200, trailing_exit_lookback=10)
    print(f"  [horario real + Turtle-10 puro] {stats_trail}", flush=True)
    for frac in (0.3, 0.5, 0.7):
        stats = realistic_stats(df_xau, 200, trailing_exit_lookback=10, partial_tp_at=frac)
        print(f"  [horario real + Turtle-10 + parcial {int(frac*100)}%] {stats}", flush=True)


if __name__ == "__main__":
    run()
