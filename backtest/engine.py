"""
Motor de backtest
==================
Simula, vela a vela, qué pasa tras cada señal: si toca antes el SL o el TP.
No usa look-ahead bias (solo usa datos ya conocidos hasta la vela de la señal).
"""

import pandas as pd

from strategy.risk import COOLDOWN_HOURS, LOSS_STREAK_THRESHOLD


def simulate_trades(df: pd.DataFrame, max_bars_forward: int = 200) -> pd.DataFrame:
    """
    Para cada fila con señal, mira hacia adelante en el propio DataFrame
    hasta que el precio toca el SL o el TP. Devuelve un DataFrame de operaciones.
    """
    trades = []
    signal_rows = df[df["signal"] != 0]

    for idx in signal_rows.index:
        pos = df.index.get_loc(idx)
        row = df.iloc[pos]
        direction = row["signal"]
        entry = row["Close"]
        sl = row["sl"]
        tp = row["tp"]

        outcome = None
        exit_price = None
        exit_idx = None
        bars_held = 0

        # Mirar velas futuras (sin look-ahead: usamos High/Low reales de cada vela siguiente)
        for j in range(pos + 1, min(pos + 1 + max_bars_forward, len(df))):
            future = df.iloc[j]
            bars_held += 1

            if direction == 1:  # largo
                hit_sl = future["Low"] <= sl
                hit_tp = future["High"] >= tp
            else:  # corto
                hit_sl = future["High"] >= sl
                hit_tp = future["Low"] <= tp

            # Si toca ambos en la misma vela, asumimos el peor caso (SL) por prudencia
            if hit_sl and hit_tp:
                outcome = "SL"
                exit_price = sl
                exit_idx = df.index[j]
                break
            elif hit_sl:
                outcome = "SL"
                exit_price = sl
                exit_idx = df.index[j]
                break
            elif hit_tp:
                outcome = "TP"
                exit_price = tp
                exit_idx = df.index[j]
                break

        if outcome is None:
            # No tocó ni SL ni TP en la ventana → cerramos al precio final de la ventana (timeout)
            outcome = "TIMEOUT"
            last_pos = min(pos + max_bars_forward, len(df) - 1)
            exit_price = df.iloc[last_pos]["Close"]
            exit_idx = df.index[last_pos]

        r_multiple = (exit_price - entry) / (entry - sl) if direction == 1 else (entry - exit_price) / (sl - entry)

        trades.append({
            "entry_date": idx,
            "exit_date": exit_idx,
            "direction": "LONG" if direction == 1 else "SHORT",
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "exit_price": exit_price,
            "outcome": outcome,
            "bars_held": bars_held,
            "r_multiple": round(r_multiple, 3),
        })

    return pd.DataFrame(trades)


def filter_non_overlapping(trades: pd.DataFrame) -> pd.DataFrame:
    """Descarta operaciones que se solaparían con una ya abierta del mismo
    activo — simulate_trades() genera una operación por cada señal
    independientemente de si la anterior sigue abierta, lo cual no es
    realista: en vivo (y en el capital real de una cuenta prop firm) solo
    hay una posición abierta por activo a la vez (worker/risk_guard.py no
    abre una señal nueva si la anterior de ese activo no se ha resuelto).

    Sin este filtro, sumar r_multiple de operaciones solapadas como si
    fueran secuenciales infla el retorno y subestima el drawdown real
    (varias pérdidas "al mismo tiempo" cuentan como si fueran una detrás de
    otra). Se queda con la primera operación que empieza y descarta
    cualquiera que arranque antes de que esa se haya cerrado."""
    if trades.empty:
        return trades
    trades = trades.sort_values("entry_date").reset_index(drop=True)
    keep_idx = []
    last_exit = None
    for i, row in trades.iterrows():
        if last_exit is not None and row["entry_date"] < last_exit:
            continue
        keep_idx.append(i)
        last_exit = row["exit_date"]
    return trades.loc[keep_idx]


def apply_circuit_breaker(trades: pd.DataFrame) -> pd.DataFrame:
    """Simula el circuit breaker de strategy/risk.py sobre una lista de
    operaciones ya generada: tras LOSS_STREAK_THRESHOLD pérdidas seguidas,
    descarta las operaciones siguientes hasta que pasen COOLDOWN_HOURS desde
    el cierre de la última pérdida de la racha — igual que
    worker/risk_guard.py en vivo, reconstruido a partir del propio
    historial de trades en vez de leer Supabase."""
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


def summarize(trades: pd.DataFrame, risk_pct: float = 1.0) -> dict:
    """Calcula estadísticas agregadas del backtest."""
    if trades.empty:
        return {"num_trades": 0}

    wins = trades[trades["outcome"] == "TP"]
    losses = trades[trades["outcome"] == "SL"]
    timeouts = trades[trades["outcome"] == "TIMEOUT"]

    win_rate = len(wins) / len(trades) * 100
    avg_r = trades["r_multiple"].mean()
    total_r = trades["r_multiple"].sum()

    # Curva de equity en % de capital, asumiendo risk_pct arriesgado por operación
    equity_curve = (trades["r_multiple"] * risk_pct).cumsum()
    running_max = equity_curve.cummax()
    drawdown = equity_curve - running_max
    max_drawdown_pct = drawdown.min()

    return {
        "num_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "timeouts": len(timeouts),
        "win_rate_pct": round(win_rate, 2),
        "avg_r_multiple": round(avg_r, 3),
        "total_r_multiple": round(total_r, 2),
        "estimated_return_pct": round(total_r * risk_pct, 2),
        "max_drawdown_pct": round(max_drawdown_pct, 2),
    }
