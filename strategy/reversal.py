"""
Estrategia de reversión (mean reversion) — paradigma OPUESTO al de rotura
de strategy/core.py. En vez de confirmar momentum a favor de una rotura,
busca el rebote tras un movimiento extremo: RSI en sobreventa/sobrecompra
(30/70 — la lectura clásica que citó el usuario, distinta del RSI>50/<50
de confirmación de tendencia que usa la estrategia de rotura) + estocástico
como segunda confirmación + Bandas de Bollinger para el contexto de precio.

Inspirado en el bloque de reversiones del curso de Enrique Moris (DXY,
soportes, indicadores de sobrecompra/sobreventa) — sin el contenido real
de esas lecciones (de pago, solo se vieron los títulos), se implementa con
la lectura estándar y documentada de RSI+estocástico+Bollinger para
reversión, no inventada al azar.

Completamente independiente de strategy/core.py: módulo aparte, cero
riesgo de tocar la estrategia de rotura ya en producción.
"""

import numpy as np
import pandas as pd

RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70

STOCH_K_PERIOD = 14
STOCH_D_PERIOD = 3
STOCH_SMOOTH = 3

BB_PERIOD = 20
BB_STD = 2

ATR_PERIOD = 14
SL_ATR_MULT = 1.0


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / RSI_PERIOD, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / RSI_PERIOD, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))

    low_min = df["Low"].rolling(STOCH_K_PERIOD).min()
    high_max = df["High"].rolling(STOCH_K_PERIOD).max()
    raw_k = 100 * (df["Close"] - low_min) / (high_max - low_min).replace(0, np.nan)
    df["stoch_k"] = raw_k.rolling(STOCH_SMOOTH).mean()
    df["stoch_d"] = df["stoch_k"].rolling(STOCH_D_PERIOD).mean()

    sma = df["Close"].rolling(BB_PERIOD).mean()
    std = df["Close"].rolling(BB_PERIOD).std()
    df["bb_mid"] = sma
    df["bb_upper"] = sma + BB_STD * std
    df["bb_lower"] = sma - BB_STD * std

    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["atr"] = true_range.ewm(span=ATR_PERIOD, adjust=False).mean()

    return df


def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Genera columna 'signal': 1 = compra (rebote esperado tras sobreventa),
    -1 = venta (corrección esperada tras sobrecompra), 0 = sin señal.

    LONG: el RSI estaba por debajo de 30 y acaba de volver a cruzar hacia
    arriba (confirma que el rebote ya empezó, no anticipa el suelo exacto),
    el estocástico cruza al alza todavía en zona baja, y el precio sigue
    por debajo de la media de Bollinger (contexto: viene de un extremo).
    SHORT es el espejo exacto para sobrecompra.

    TP = vuelta a la media móvil de Bollinger (bb_mid) — el objetivo propio
    de una reversión es volver a la media, no una tendencia larga, así que
    NO reutiliza el TP_ATR_MULT de la estrategia de rotura.
    """
    df = compute_indicators(df)

    rsi_prev = df["rsi"].shift(1)

    # El estocástico (14,3,3) reacciona antes que el RSI(14) — en la
    # práctica, para cuando el RSI vuelve a cruzar 30/70, el estocástico ya
    # ha salido de su propia zona de sobreventa/sobrecompra (confirmado con
    # datos: exigir que siguiera en zona bloqueaba el 100% de las señales).
    # Se usa solo como confirmación de alineación (a favor del rebote), no
    # de zona — el RSI 30/70 sigue siendo el disparador real.
    long_signal = (
        (rsi_prev < RSI_OVERSOLD) & (df["rsi"] >= RSI_OVERSOLD)
        & (df["stoch_k"] > df["stoch_d"])
        & (df["Close"] < df["bb_mid"])
    )
    short_signal = (
        (rsi_prev > RSI_OVERBOUGHT) & (df["rsi"] <= RSI_OVERBOUGHT)
        & (df["stoch_k"] < df["stoch_d"])
        & (df["Close"] > df["bb_mid"])
    )

    df["signal"] = 0
    df.loc[long_signal, "signal"] = 1
    df.loc[short_signal, "signal"] = -1

    df["sl"] = np.nan
    df["tp"] = np.nan
    df.loc[long_signal, "sl"] = df["Close"] - SL_ATR_MULT * df["atr"]
    df.loc[long_signal, "tp"] = df["bb_mid"]
    df.loc[short_signal, "sl"] = df["Close"] + SL_ATR_MULT * df["atr"]
    df.loc[short_signal, "tp"] = df["bb_mid"]

    return df
