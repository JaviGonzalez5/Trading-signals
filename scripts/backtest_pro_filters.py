"""
Analiza, activo por activo, si añadir filtro de ADX (fuerza de tendencia),
excluir horas/días flojos del diagnóstico (scripts/backtest_diagnose_v2.py)
o restringir dirección (XAUUSD: SHORT rinde la mitad que LONG) mejora la
config YA desplegada de cada uno. Todas las variantes bajo las mismas
reglas realistas (sin solape de operaciones, con circuit breaker).

Se aplica solo donde el backtest demuestre mejora real en retorno Y
drawdown a la vez — mismo criterio que el resto de decisiones de hoy.

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

# Config YA desplegada en producción, por activo.
ASSET_CONFIG = {
    "BTC": {"entry_minutes": "60", "htf_minutes": None, "lookback": 20, "max_bars_forward": 200, "volume": False},
    "ETH": {"entry_minutes": "15", "htf_minutes": "60", "lookback": 20, "max_bars_forward": 400, "volume": True},
    "XAUUSD (proxy PAXG)": {"entry_minutes": "60", "htf_minutes": "240", "lookback": 20, "max_bars_forward": 200, "volume": False},
}

# Variantes candidatas a probar por activo (kwargs extra sobre generate_signals).
CANDIDATES = {
    "BTC": {
        "+ excluir domingo": {"exclude_weekdays": {6}},
        "+ ADX>=20": {"min_adx": 20},
        "+ ADX>=25": {"min_adx": 25},
        "+ domingo + ADX>=20": {"exclude_weekdays": {6}, "min_adx": 20},
    },
    "ETH": {
        "+ excluir domingo": {"exclude_weekdays": {6}},
        "+ excluir 00-02h UTC": {"exclude_hours": {0, 1}},
        "+ domingo + 00-02h UTC": {"exclude_weekdays": {6}, "exclude_hours": {0, 1}},
        "+ ADX>=20": {"min_adx": 20},
        "+ domingo + 00-02h + ADX>=20": {"exclude_weekdays": {6}, "exclude_hours": {0, 1}, "min_adx": 20},
    },
    "XAUUSD (proxy PAXG)": {
        "+ sin SHORT": {"allow_short": False},
        "+ ADX>=20": {"min_adx": 20},
        "+ sin SHORT + ADX>=20": {"allow_short": False, "min_adx": 20},
        "+ excluir sábado": {"exclude_weekdays": {5}},
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


def realistic_stats(df: pd.DataFrame, max_bars_forward: int) -> dict:
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

        raw_entry = fetch_full_history(pair, cfg["entry_minutes"])
        if raw_entry.empty:
            print("  Sin datos.", flush=True)
            continue
        htf_df = fetch_full_history(pair, cfg["htf_minutes"]) if cfg["htf_minutes"] else None

        original_lookback = core.STRUCTURE_LOOKBACK
        core.STRUCTURE_LOOKBACK = cfg["lookback"]
        try:
            df_base = core.generate_signals(raw_entry.copy(), htf_df=htf_df, require_volume_confirmation=cfg["volume"])
            base_stats = realistic_stats(df_base, cfg["max_bars_forward"])
            print(f"  [ACTUAL, config desplegada] {base_stats}", flush=True)

            for label, kwargs in CANDIDATES[name].items():
                df_cand = core.generate_signals(
                    raw_entry.copy(), htf_df=htf_df, require_volume_confirmation=cfg["volume"], **kwargs,
                )
                cand_stats = realistic_stats(df_cand, cfg["max_bars_forward"])
                print(f"  [{label}] {cand_stats}", flush=True)

                base_r = base_stats.get("estimated_return_pct", 0)
                base_dd = base_stats.get("max_drawdown_pct", 0)
                cand_r = cand_stats.get("estimated_return_pct", 0)
                cand_dd = cand_stats.get("max_drawdown_pct", 0)
                improves = cand_r > base_r and cand_dd > base_dd
                print(f"    -> {'MEJORA' if improves else 'no mejora'}", flush=True)
        finally:
            core.STRUCTURE_LOOKBACK = original_lookback


if __name__ == "__main__":
    run()
