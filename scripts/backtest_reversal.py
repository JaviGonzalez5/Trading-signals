"""
Valida la estrategia de reversión (strategy/reversal.py, RSI 30/70 +
estocástico + Bollinger) con datos reales, ANTES de tocar nada en el
worker ni en la web — pedido explícito del usuario ("haz test antes de
nada"). Prueba los 3 activos en 1h, bajo las mismas reglas realistas de
siempre (sin solape de operaciones, con circuit breaker), y la compara
contra la estrategia de rotura ya desplegada de cada uno como referencia.

Estrategia completamente aparte de strategy/core.py — este test no toca
nada de lo que ya está en producción.

Script de un solo uso — no forma parte del sistema en marcha.
"""

import io
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import requests

import strategy.reversal as reversal
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

# Referencia: lo que ya sabemos que da la estrategia de rotura desplegada
# (ver sesiones anteriores de este mismo día, backtest_pro_research.py).
BREAKOUT_REFERENCE = {
    "BTC": {"return": 37.35, "drawdown": -9.33, "win_rate": 48.44},
    "ETH": {"return": 37.73, "drawdown": -8.33, "win_rate": 43.75},
    "XAUUSD (proxy PAXG)": {"return": 35.68, "drawdown": -7.67, "win_rate": 49.55},
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


def run() -> None:
    for name, pair in PAIRS.items():
        print(f"\n{'=' * 60}", flush=True)
        print(f"  {name} ({pair}) — reversión (RSI 30/70 + estocástico + Bollinger)", flush=True)
        ref = BREAKOUT_REFERENCE[name]
        print(f"  Referencia (rotura, ya en producción): retorno {ref['return']}% / DD {ref['drawdown']}% / WR {ref['win_rate']}%", flush=True)
        print(f"{'=' * 60}", flush=True)

        raw = fetch_full_history(pair, "60")
        if raw.empty:
            print("  Sin datos.", flush=True)
            continue
        print(f"  Velas: {len(raw)} | {raw.index[0]} -> {raw.index[-1]}", flush=True)

        df = reversal.generate_signals(raw.copy())
        n_signals = (df["signal"] != 0).sum()
        print(f"  Señales generadas: {n_signals}", flush=True)

        trades = simulate_trades(df, max_bars_forward=100)
        trades_no_overlap = filter_non_overlapping(trades)
        trades_final = apply_circuit_breaker(trades_no_overlap)

        print(f"  [Sin filtrar solape] {summarize(trades)}", flush=True)
        print(f"  [Realista: sin solape + circuit breaker] {summarize(trades_final)}", flush=True)


if __name__ == "__main__":
    run()
