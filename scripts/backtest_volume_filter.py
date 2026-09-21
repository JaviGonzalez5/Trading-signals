"""
Prueba si exigir confirmación por volumen en la rotura (ver strategy/core.py,
parámetro require_volume_confirmation) mejora el win rate — motivado por
que los 3 activos, con la config actual en producción, pierden más
operaciones de las que ganan (aunque el retorno sea positivo porque el TP
es más ancho que el SL). Compara CADA activo con su config ya desplegada
(entrada + filtro HTF que le corresponde) con y sin confirmación por
volumen, ambas bajo las reglas realistas (sin solape de operaciones,
con circuit breaker) — se aplica solo donde mejora de verdad.

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

# Config actual ya desplegada en producción (worker/main.py) por activo:
# timeframe de entrada, timeframe del filtro de tendencia (None = sin
# filtro), y el max_bars_forward equivalente usado en el backtest de
# validación de cada uno.
ASSET_CONFIG = {
    "BTC": {"entry_minutes": "60", "htf_minutes": None, "lookback": 20, "max_bars_forward": 200},
    "ETH": {"entry_minutes": "15", "htf_minutes": "60", "lookback": 20, "max_bars_forward": 400},
    "XAUUSD (proxy PAXG)": {"entry_minutes": "60", "htf_minutes": "240", "lookback": 20, "max_bars_forward": 200},
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


def realistic_stats(df: pd.DataFrame, max_bars_forward: int) -> dict:
    trades = simulate_trades(df, max_bars_forward=max_bars_forward)
    trades = filter_non_overlapping(trades)
    trades = apply_circuit_breaker(trades)
    return summarize(trades)


def run() -> None:
    for name, pair in PAIRS.items():
        cfg = ASSET_CONFIG[name]
        print(f"\n{'=' * 60}", flush=True)
        print(f"  {name} ({pair}) — entrada {cfg['entry_minutes']}m, HTF {cfg['htf_minutes']}m", flush=True)
        print(f"{'=' * 60}", flush=True)

        raw_entry = fetch_full_history(pair, cfg["entry_minutes"])
        if raw_entry.empty:
            print("  Sin datos de entrada disponibles.", flush=True)
            continue
        htf_df = None
        if cfg["htf_minutes"] is not None:
            htf_df = fetch_full_history(pair, cfg["htf_minutes"])
            if htf_df.empty:
                htf_df = None

        original_lookback = core.STRUCTURE_LOOKBACK
        core.STRUCTURE_LOOKBACK = cfg["lookback"]
        try:
            df_no_vol = core.generate_signals(raw_entry.copy(), htf_df=htf_df, require_volume_confirmation=False)
            df_with_vol = core.generate_signals(raw_entry.copy(), htf_df=htf_df, require_volume_confirmation=True)
        finally:
            core.STRUCTURE_LOOKBACK = original_lookback

        stats_no_vol = realistic_stats(df_no_vol, cfg["max_bars_forward"])
        stats_with_vol = realistic_stats(df_with_vol, cfg["max_bars_forward"])

        print(f"  [ACTUAL, sin filtro volumen] {stats_no_vol}", flush=True)
        print(f"  [CANDIDATO, + confirmación por volumen] {stats_with_vol}", flush=True)

        base_return = stats_no_vol.get("estimated_return_pct", 0)
        base_dd = stats_no_vol.get("max_drawdown_pct", 0)
        base_wr = stats_no_vol.get("win_rate_pct", 0)
        cand_return = stats_with_vol.get("estimated_return_pct", 0)
        cand_dd = stats_with_vol.get("max_drawdown_pct", 0)
        cand_wr = stats_with_vol.get("win_rate_pct", 0)

        improves = cand_return > base_return and cand_dd > base_dd
        veredicto = "MEJORA -> aplicar filtro de volumen" if improves else "NO mejora -> mantener sin filtro de volumen"
        print(
            f"  Win rate: {base_wr}% -> {cand_wr}% | Retorno: {base_return}% -> {cand_return}% | "
            f"Drawdown: {base_dd}% -> {cand_dd}%",
            flush=True,
        )
        print(f"  VEREDICTO: {veredicto}", flush=True)


if __name__ == "__main__":
    run()
