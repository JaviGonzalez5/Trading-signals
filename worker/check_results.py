"""
Paso 4: revisión de señales activas. Para cada señal con status=ACTIVE,
mira las velas reales desde que se generó hasta ahora y comprueba si el
precio tocó ya el TP o el SL. Esto NO es aprendizaje automático de ningún
tipo — es un registro objetivo de aciertos/fallos (igual criterio que
backtest/engine.py::simulate_trades, pero sobre datos ya vividos en vez de
un backtest) para que el usuario pueda ajustar la estrategia con datos
reales.

Corre en Railway cada 5 minutos (antes cada 24h) — con la cadencia diaria
un trade podía tocar TP/SL y el sistema tardaba hasta un día en enterarse
y en avisar (bug real reportado por el usuario, viendo en la web una señal
"Activa" que el gráfico mostraba claramente resuelta). La revisión narrada
y el análisis fundamental (API de Claude, con coste real) NO deben
dispararse en cada uno de esos ciclos de 5 min — se limitan a una vez al
día mediante los *_exists() de abajo, no mediante el cron.
"""

import logging
from datetime import datetime, timedelta, timezone

from worker import daily_review, db, fundamental_analysis, telegram_client
from worker.data_sources import fetch_candles_since

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("worker.check_results")

# La revisión narrada resume el día completo — se espera a última hora UTC
# para que capture los trades resueltos en cualquier momento del día, no
# solo los del primer ciclo de 5 min que encuentre algo. daily_review_exists()
# evita repetirla en los demás ciclos de esa misma hora.
DAILY_REVIEW_HOUR_UTC = 23


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


def format_resolution_message(symbol: str, direction: str, status: str, exit_price: float, r_multiple: float) -> str:
    emoji = "✅" if status == "HIT_TP" else "❌"
    label = "TAKE PROFIT" if status == "HIT_TP" else "STOP LOSS"
    return (
        f"{emoji} {label} · {symbol}\n"
        f"{direction} cerrada @ {exit_price:.5g}\n"
        f"Resultado: {r_multiple:+.2f}R"
    )


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

        telegram_client.send_message(
            format_resolution_message(asset["symbol"], signal["direction"], result["status"], exit_price, r_mult)
        )

    log.info("Revisión completa. %d señal(es) resuelta(s) de %d activas.", resolved, len(active_signals))

    now = datetime.now(timezone.utc)
    today_iso = now.date().isoformat()

    if daily_review.is_configured() and now.hour == DAILY_REVIEW_HOUR_UTC:
        if not db.daily_review_exists(client, today_iso):
            closed_today = db.get_signals_closed_on(client, today_iso)
            if closed_today:
                asset_ids = {s["asset_id"] for s in closed_today}
                asset_symbols = {}
                for aid in asset_ids:
                    a = assets_cache.get(aid) or db.get_asset(client, aid)
                    if a:
                        asset_symbols[aid] = a["symbol"]
                narrative = daily_review.generate_daily_review(closed_today, asset_symbols)
                if narrative:
                    db.save_daily_review(client, today_iso, [s["id"] for s in closed_today], narrative)
                    log.info("Revisión narrada del %s guardada (%d trades).", today_iso, len(closed_today))

    if fundamental_analysis.is_configured():
        for asset in db.get_active_assets(client):
            if db.fundamental_analysis_exists(client, asset["id"], today_iso):
                continue
            result = fundamental_analysis.analyze_asset(asset["symbol"], asset["name"])
            if result:
                db.save_fundamental_analysis(
                    client, asset["id"], today_iso, result["sentiment"], result["narrative"]
                )
                log.info(
                    "Análisis fundamental de %s guardado (sesgo: %s).",
                    asset["symbol"], result["sentiment"],
                )


if __name__ == "__main__":
    run()
