"""
Diagnóstico sobre la config FINAL ya desplegada de cada activo (post todos
los cambios de esta sesión: HTF, circuit breaker, volumen en ETH, sin
solape) — para saber DÓNDE se concentran las pérdidas ahora, no con datos
de antes de los cambios. Desglosa por dirección, RSI de entrada, mes, hora
del día (sesión) y día de la semana.

Motivo de mirar hora/día: cripto opera 24/7 pero el volumen y la
volatilidad no son constantes — la sesión de solape EU/US (13:00-17:00 UTC
aprox.) suele concentrar los movimientos limpios; fuera de sesión (noche
asiática/madrugada UTC) hay más ruido y rangos falsos. El oro además tiene
huecos de baja liquidez los findes/festivos USA que pueden generar roturas
falsas nada más abrir.

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

# Config final ya desplegada en producción (worker/main.py) por activo.
ASSET_CONFIG = {
    "BTC": {"entry_minutes": "60", "htf_minutes": None, "lookback": 20, "max_bars_forward": 200, "volume": False},
    "ETH": {"entry_minutes": "15", "htf_minutes": "60", "lookback": 20, "max_bars_forward": 400, "volume": True},
    "XAUUSD (proxy PAXG)": {"entry_minutes": "60", "htf_minutes": "240", "lookback": 20, "max_bars_forward": 200, "volume": False},
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


def diagnose(df: pd.DataFrame, trades: pd.DataFrame) -> None:
    if trades.empty:
        print("  Sin operaciones que diagnosticar.", flush=True)
        return

    trades = trades.copy()
    trades["rsi_at_entry"] = trades["entry_date"].map(df["rsi"])
    trades["hour"] = pd.to_datetime(trades["entry_date"]).dt.hour
    trades["weekday"] = pd.to_datetime(trades["entry_date"]).dt.day_name()
    trades = trades.sort_values("entry_date")

    def block(label, groups):
        print(f"\n  -- {label} --", flush=True)
        for key, sub in groups:
            if sub.empty:
                continue
            wins = (sub["outcome"] == "TP").sum()
            print(
                f"  {key}: {len(sub)} ops, {wins}/{len(sub)} ({wins / len(sub) * 100:.1f}%), R total {sub['r_multiple'].sum():+.2f}",
                flush=True,
            )

    block("Por dirección", trades.groupby("direction"))

    bins = [0, 40, 50, 55, 60, 65, 100]
    labels = ["<40", "40-50", "50-55", "55-60", "60-65", ">65"]
    trades["rsi_bucket"] = pd.cut(trades["rsi_at_entry"], bins=bins, labels=labels)
    block("Por RSI al entrar", trades.groupby("rsi_bucket", observed=True))

    block("Por hora de entrada (UTC)", trades.groupby("hour"))

    weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    trades["weekday"] = pd.Categorical(trades["weekday"], categories=weekday_order, ordered=True)
    block("Por día de la semana", trades.groupby("weekday", observed=True))

    print("\n  -- Rachas de pérdidas seguidas --", flush=True)
    max_streak = cur = 0
    for outcome in trades["outcome"]:
        if outcome == "SL":
            cur += 1
            max_streak = max(max_streak, cur)
        else:
            cur = 0
    print(f"  Racha máxima: {max_streak} pérdidas seguidas", flush=True)


def run() -> None:
    for name, pair in PAIRS.items():
        cfg = ASSET_CONFIG[name]
        print(f"\n{'=' * 60}", flush=True)
        print(f"  {name} ({pair}) — config final: entrada {cfg['entry_minutes']}m, HTF {cfg['htf_minutes']}, volumen {cfg['volume']}", flush=True)
        print(f"{'=' * 60}", flush=True)

        raw_entry = fetch_full_history(pair, cfg["entry_minutes"])
        if raw_entry.empty:
            print("  Sin datos disponibles.", flush=True)
            continue
        htf_df = fetch_full_history(pair, cfg["htf_minutes"]) if cfg["htf_minutes"] else None

        original_lookback = core.STRUCTURE_LOOKBACK
        core.STRUCTURE_LOOKBACK = cfg["lookback"]
        try:
            df = core.generate_signals(raw_entry.copy(), htf_df=htf_df, require_volume_confirmation=cfg["volume"])
        finally:
            core.STRUCTURE_LOOKBACK = original_lookback

        trades = simulate_trades(df, max_bars_forward=cfg["max_bars_forward"])
        trades = filter_non_overlapping(trades)
        trades = apply_circuit_breaker(trades)
        stats = summarize(trades)
        print(f"  Resumen: {stats}", flush=True)

        diagnose(df, trades)


if __name__ == "__main__":
    run()
