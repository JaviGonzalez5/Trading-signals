"""
Prueba la idea de Enrique Moris: entrar en 15m (SL más ajustado, mejor R:R)
usando 1h como marco de contexto/tendencia, en vez de generar y ejecutar la
señal en 1h como hace el bot ahora. Se compara contra los mismos 6 meses ya
conocidos, con y sin filtro de tendencia HTF, y con dos lookbacks de
estructura distintos (el mismo nº de velas que en 1h da una ventana mucho
más corta en tiempo real).

No cambia nada en worker/ ni en strategy/core.py — monkeypatchea los
parámetros del módulo solo dentro de este proceso, para no tocar la
estrategia en producción mientras se valida. Si los números convencen, el
cambio a producción se hace aparte, a propósito.

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
from backtest.engine import simulate_trades, summarize

QUARTERS = [
    "2024Q4", "2025Q1", "2025Q2", "2025Q3", "2025Q4", "2026Q1", "2026Q2", "2026Q3",
]
BASE_URL = "https://assets.kraken.com/marketing/institutions/Kraken_OHLCVT_{q}.zip"

PAIRS = {
    "BTC": "XBTUSD",
    "ETH": "ETHUSD",
    "XAUUSD (proxy PAXG)": "PAXGUSD",
}

# Referencia: lo que ya sabemos que da la config actual en producción
# (1h de entrada, ver scripts/backtest_improvements.py, commit 12423d8).
PRODUCTION_REFERENCE = {
    "BTC": {"return": 45.37, "drawdown": -28.32},
    "ETH": {"return": -9.32, "drawdown": -24.0},
    "XAUUSD (proxy PAXG)": {"return": 88.04, "drawdown": -12.33},
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


def run_variant(label: str, raw_15m: pd.DataFrame, htf_df: pd.DataFrame | None, lookback: int) -> None:
    original_lookback = core.STRUCTURE_LOOKBACK
    core.STRUCTURE_LOOKBACK = lookback
    try:
        df = core.generate_signals(raw_15m.copy(), htf_df=htf_df)
    finally:
        core.STRUCTURE_LOOKBACK = original_lookback
    trades = simulate_trades(df, max_bars_forward=400)  # ventana más larga: velas de 15m, no 1h
    stats = summarize(trades)
    print(f"  [{label}] {stats}", flush=True)


def run() -> None:
    for name, pair in PAIRS.items():
        print(f"\n{'=' * 60}", flush=True)
        print(f"  {name} ({pair})", flush=True)
        ref = PRODUCTION_REFERENCE[name]
        print(f"  Referencia (1h, producción actual): retorno {ref['return']}% / drawdown {ref['drawdown']}%", flush=True)
        print(f"{'=' * 60}", flush=True)

        raw_15m = fetch_full_history(pair, "15")
        if raw_15m.empty:
            print("  Sin datos 15m disponibles.", flush=True)
            continue
        raw_1h = fetch_full_history(pair, "60")
        print(
            f"  Velas 15m: {len(raw_15m)} | 1h: {len(raw_1h)} | "
            f"{raw_15m.index[0]} -> {raw_15m.index[-1]}",
            flush=True,
        )

        # a) mismo nº de velas (20) que en 1h -> ventana de solo 5h en 15m
        run_variant("15m, lookback=20 (5h), sin filtro 1h", raw_15m, htf_df=None, lookback=20)
        run_variant(
            "15m, lookback=20 (5h), + filtro tendencia 1h",
            raw_15m, htf_df=raw_1h if not raw_1h.empty else None, lookback=20,
        )
        # b) lookback escalado para cubrir la misma ventana real que 1h (20h = 80 velas de 15m)
        run_variant("15m, lookback=80 (20h), sin filtro 1h", raw_15m, htf_df=None, lookback=80)
        run_variant(
            "15m, lookback=80 (20h), + filtro tendencia 1h",
            raw_15m, htf_df=raw_1h if not raw_1h.empty else None, lookback=80,
        )


if __name__ == "__main__":
    run()
