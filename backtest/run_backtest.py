import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yfinance as yf
from strategy.core import generate_signals
from backtest.engine import simulate_trades, summarize

# Tickers de yfinance para cada activo
ASSETS = {
    "XAUUSD": "GC=F",     # Futuro del oro (proxy de XAUUSD)
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
}

PERIOD = "2y"
INTERVAL = "1h"   # velas de 1 hora


def run_for_asset(name: str, ticker: str, risk_pct: float = 1.0):
    print(f"\n{'='*50}")
    print(f"  {name} ({ticker})")
    print(f"{'='*50}")

    df = yf.download(ticker, period=PERIOD, interval=INTERVAL, progress=False, auto_adjust=True)
    if df.empty:
        print("  ⚠️  Sin datos disponibles para este ticker/intervalo.")
        return None

    # yfinance a veces devuelve columnas multi-index; normalizamos
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = generate_signals(df)
    trades = simulate_trades(df)
    stats = summarize(trades, risk_pct=risk_pct)

    print(f"  Velas analizadas: {len(df)}")
    print(f"  Periodo real de datos: {df.index[0]} → {df.index[-1]}")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    return {"name": name, "trades": trades, "stats": stats}


if __name__ == "__main__":
    import pandas as pd
    results = {}
    for name, ticker in ASSETS.items():
        try:
            res = run_for_asset(name, ticker)
            if res:
                results[name] = res
        except Exception as e:
            print(f"  ❌ Error con {name}: {e}")

    print(f"\n{'='*50}")
    print("  RESUMEN COMPARATIVO")
    print(f"{'='*50}")
    for name, res in results.items():
        s = res["stats"]
        if s.get("num_trades", 0) > 0:
            print(f"  {name}: {s['num_trades']} ops | winrate {s['win_rate_pct']}% | "
                  f"retorno estimado {s['estimated_return_pct']}% | max DD {s['max_drawdown_pct']}%")
