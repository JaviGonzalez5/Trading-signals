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


def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Genera columna 'signal': 1 = compra, -1 = venta, 0 = sin señal.
    También añade 'sl' y 'tp' para las filas con señal.
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
