"""
Revisión profunda de la estrategia base, pedida por el usuario: hasta ahora
solo hemos añadido FILTROS por encima (HTF, volumen, ADX, horario, circuit
breaker) sin tocar nunca los parámetros de partida de strategy/core.py —
RSI_LONG_MIN/RSI_SHORT_MAX (umbral de confirmación), STRUCTURE_LOOKBACK
(ventana de rotura) y SL_ATR_MULT/TP_ATR_MULT (el ratio riesgo:beneficio).
Barrido sistemático de cada uno por separado (sensibilidad), sobre la
config YA desplegada de cada activo, con las reglas realistas de siempre.

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
    "ETH": "ETHUSD",
    "XAUUSD (proxy PAXG)": "PAXGUSD",
}

ASSET_CONFIG = {
    "BTC": {
        "entry_minutes": "60", "htf_minutes": None, "max_bars_forward": 200,
        "gen_kwargs": {"require_volume_confirmation": False},
    },
    "ETH": {
        "entry_minutes": "15", "htf_minutes": "60", "max_bars_forward": 400,
        "gen_kwargs": {"require_volume_confirmation": True, "exclude_weekdays": {6}},
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


def realistic_stats(raw: pd.DataFrame, htf_df, max_bars_forward: int, gen_kwargs: dict) -> dict:
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

        orig_rsi_long = core.RSI_LONG_MIN
        orig_rsi_short = core.RSI_SHORT_MAX
        orig_lookback = core.STRUCTURE_LOOKBACK
        orig_sl_mult = core.SL_ATR_MULT
        orig_tp_mult = core.TP_ATR_MULT

        try:
            print("\n  -- Baseline (config actual: RSI 50, lookback 20, SL 1.5x/TP 2.5x ATR) --", flush=True)
            core.STRUCTURE_LOOKBACK = 20
            stats = realistic_stats(raw, htf_df, cfg["max_bars_forward"], cfg["gen_kwargs"])
            print(f"  {stats}", flush=True)

            print("\n  -- Sensibilidad: umbral de RSI (long>X / short<100-X) --", flush=True)
            for rsi_th in (45, 55, 60, 65):
                core.RSI_LONG_MIN = rsi_th
                core.RSI_SHORT_MAX = 100 - rsi_th
                stats = realistic_stats(raw, htf_df, cfg["max_bars_forward"], cfg["gen_kwargs"])
                print(f"  RSI {rsi_th}/{100-rsi_th}: {stats}", flush=True)
            core.RSI_LONG_MIN = orig_rsi_long
            core.RSI_SHORT_MAX = orig_rsi_short

            print("\n  -- Sensibilidad: ventana de rotura (velas de estructura) --", flush=True)
            for lb in (10, 15, 30, 40):
                core.STRUCTURE_LOOKBACK = lb
                stats = realistic_stats(raw, htf_df, cfg["max_bars_forward"], cfg["gen_kwargs"])
                print(f"  lookback={lb}: {stats}", flush=True)
            core.STRUCTURE_LOOKBACK = 20

            print("\n  -- Sensibilidad: ratio SL/TP (múltiplos de ATR) --", flush=True)
            for sl_mult, tp_mult in ((1.0, 2.0), (1.0, 3.0), (2.0, 3.0), (2.0, 4.0), (1.5, 3.5)):
                core.SL_ATR_MULT = sl_mult
                core.TP_ATR_MULT = tp_mult
                stats = realistic_stats(raw, htf_df, cfg["max_bars_forward"], cfg["gen_kwargs"])
                print(f"  SL {sl_mult}x / TP {tp_mult}x: {stats}", flush=True)
            core.SL_ATR_MULT = orig_sl_mult
            core.TP_ATR_MULT = orig_tp_mult
        finally:
            core.RSI_LONG_MIN = orig_rsi_long
            core.RSI_SHORT_MAX = orig_rsi_short
            core.STRUCTURE_LOOKBACK = orig_lookback
            core.SL_ATR_MULT = orig_sl_mult
            core.TP_ATR_MULT = orig_tp_mult


if __name__ == "__main__":
    run()
