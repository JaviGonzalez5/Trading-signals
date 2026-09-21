"""
Valida con datos reales (mismos 6 meses del backtest ya conocido) si el
filtro de tendencia en 4h y el circuit breaker por racha de pérdidas
(ver strategy/core.py::generate_signals htf_df, strategy/risk.py,
worker/risk_guard.py) mejoran de verdad antes de confiar en ellos en
producción — mismo criterio que el resto de scripts/ de un solo uso:
no se despliega nada sin verlo funcionar sobre datos reales primero.

Compara 4 variantes para BTC/ETH/XAUUSD-proxy: baseline (sin cambios),
solo filtro HTF, solo circuit breaker, y ambos combinados.

Script de un solo uso — no forma parte del sistema en marcha.
"""

import io
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import requests

from backtest.engine import simulate_trades, summarize
from strategy.core import generate_signals
from strategy.risk import COOLDOWN_HOURS, LOSS_STREAK_THRESHOLD

QUARTERS = [
    "2024Q4", "2025Q1", "2025Q2", "2025Q3", "2025Q4", "2026Q1", "2026Q2", "2026Q3",
]
BASE_URL = "https://assets.kraken.com/marketing/institutions/Kraken_OHLCVT_{q}.zip"

PAIRS = {
    "BTC": "XBTUSD",
    "ETH": "ETHUSD",
    "XAUUSD (proxy PAXG)": "PAXGUSD",
}

# Config final que va a producción (worker/main.py::HTF_FILTER_ASSETS) — el
# circuit breaker se aplica siempre, el filtro HTF solo donde el backtest
# demostró que ayuda (en BTC lo empeora, ver commit db8cafa).
FINAL_CONFIG_USES_HTF = {"BTC": False, "ETH": True, "XAUUSD (proxy PAXG)": True}


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


def apply_circuit_breaker(trades: pd.DataFrame) -> pd.DataFrame:
    """Simula el circuit breaker sobre una lista de operaciones YA generada:
    tras LOSS_STREAK_THRESHOLD pérdidas seguidas, se descartan las
    operaciones siguientes hasta que pasen COOLDOWN_HOURS desde el cierre de
    la última pérdida de la racha — igual que haría worker/risk_guard.py en
    vivo, pero reconstruido a partir del propio historial de trades en vez
    de leer Supabase."""
    if trades.empty:
        return trades
    trades = trades.sort_values("entry_date").reset_index(drop=True)
    keep_idx = []
    streak = 0
    paused_until = None
    for i, row in trades.iterrows():
        if paused_until is not None and row["entry_date"] < paused_until:
            continue
        keep_idx.append(i)
        if row["outcome"] == "SL":
            streak += 1
        elif row["outcome"] == "TP":
            streak = 0
        if streak >= LOSS_STREAK_THRESHOLD:
            paused_until = row["exit_date"] + pd.Timedelta(hours=COOLDOWN_HOURS)
            streak = 0
    return trades.loc[keep_idx]


def run_variant(label: str, raw: pd.DataFrame, htf_df: pd.DataFrame | None, use_breaker: bool) -> None:
    df = generate_signals(raw.copy(), htf_df=htf_df)
    trades = simulate_trades(df)
    if use_breaker:
        trades = apply_circuit_breaker(trades)
    stats = summarize(trades)
    print(f"  [{label}] {stats}", flush=True)


def run() -> None:
    for name, pair in PAIRS.items():
        print(f"\n{'=' * 60}", flush=True)
        print(f"  {name} ({pair})", flush=True)
        print(f"{'=' * 60}", flush=True)

        raw_1h = fetch_full_history(pair, "60")
        if raw_1h.empty:
            print("  Sin datos 1h disponibles.", flush=True)
            continue
        raw_4h = fetch_full_history(pair, "240")
        print(
            f"  Velas 1h: {len(raw_1h)} | 4h: {len(raw_4h)} | "
            f"{raw_1h.index[0]} -> {raw_1h.index[-1]}",
            flush=True,
        )

        run_variant("baseline", raw_1h, htf_df=None, use_breaker=False)
        run_variant("+ filtro HTF 4h", raw_1h, htf_df=raw_4h if not raw_4h.empty else None, use_breaker=False)
        run_variant("+ circuit breaker", raw_1h, htf_df=None, use_breaker=True)
        run_variant("+ HTF + circuit breaker", raw_1h, htf_df=raw_4h if not raw_4h.empty else None, use_breaker=True)

        final_htf = raw_4h if (FINAL_CONFIG_USES_HTF.get(name) and not raw_4h.empty) else None
        run_variant("CONFIG FINAL EN PRODUCCIÓN", raw_1h, htf_df=final_htf, use_breaker=True)


if __name__ == "__main__":
    run()
