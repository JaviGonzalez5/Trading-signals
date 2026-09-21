"""
Decide, activo por activo, si pasar la entrada de 1h a 15m (con 1h como
filtro de tendencia) usando una comparación justa: la config que YA está en
producción (worker/main.py) contra el mejor candidato de 15m encontrado en
scripts/backtest_15m_entry.py — ambas bajo las MISMAS reglas realistas:
- backtest/engine.py::filter_non_overlapping (una operación abierta por
  activo a la vez, igual que ahora exige worker/db.has_active_signal_for_asset
  en vivo) — sin esto, 15m parecía ganar solo porque sumaba operaciones
  solapadas que en la vida real no podrían abrirse a la vez.
- backtest/engine.py::apply_circuit_breaker (mismo circuit breaker que ya
  corre en producción).

Regla de decisión (pedida por el usuario): aplicar el cambio a 15m SOLO en
el activo donde el backtest, con estas reglas, mejora. Si empeora, no se
toca nada de ese activo — se queda en 1h.

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

# Config actual en producción (worker/main.py::HTF_FILTER_ASSETS) para el
# candidato de 1h, y el mejor candidato de 15m encontrado en
# scripts/backtest_15m_entry.py (lookback de estructura en nº de velas de 15m).
PROD_USES_HTF_1H = {"BTC": False, "ETH": True, "XAUUSD (proxy PAXG)": True}
CANDIDATE_15M_LOOKBACK = {"BTC": 80, "ETH": 20, "XAUUSD (proxy PAXG)": 80}


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
    decisions = {}

    for name, pair in PAIRS.items():
        print(f"\n{'=' * 60}", flush=True)
        print(f"  {name} ({pair})", flush=True)
        print(f"{'=' * 60}", flush=True)

        raw_1h = fetch_full_history(pair, "60")
        raw_15m = fetch_full_history(pair, "15")
        if raw_1h.empty or raw_15m.empty:
            print("  Sin datos suficientes.", flush=True)
            continue

        htf_1h_for_1h_entry = raw_1h if PROD_USES_HTF_1H[name] else None
        df_1h = core.generate_signals(raw_1h.copy(), htf_df=htf_1h_for_1h_entry)
        prod_stats = realistic_stats(df_1h, max_bars_forward=200)
        print(f"  [PRODUCCIÓN, 1h, realista] {prod_stats}", flush=True)

        lookback = CANDIDATE_15M_LOOKBACK[name]
        original_lookback = core.STRUCTURE_LOOKBACK
        core.STRUCTURE_LOOKBACK = lookback
        try:
            df_15m = core.generate_signals(raw_15m.copy(), htf_df=raw_1h)
        finally:
            core.STRUCTURE_LOOKBACK = original_lookback
        candidate_stats = realistic_stats(df_15m, max_bars_forward=400)
        print(f"  [CANDIDATO, 15m lookback={lookback} + filtro 1h, realista] {candidate_stats}", flush=True)

        prod_return = prod_stats.get("estimated_return_pct", 0)
        prod_dd = prod_stats.get("max_drawdown_pct", 0)
        cand_return = candidate_stats.get("estimated_return_pct", 0)
        cand_dd = candidate_stats.get("max_drawdown_pct", 0)

        # Mejora solo si gana en LAS DOS métricas (retorno y drawdown) — no
        # vale ganar en una a costa de la otra, dado que el objetivo es una
        # cuenta prop firm con límite de drawdown, no solo maximizar retorno.
        improves = cand_return > prod_return and cand_dd > prod_dd
        decisions[name] = improves
        veredicto = "MEJORA -> aplicar 15m" if improves else "NO mejora -> mantener 1h"
        print(f"  VEREDICTO: {veredicto}", flush=True)

    print(f"\n{'=' * 60}", flush=True)
    print("  RESUMEN DE DECISIONES", flush=True)
    print(f"{'=' * 60}", flush=True)
    for name, improves in decisions.items():
        print(f"  {name}: {'15m' if improves else '1h (sin cambios)'}", flush=True)


if __name__ == "__main__":
    run()
