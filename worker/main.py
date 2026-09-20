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
from worker import config, db, telegram_client
from worker.data_sources import fetch_candles

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("worker")

MIN_CANDLES_NEEDED = 210  # EMA200 + margen para que no salga NaN


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

    df = generate_signals(df)
    last = df.iloc[-1]
    if last["signal"] == 0:
        return

    signal_ts = df.index[-1].to_pydatetime()
    signal_ts_iso = signal_ts.isoformat()

    if db.has_signal_for_ts(client, asset["id"], signal_ts_iso):
        return  # esta vela ya se procesó (evita duplicar en cada ciclo)

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
