"""
Valida con datos reales lo que salió de la investigación de "cómo opera un
trader profesional" (Turtle Trading, horario real del oro): salida por
canal Donchian en vez de TP fijo (los 3 activos), y horario real de
mercado del oro (solo XAUUSD). Todas las variantes sobre la config YA
desplegada de cada activo (incluida la mejora de domingo en ETH, que
sigue pendiente de aplicar), bajo las mismas reglas realistas (sin
solape, con circuit breaker).

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

# Config ya desplegada por activo, MÁS la mejora de ETH-domingo ya
# validada (todavía sin aplicar en producción, se incluye aquí como base
# de referencia justa).
ASSET_CONFIG = {
    "BTC": {
        "entry_minutes": "60", "htf_minutes": None, "lookback": 20,
        "max_bars_forward": 200, "gen_kwargs": {"require_volume_confirmation": False},
    },
    "ETH": {
        "entry_minutes": "15", "htf_minutes": "60", "lookback": 20,
        "max_bars_forward": 400,
        "gen_kwargs": {"require_volume_confirmation": True, "exclude_weekdays": {6}},
    },
    "XAUUSD (proxy PAXG)": {
        "entry_minutes": "60", "htf_minutes": "240", "lookback": 20,
        "max_bars_forward": 200, "gen_kwargs": {"require_volume_confirmation": False},
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


def realistic_stats(df: pd.DataFrame, max_bars_forward: int, trailing_exit_lookback=None) -> dict:
    trades = simulate_trades(df, max_bars_forward=max_bars_forward, trailing_exit_lookback=trailing_exit_lookback)
    trades = filter_non_overlapping(trades)
    trades = apply_circuit_breaker(trades)
    return summarize(trades)


def run() -> None:
    for name, pair in PAIRS.items():
        cfg = ASSET_CONFIG[name]
        print(f"\n{'=' * 60}", flush=True)
        print(f"  {name} ({pair})", flush=True)
        print(f"{'=' * 60}", flush=True)

        raw_entry = fetch_full_history(pair, cfg["entry_minutes"])
        if raw_entry.empty:
            print("  Sin datos.", flush=True)
            continue
        htf_df = fetch_full_history(pair, cfg["htf_minutes"]) if cfg["htf_minutes"] else None

        original_lookback = core.STRUCTURE_LOOKBACK
        core.STRUCTURE_LOOKBACK = cfg["lookback"]
        try:
            df_base = core.generate_signals(raw_entry.copy(), htf_df=htf_df, **cfg["gen_kwargs"])
            base_stats = realistic_stats(df_base, cfg["max_bars_forward"])
            print(f"  [ACTUAL, config desplegada + mejoras ya validadas] {base_stats}", flush=True)

            for lookback in (10, 20):
                stats = realistic_stats(df_base, cfg["max_bars_forward"], trailing_exit_lookback=lookback)
                print(f"  [+ salida Turtle (canal {lookback} velas)] {stats}", flush=True)

            if name.startswith("XAUUSD"):
                df_gold_hours = core.generate_signals(
                    raw_entry.copy(), htf_df=htf_df, exclude_gold_market_closed=True, **cfg["gen_kwargs"],
                )
                stats = realistic_stats(df_gold_hours, cfg["max_bars_forward"])
                print(f"  [+ solo horario real del oro] {stats}", flush=True)

                df_gold_hours_trail = df_gold_hours
                for lookback in (10, 20):
                    stats = realistic_stats(df_gold_hours_trail, cfg["max_bars_forward"], trailing_exit_lookback=lookback)
                    print(f"  [+ horario real + salida Turtle {lookback}] {stats}", flush=True)
        finally:
            core.STRUCTURE_LOOKBACK = original_lookback


if __name__ == "__main__":
    run()
