"""
Retoma el hallazgo pendiente del barrido de parámetros
(scripts/backtest_param_sweep.py): SL 2.0x/TP 3.0x ATR subía el win rate
y bajaba el drawdown en XAUUSD y BTC frente al ratio actual (SL 1.5x/TP
2.5x). Lo valida sobre la config EXACTA ya desplegada de cada activo
(HTF, volumen, circuit breaker, sin solape) para decidir si compensa.

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

PAIRS = {
    "BTC": "XBTUSD",
    "XAUUSD (proxy PAXG)": "PAXGUSD",
}

ASSET_CONFIG = {
    "BTC": {
        "entry_minutes": "60", "htf_minutes": None, "max_bars_forward": 200,
        "gen_kwargs": {"require_volume_confirmation": False},
    },
    "XAUUSD (proxy PAXG)": {
        "entry_minutes": "60", "htf_minutes": "240", "max_bars_forward": 200,
        "gen_kwargs": {"require_volume_confirmation": False},
    },
}


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


def realistic_stats(raw, htf_df, max_bars_forward, gen_kwargs) -> dict:
    df = core.generate_signals(raw.copy(), htf_df=htf_df, **gen_kwargs)
    trades = simulate_trades(df, max_bars_forward=max_bars_forward)
    trades = filter_non_overlapping(trades)
    trades = apply_circuit_breaker(trades)
    return summarize(trades)


def run() -> None:
    for name, pair in PAIRS.items():
        cfg = ASSET_CONFIG[name]
        print(f"\n{'=' * 60}", flush=True)
        print(f"  {name} ({pair})", flush=True)
        print(f"{'=' * 60}", flush=True)

        raw = fetch_full_history(pair, cfg["entry_minutes"])
        if raw.empty:
            print("  Sin datos.", flush=True)
            continue
        htf_df = fetch_full_history(pair, cfg["htf_minutes"]) if cfg["htf_minutes"] else None

        orig_sl, orig_tp = core.SL_ATR_MULT, core.TP_ATR_MULT
        try:
            stats = realistic_stats(raw, htf_df, cfg["max_bars_forward"], cfg["gen_kwargs"])
            print(f"  [ACTUAL, SL 1.5x/TP 2.5x] {stats}", flush=True)

            core.SL_ATR_MULT, core.TP_ATR_MULT = 2.0, 3.0
            stats = realistic_stats(raw, htf_df, cfg["max_bars_forward"], cfg["gen_kwargs"])
            print(f"  [CANDIDATO, SL 2.0x/TP 3.0x] {stats}", flush=True)
        finally:
            core.SL_ATR_MULT, core.TP_ATR_MULT = orig_sl, orig_tp


if __name__ == "__main__":
    run()
