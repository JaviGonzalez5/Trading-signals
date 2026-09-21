"""
Estrategia base — Señales de trading
======================================
Filtro de tendencia: EMA 50 vs EMA 200
Gatillo de entrada: ruptura de máximo/mínimo de N velas + confirmación RSI
SL/TP: basados en ATR(14)

Todas las funciones son puras (reciben DataFrame, devuelven DataFrame/valores),
para poder reutilizarlas igual en backtest y en el motor en vivo (Fase 2).
"""

import pandas as pd
import numpy as np

# ---- Parámetros por defecto de la estrategia (ajustables) ----
EMA_FAST = 50
EMA_SLOW = 200
STRUCTURE_LOOKBACK = 20      # velas para detectar ruptura de máx/mín
RSI_PERIOD = 14
RSI_LONG_MIN = 50            # RSI debe superar esto para confirmar largo
RSI_SHORT_MAX = 50           # RSI debe estar por debajo para confirmar corto
ATR_PERIOD = 14
SL_ATR_MULT = 1.5
TP_ATR_MULT = 2.5

# Filtro de tendencia en marco temporal superior (ver generate_signals,
# parámetro htf_df) — mismo cruce EMA50/200 que el filtro de 1h, pero en 4h.
# Inspirado en el bloque de roturas Forex/materias primas del curso de
# Enrique Moris (usa 15m/1h/4h/1D para confirmar tendencia antes de operar
# la rotura en el marco menor). Validado en scripts/backtest_improvements.py:
# sin este filtro, BTC/ETH generaban roturas en contra de la tendencia mayor
# durante los meses laterales del backtest (feb-abr 2026).
HTF_EMA_FAST = 50
HTF_EMA_SLOW = 200


def compute_htf_trend(htf_df: pd.DataFrame) -> pd.Series:
    """+1 alcista / -1 bajista / 0 sin datos suficientes, indexado por fecha
    de vela del marco superior (p.ej. 4h)."""
    ema_fast = htf_df["Close"].ewm(span=HTF_EMA_FAST, adjust=False).mean()
    ema_slow = htf_df["Close"].ewm(span=HTF_EMA_SLOW, adjust=False).mean()
    trend = pd.Series(0, index=htf_df.index)
    trend[ema_fast > ema_slow] = 1
    trend[ema_fast < ema_slow] = -1
    return trend


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Añade EMA50, EMA200, RSI14, ATR14 al DataFrame de velas (OHLC)."""
    df = df.copy()

    df["ema_fast"] = df["Close"].ewm(span=EMA_FAST, adjust=False).mean()
    df["ema_slow"] = df["Close"].ewm(span=EMA_SLOW, adjust=False).mean()

    # RSI
    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / RSI_PERIOD, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / RSI_PERIOD, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))

    # ATR
    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["atr"] = true_range.ewm(span=ATR_PERIOD, adjust=False).mean()

    # Máximo/mínimo de estructura (excluyendo la vela actual)
    df["structure_high"] = df["High"].shift(1).rolling(STRUCTURE_LOOKBACK).max()
    df["structure_low"] = df["Low"].shift(1).rolling(STRUCTURE_LOOKBACK).min()

    return df


def generate_signals(df: pd.DataFrame, htf_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    Genera columna 'signal': 1 = compra, -1 = venta, 0 = sin señal.
    También añade 'sl' y 'tp' para las filas con señal.

    htf_df (opcional): velas de un marco temporal superior (p.ej. 4h) del
    mismo activo. Si se pasa, una señal solo es válida si la tendencia del
    marco superior (EMA50/200 en htf_df) va en la misma dirección — evita
    operar roturas de 1h en contra de la tendencia mayor. Cada vela de 1h
    usa la última vela HTF ya cerrada en ese momento (merge_asof hacia
    atrás), nunca una vela HTF futura.
    """
    df = compute_indicators(df)

    trend_up = df["ema_fast"] > df["ema_slow"]
    trend_down = df["ema_fast"] < df["ema_slow"]

    breakout_up = df["Close"] > df["structure_high"]
    breakout_down = df["Close"] < df["structure_low"]

    rsi_confirms_long = df["rsi"] > RSI_LONG_MIN
    rsi_confirms_short = df["rsi"] < RSI_SHORT_MAX

    long_signal = trend_up & breakout_up & rsi_confirms_long
    short_signal = trend_down & breakout_down & rsi_confirms_short

    if htf_df is not None and not htf_df.empty:
        htf_trend = compute_htf_trend(htf_df)
        left = df.index.to_frame(name="ts").reset_index(drop=True).sort_values("ts")
        right = htf_trend.rename("htf_trend").reset_index()
        right.columns = ["ts", "htf_trend"]
        right = right.sort_values("ts")
        merged = pd.merge_asof(left, right, on="ts", direction="backward")
        aligned = merged.set_index("ts")["htf_trend"].reindex(df.index)
        long_signal = long_signal & (aligned == 1)
        short_signal = short_signal & (aligned == -1)

    df["signal"] = 0
    df.loc[long_signal, "signal"] = 1
    df.loc[short_signal, "signal"] = -1

    df["sl"] = np.nan
    df["tp"] = np.nan

    df.loc[long_signal, "sl"] = df["Close"] - SL_ATR_MULT * df["atr"]
    df.loc[long_signal, "tp"] = df["Close"] + TP_ATR_MULT * df["atr"]
    df.loc[short_signal, "sl"] = df["Close"] + SL_ATR_MULT * df["atr"]
    df.loc[short_signal, "tp"] = df["Close"] - TP_ATR_MULT * df["atr"]

    return df


def position_size(capital: float, risk_pct: float, entry: float, sl: float, contract_size: float = 1.0):
    """
    Calcula el tamaño de posición para que la pérdida máxima (si toca SL)
    sea exactamente risk_pct% del capital.
    """
    risk_amount = capital * (risk_pct / 100)
    sl_distance = abs(entry - sl)
    if sl_distance == 0:
        return 0
    units = risk_amount / (sl_distance * contract_size)
    return round(units, 4)
