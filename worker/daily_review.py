"""
Revisión narrada diaria: explica en texto, con los datos reales de cada
trade resuelto ese día, qué pasó y por qué — nunca propone una operación
nueva. Las señales siguen saliendo únicamente de strategy/core.py con
reglas fijas; esto es solo lectura/explicación de lo ya ocurrido.

Sin ANTHROPIC_API_KEY configurada, se omite sin más (igual patrón que
Telegram: el resto del sistema sigue funcionando).
"""

import logging

from anthropic import Anthropic

from worker import config

log = logging.getLogger("worker.daily_review")

MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = """Eres un analista objetivo que revisa trades YA CERRADOS de un sistema \
de señales de trading. Tu única tarea es explicar, con los datos que se te dan, qué pasó \
y por qué pudo pasar (contexto técnico: RSI al entrar, cuánto se movió el precio a favor \
y en contra antes de resolverse).

Reglas estrictas:
- NUNCA propongas una operación nueva, ni un nivel de entrada/SL/TP para el futuro. Eso lo \
decide únicamente el motor de reglas del sistema, no tú.
- NUNCA inventes datos que no se te hayan dado (precios, indicadores, noticias, eventos de \
mercado). Si no tienes un dato, no lo menciones.
- Sé conciso: 120-200 palabras, en español de España, tono directo y profesional.
- Si ves un patrón real en los números (ej. varias pérdidas con RSI alto), dilo explícitamente \
con las cifras exactas — no generalices sin base.
"""


def is_configured() -> bool:
    return bool(config.ANTHROPIC_API_KEY)


def _format_trade(t: dict, asset_symbol: str) -> str:
    result = "GANÓ (TP)" if t["status"] == "HIT_TP" else "PERDIÓ (SL)"
    rsi = f"{t['rsi_at_signal']:.1f}" if t.get("rsi_at_signal") is not None else "N/D"
    mae = f"{t['mae_r']:.2f}R" if t.get("mae_r") is not None else "N/D"
    mfe = f"{t['mfe_r']:.2f}R" if t.get("mfe_r") is not None else "N/D"
    r = f"{t['r_multiple']:.2f}R" if t.get("r_multiple") is not None else "N/D"
    return (
        f"- {asset_symbol} {t['direction']}: {result}, resultado {r}. "
        f"RSI al entrar: {rsi}. Excursión en contra (MAE): {mae}. Excursión a favor (MFE): {mfe}."
    )


def generate_daily_review(trades: list[dict], asset_symbols: dict[str, str]) -> str | None:
    """trades: filas de `signals` ya resueltas hoy. asset_symbols: asset_id -> symbol."""
    if not is_configured() or not trades:
        return None

    lines = [_format_trade(t, asset_symbols.get(t["asset_id"], "?")) for t in trades]
    user_prompt = "Trades resueltos hoy:\n" + "\n".join(lines)

    try:
        client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=MODEL,
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        log.error("Error generando la revisión diaria con Claude: %s", e)
        return None
