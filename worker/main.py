"""
Worker 24/7: para cada activo activo en Supabase, descarga velas recientes,
aplica la estrategia y, si hay señal nueva en la última vela cerrada, la
guarda y avisa por Telegram. Corre en bucle infinito (pensado para un
servicio "siempre activo" en Railway, no para un cron corto).
"""

import logging
import time
from datetime import datetime, timezone

from strategy.core import generate_signals, position_size
from worker import config, db, risk_guard, telegram_client
from worker.data_sources import fetch_candles, fetch_htf_candles

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("worker")

MIN_CANDLES_NEEDED = 210  # EMA200 + margen para que no salga NaN

# Activos donde el filtro de tendencia HTF (4h) demostró mejorar el backtest
# real (ver scripts/backtest_improvements.py, 6 meses de datos reales). En
# BTC el filtro EMPEORA el resultado en todo: menos operaciones, peor
# drawdown (-36.66% -> -50.33%) — el cruce EMA50/200 en 4h va por detrás de
# los giros rápidos de BTC y filtra justo las entradas buenas. Se deja BTC
# fuera a propósito, con datos que lo respaldan, no por descuido.
HTF_FILTER_ASSETS = {"ETH", "XAUUSD"}


def format_signal_message(symbol: str, direction: str, entry: float, sl: float, tp: float, size) -> str:
    emoji = "🟢 COMPRA" if direction == "LONG" else "🔴 VENTA"
    lines = [
        f"{emoji} · {symbol}",
        f"Entrada: {entry:.5g}",
        f"Stop loss: {sl:.5g}",
        f"Take profit: {tp:.5g}",
    ]
    if size:
        lines.append(f"Tamaño sugerido: {size}")
    else:
        lines.append("Tamaño: configura DEFAULT_CAPITAL en Railway para calcularlo")
    return "\n".join(lines)


def process_asset(client, asset: dict) -> None:
    symbol = asset["symbol"]
    try:
        df = fetch_candles(asset)
    except Exception as e:
        log.error("Error descargando velas de %s: %s", symbol, e)
        return

    if df.empty or len(df) < MIN_CANDLES_NEEDED:
        log.warning("Datos insuficientes para %s (%d velas)", symbol, len(df))
        return

    htf_df = None
    if symbol in HTF_FILTER_ASSETS:
        try:
            htf_df = fetch_htf_candles(asset)
        except Exception as e:
            # Filtro de mejora, no de seguridad — si falla la descarga del
            # marco superior seguimos operando sin él en vez de dejar de
            # generar señales por un fallo puntual de Kraken.
            log.warning("No se pudo descargar el marco temporal superior de %s: %s — sin filtro HTF este ciclo.", symbol, e)

    df = generate_signals(df, htf_df=htf_df)
    last = df.iloc[-1]
    if last["signal"] == 0:
        return

    signal_ts = df.index[-1].to_pydatetime()
    signal_ts_iso = signal_ts.isoformat()

    if db.has_signal_for_ts(client, asset["id"], signal_ts_iso):
        return  # esta vela ya se procesó (evita duplicar en cada ciclo)

    if db.has_active_signal_for_asset(client, asset["id"]):
        log.info("%s ya tiene una posición abierta — señal de %s omitida (una operación por activo a la vez).", symbol, signal_ts_iso)
        return

    if risk_guard.is_paused(client, asset["id"]):
        log.info(
            "%s en pausa por racha de pérdidas (circuit breaker) — señal de %s omitida.",
            symbol, signal_ts_iso,
        )
        return

    direction = "LONG" if last["signal"] == 1 else "SHORT"
    entry = float(last["Close"])
    sl = float(last["sl"])
    tp = float(last["tp"])

    size = None
    if config.DEFAULT_CAPITAL > 0:
        size = position_size(config.DEFAULT_CAPITAL, config.DEFAULT_RISK_PCT, entry, sl)

    row = {
        "asset_id": asset["id"],
        "direction": direction,
        "entry_price": entry,
        "stop_loss": sl,
        "take_profit": tp,
        "risk_pct": config.DEFAULT_RISK_PCT,
        "capital_snapshot": config.DEFAULT_CAPITAL or None,
        "position_size": size,
        "signal_ts": signal_ts_iso,
        # Contexto de la estrategia en el momento de la señal — para poder
        # analizar después qué patrones fallan (ver worker/check_results.py
        # y la página /trades de la web), no solo si ganó o perdió.
        "rsi_at_signal": float(last["rsi"]) if last["rsi"] == last["rsi"] else None,  # NaN != NaN
        "atr_at_signal": float(last["atr"]) if last["atr"] == last["atr"] else None,
        "ema_fast": float(last["ema_fast"]) if last["ema_fast"] == last["ema_fast"] else None,
        "ema_slow": float(last["ema_slow"]) if last["ema_slow"] == last["ema_slow"] else None,
    }

    try:
        saved = db.insert_signal(client, row)
    except Exception as e:
        # El índice único (asset_id, signal_ts) puede rechazar un duplicado
        # si dos ciclos se solapan; no es un error real, solo dedupe.
        if "duplicate key" in str(e).lower() or "unique" in str(e).lower():
            log.info("Señal de %s en %s ya existía (dedupe por índice único).", symbol, signal_ts_iso)
            return
        log.error("Error guardando señal de %s en Supabase: %s", symbol, e)
        return

    log.info("Señal nueva: %s %s @ %s (SL %s / TP %s)", symbol, direction, entry, sl, tp)

    message = format_signal_message(symbol, direction, entry, sl, tp, size)
    if telegram_client.send_message(message):
        db.mark_notified(client, saved["id"], datetime.now(timezone.utc).isoformat())


def run_once() -> None:
    client = db.get_client()
    assets = db.get_active_assets(client)
    if not assets:
        log.warning("No hay activos activos en la tabla 'assets'.")
        return
    for asset in assets:
        process_asset(client, asset)


def main() -> None:
    log.info(
        "Worker de señales arrancado. Intervalo: %s min. Telegram configurado: %s",
        config.POLL_INTERVAL_MINUTES,
        telegram_client.is_configured(),
    )
    while True:
        try:
            run_once()
        except Exception:
            log.exception("Fallo en el ciclo del worker — se reintenta en el siguiente ciclo.")
        time.sleep(config.POLL_INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    main()
