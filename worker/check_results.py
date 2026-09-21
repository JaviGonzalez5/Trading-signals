"""
Paso 4: revisión de señales activas. Para cada señal con status=ACTIVE,
mira las velas reales desde que se generó hasta ahora y comprueba si el
precio tocó ya el TP o el SL. Esto NO es aprendizaje automático de ningún
tipo — es un registro objetivo de aciertos/fallos (igual criterio que
backtest/engine.py::simulate_trades, pero sobre datos ya vividos en vez de
un backtest) para que el usuario pueda ajustar la estrategia con datos
reales. Pensado para correr como cron diario (servicio Railway aparte del
worker 24/7), no como bucle.
"""

import logging

from worker import db
from worker.data_sources import fetch_candles_since

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("worker.check_results")


def evaluate_signal(signal: dict, df) -> dict | None:
    """Recorre las velas posteriores a la señal en orden y devuelve el
    resultado (HIT_SL/HIT_TP + precio de salida + fecha) en cuanto se toca
    alguno de los dos, o None si aún sigue sin resolverse.

    De paso mide mae_r/mfe_r (excursión máxima en contra/a favor, en
    múltiplos de riesgo) hasta el momento de resolverse — así una señal que
    ganó pero estuvo a punto de saltar el stop se distingue de una que ganó
    sin sobresaltos, algo que "ganó/perdió" por sí solo no cuenta."""
    direction = signal["direction"]
    sl = float(signal["stop_loss"])
    tp = float(signal["take_profit"])
    entry = float(signal["entry_price"])
    sl_distance = abs(entry - sl) or 1e-9

    def r_of(price: float) -> float:
        if direction == "LONG":
            return (price - entry) / sl_distance
        return (entry - price) / sl_distance

    mfe = 0.0
    mae = 0.0

    for ts, row in df.iterrows():
        if direction == "LONG":
            hit_sl = row["Low"] <= sl
            hit_tp = row["High"] >= tp
            favorable_r = r_of(row["High"])
            adverse_r = r_of(row["Low"])
        else:
            hit_sl = row["High"] >= sl
            hit_tp = row["Low"] <= tp
            favorable_r = r_of(row["Low"])
            adverse_r = r_of(row["High"])

        mfe = max(mfe, favorable_r)
        mae = min(mae, adverse_r)

        # Si toca los dos en la misma vela, asumimos el peor caso (SL) por
        # prudencia — mismo criterio que el backtest.
        if hit_sl:
            return {"status": "HIT_SL", "exit_price": sl, "closed_at": ts, "mfe_r": round(mfe, 3), "mae_r": round(mae, 3)}
        if hit_tp:
            return {"status": "HIT_TP", "exit_price": tp, "closed_at": ts, "mfe_r": round(mfe, 3), "mae_r": round(mae, 3)}

    return None


def r_multiple_for(direction: str, entry: float, sl: float, exit_price: float) -> float:
    if direction == "LONG":
        return (exit_price - entry) / (entry - sl)
    return (entry - exit_price) / (sl - entry)


def run() -> None:
    client = db.get_client()
    active_signals = db.get_active_signals(client)
    log.info("Señales activas a revisar: %d", len(active_signals))

    assets_cache: dict[str, dict | None] = {}
    resolved = 0

    for signal in active_signals:
        asset_id = signal["asset_id"]
        if asset_id not in assets_cache:
            assets_cache[asset_id] = db.get_asset(client, asset_id)
        asset = assets_cache[asset_id]

        if asset is None:
            log.warning("Activo %s no encontrado para señal %s — se omite.", asset_id, signal["id"])
            continue

        try:
            df = fetch_candles_since(asset, signal["signal_ts"])
        except Exception as e:
            log.error("Error descargando histórico de %s para revisar señal %s: %s", asset["symbol"], signal["id"], e)
            continue

        if df.empty:
            continue

        result = evaluate_signal(signal, df)
        if result is None:
            continue

        exit_price = result["exit_price"]
        r_mult = r_multiple_for(
            signal["direction"], float(signal["entry_price"]), float(signal["stop_loss"]), exit_price
        )
        closed_at_iso = result["closed_at"].to_pydatetime().isoformat()

        db.close_signal(
            client,
            signal["id"],
            status=result["status"],
            exit_price=exit_price,
            r_multiple=round(r_mult, 3),
            closed_at_iso=closed_at_iso,
            mae_r=result["mae_r"],
            mfe_r=result["mfe_r"],
        )
        resolved += 1
        log.info(
            "Señal %s (%s) resuelta: %s @ %s (R=%.2f)",
            signal["id"], asset["symbol"], result["status"], exit_price, r_mult,
        )

    log.info("Revisión completa. %d señal(es) resuelta(s) de %d activas.", resolved, len(active_signals))


if __name__ == "__main__":
    run()
