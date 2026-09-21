"""
Motor de backtest
==================
Simula, vela a vela, qué pasa tras cada señal: si toca antes el SL o el TP.
No usa look-ahead bias (solo usa datos ya conocidos hasta la vela de la señal).
"""

import pandas as pd

from strategy.risk import COOLDOWN_HOURS, LOSS_STREAK_THRESHOLD


def simulate_trades(
    df: pd.DataFrame,
    max_bars_forward: int = 200,
    trailing_exit_lookback: int | None = None,
    partial_tp_at: float | None = None,
) -> pd.DataFrame:
    """
    Para cada fila con señal, mira hacia adelante en el propio DataFrame
    hasta que el precio toca el SL o el TP. Devuelve un DataFrame de operaciones.

    trailing_exit_lookback (opcional): en vez de un TP fijo (ATR x
    TP_ATR_MULT), usa una salida de canal Donchian estilo Turtle Trading —
    el sistema de breakout+ATR más estudiado y documentado (Richard Dennis,
    años 80): deja correr al ganador y sale cuando el precio rompe el
    mínimo/máximo de las últimas N velas EN CONTRA de la posición, en vez
    de cortar en un múltiplo de ATR fijo. El nivel de salida por canal
    nunca puede ser peor que el SL inicial (se usa el más favorable de los
    dos, ratchet solo a favor) — sigue siendo, como mínimo, tan protector
    como el SL de siempre.

    partial_tp_at (opcional, solo tiene efecto junto a trailing_exit_lookback):
    fracción de la posición (0-1) que se cierra al llegar al TP original —
    el resto sigue con la salida por canal. Con esto, tocar el TP sigue
    contando como "ganada" (sube el win rate real, no solo el retorno) y a
    la vez se conserva parte de la ganancia extra de dejar correr el resto.
    El SL del resto NO se mueve a breakeven (decisión explícita: un solo
    pequeño retroceso tras el parcial no debe cerrar solo por eso).
    """
    trades = []
    signal_rows = df[df["signal"] != 0]

    trail_low = None
    trail_high = None
    if trailing_exit_lookback is not None:
        trail_low = df["Low"].shift(1).rolling(trailing_exit_lookback).min()
        trail_high = df["High"].shift(1).rolling(trailing_exit_lookback).max()

    for idx in signal_rows.index:
        pos = df.index.get_loc(idx)
        row = df.iloc[pos]
        direction = row["signal"]
        entry = row["Close"]
        sl = row["sl"]
        tp = row["tp"]

        legs: list[tuple[float, float]] = []  # (fracción cerrada, precio de salida)
        remaining = 1.0
        partial_done = False
        outcome = None
        exit_idx = None
        bars_held = 0

        # Mirar velas futuras (sin look-ahead: usamos High/Low reales de cada vela siguiente)
        for j in range(pos + 1, min(pos + 1 + max_bars_forward, len(df))):
            future = df.iloc[j]
            bars_held += 1

            if trailing_exit_lookback is not None:
                if direction == 1:
                    channel_floor = trail_low.iloc[j]
                    exit_level = sl if pd.isna(channel_floor) else max(sl, channel_floor)
                    hit_trail = future["Low"] <= exit_level
                    hit_partial = (not partial_done) and (partial_tp_at is not None) and (future["High"] >= tp)
                else:
                    channel_ceiling = trail_high.iloc[j]
                    exit_level = sl if pd.isna(channel_ceiling) else min(sl, channel_ceiling)
                    hit_trail = future["High"] >= exit_level
                    hit_partial = (not partial_done) and (partial_tp_at is not None) and (future["Low"] <= tp)

                if hit_trail and hit_partial:
                    hit_partial = False  # misma vela: prudencia, no se cobra el parcial

                if hit_partial:
                    legs.append((partial_tp_at, tp))
                    remaining -= partial_tp_at
                    partial_done = True
                    continue

                if hit_trail:
                    legs.append((remaining, exit_level))
                    outcome = "SL" if exit_level == sl else "TRAIL"
                    exit_idx = df.index[j]
                    break
                continue

            if direction == 1:  # largo
                hit_sl = future["Low"] <= sl
                hit_tp = future["High"] >= tp
            else:  # corto
                hit_sl = future["High"] >= sl
                hit_tp = future["Low"] <= tp

            # Si toca ambos en la misma vela, asumimos el peor caso (SL) por prudencia
            if hit_sl and hit_tp:
                legs = [(1.0, sl)]
                outcome = "SL"
                exit_idx = df.index[j]
                break
            elif hit_sl:
                legs = [(1.0, sl)]
                outcome = "SL"
                exit_idx = df.index[j]
                break
            elif hit_tp:
                legs = [(1.0, tp)]
                outcome = "TP"
                exit_idx = df.index[j]
                break

        if outcome is None:
            # No se resolvió en la ventana → cerramos el resto al precio final (timeout)
            outcome = "TIMEOUT"
            last_pos = min(pos + max_bars_forward, len(df) - 1)
            legs.append((remaining, df.iloc[last_pos]["Close"]))
            exit_idx = df.index[last_pos]

        sl_distance = (entry - sl) if direction == 1 else (sl - entry)
        r_multiple = sum(
            frac * ((price - entry) / sl_distance if direction == 1 else (entry - price) / sl_distance)
            for frac, price in legs
        )
        exit_price = legs[-1][1]

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
            "partial_taken": len(legs) > 1,
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

    # Gana/pierde por signo del r_multiple, no por el nombre del outcome —
    # con salida por canal Donchian (TRAIL) el resultado puede ser positivo
    # o negativo según dónde haya quedado el canal, a diferencia de TP/SL
    # que por construcción siempre son favorable/desfavorable.
    non_timeout = trades[trades["outcome"] != "TIMEOUT"]
    wins = non_timeout[non_timeout["r_multiple"] > 0]
    losses = non_timeout[non_timeout["r_multiple"] <= 0]
    timeouts = trades[trades["outcome"] == "TIMEOUT"]

    win_rate = len(wins) / len(trades) * 100
    avg_r = trades["r_multiple"].mean()
    total_r = trades["r_multiple"].sum()

    # Curva de equity en % de capital, asumiendo risk_pct arriesgado por operación
    equity_curve = (trades["r_multiple"] * risk_pct).cumsum()
    running_max = equity_curve.cummax()
    drawdown = equity_curve - running_max
    max_drawdown_pct = drawdown.min()

    result = {
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

    if "partial_taken" in trades.columns and trades["partial_taken"].any():
        # Con cierre parcial en el TP original, una operación que luego
        # pierde en el resto puede seguir siendo neta positiva o negativa —
        # pero el operador SÍ vio un beneficio real cerrado en el camino.
        # win_rate_pct ya cuenta bien el resultado neto; esto es la métrica
        # "se sintió como una ganancia", más relevante para la sensación de
        # operar en vivo que para la rentabilidad.
        felt_win = non_timeout[(non_timeout["r_multiple"] > 0) | non_timeout["partial_taken"]]
        result["felt_win_rate_pct"] = round(len(felt_win) / len(trades) * 100, 2)

    return result
