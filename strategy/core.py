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

# Confirmación por volumen (ver generate_signals, parámetro
# require_volume_confirmation) — inspirado en el bloque de "Lectura de
# volumen avanzada para roturas" del curso de Enrique Moris: una rotura de
# estructura sin volumen por encima de lo normal es más sospechosa de ser
# una rotura falsa. Se deja como parámetro opcional (default False, cero
# cambio de comportamiento) hasta validarlo por activo con datos reales.
VOLUME_MA_PERIOD = 20
VOLUME_CONFIRM_MULT = 1.2

# Filtro de tendencia en marco temporal superior (ver generate_signals,
# parámetro htf_df) — mismo cruce EMA50/200 que el filtro de 1h, pero en 4h.
# Inspirado en el bloque de roturas Forex/materias primas del curso de
# Enrique Moris (usa 15m/1h/4h/1D para confirmar tendencia antes de operar
# la rotura en el marco menor). Validado en scripts/backtest_improvements.py:
# sin este filtro, BTC/ETH generaban roturas en contra de la tendencia mayor
# durante los meses laterales del backtest (feb-abr 2026).
HTF_EMA_FAST = 50
HTF_EMA_SLOW = 200

# ADX — fuerza de tendencia (ver generate_signals, parámetro min_adx).
# Un breakout de estructura en un mercado LATERAL (sin tendencia real) es
# el tipo de operación que más falla — el ADX es el indicador estándar
# para distinguir "hay tendencia" de "está en rango". Análisis del
# backtest (scripts/backtest_diagnose_v2.py) encontró rachas de hasta 15
# pérdidas seguidas en BTC concentradas en meses laterales (feb-abr) —
# candidato directo a filtrar con esto. Opcional, default None (sin
# filtro), hasta validarlo por activo con datos reales.
ADX_PERIOD = 14


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

    # Volumen medio para confirmar roturas (ver generate_signals)
    df["volume_ma"] = df["Volume"].rolling(VOLUME_MA_PERIOD).mean()

    # ADX (fuerza de tendencia) — suavizado de Wilder, fórmula estándar
    up_move = df["High"].diff()
    down_move = -df["Low"].diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)
    atr_wilder = true_range.ewm(alpha=1 / ADX_PERIOD, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1 / ADX_PERIOD, adjust=False).mean() / atr_wilder)
    minus_di = 100 * (minus_dm.ewm(alpha=1 / ADX_PERIOD, adjust=False).mean() / atr_wilder)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    df["adx"] = dx.ewm(alpha=1 / ADX_PERIOD, adjust=False).mean()

    return df


def generate_signals(
    df: pd.DataFrame,
    htf_df: pd.DataFrame | None = None,
    require_volume_confirmation: bool = False,
    min_adx: float | None = None,
    exclude_weekdays: set[int] | None = None,
    exclude_hours: set[int] | None = None,
    allow_long: bool = True,
    allow_short: bool = True,
) -> pd.DataFrame:
    """
    Genera columna 'signal': 1 = compra, -1 = venta, 0 = sin señal.
    También añade 'sl' y 'tp' para las filas con señal.

    htf_df (opcional): velas de un marco temporal superior (p.ej. 4h) del
    mismo activo. Si se pasa, una señal solo es válida si la tendencia del
    marco superior (EMA50/200 en htf_df) va en la misma dirección — evita
    operar roturas de 1h en contra de la tendencia mayor. Cada vela de 1h
    usa la última vela HTF ya cerrada en ese momento (merge_asof hacia
    atrás), nunca una vela HTF futura.

    require_volume_confirmation (opcional, default False): exige que el
    volumen de la vela de rotura supere VOLUME_CONFIRM_MULT veces su media
    de VOLUME_MA_PERIOD velas — una rotura sin volumen por encima de lo
    normal es más sospechosa de ser falsa.

    min_adx (opcional): exige ADX >= min_adx en la vela de rotura — filtra
    roturas en mercado lateral/sin tendencia real (valores típicos: 20-25).

    exclude_weekdays (opcional): días de la semana a excluir de la entrada
    (0=lunes ... 6=domingo, como pandas .dayofweek).

    exclude_hours (opcional): horas UTC (0-23) a excluir de la entrada.

    allow_long / allow_short (opcional, default True): permite desactivar
    un lado completo de la estrategia para un activo donde ese lado no
    tiene edge real.
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

    if require_volume_confirmation:
        volume_confirms = df["Volume"] > df["volume_ma"] * VOLUME_CONFIRM_MULT
        long_signal = long_signal & volume_confirms
        short_signal = short_signal & volume_confirms

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

    if min_adx is not None:
        adx_confirms = df["adx"] >= min_adx
        long_signal = long_signal & adx_confirms
        short_signal = short_signal & adx_confirms

    if exclude_weekdays:
        weekday = pd.Series(df.index.dayofweek, index=df.index)
        day_ok = ~weekday.isin(exclude_weekdays)
        long_signal = long_signal & day_ok
        short_signal = short_signal & day_ok

    if exclude_hours:
        hour = pd.Series(df.index.hour, index=df.index)
        hour_ok = ~hour.isin(exclude_hours)
        long_signal = long_signal & hour_ok
        short_signal = short_signal & hour_ok

    if not allow_long:
        long_signal = long_signal & False
    if not allow_short:
        short_signal = short_signal & False

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
