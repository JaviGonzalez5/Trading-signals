"""
Lectura de sentimiento de mercado vía búsqueda web (API de Claude, tool
server-side web_search). NUNCA propone una operación ni un nivel de
entrada/SL/TP — solo describe el sesgo alcista/bajista/neutral que
encuentra en noticias/análisis recientes, como contexto adicional junto
al análisis técnico. El motor de señales (strategy/core.py) sigue siendo
el único que genera entradas reales; esto es puramente informativo.

Sin ANTHROPIC_API_KEY configurada, se omite sin más (mismo patrón que
worker/daily_review.py).
"""

import logging
import re

from anthropic import Anthropic

from worker import config

log = logging.getLogger("worker.fundamental_analysis")

MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = """Eres un analista de mercado. Tu única tarea es dar una lectura del \
sentimiento actual de un activo financiero, basada en noticias y análisis recientes que \
encuentres por búsqueda web.

Reglas estrictas:
- NUNCA propongas una operación, ni un nivel de entrada, stop loss o take profit. Eso no \
es tu trabajo — lo decide únicamente un motor de reglas técnico aparte.
- Empieza tu respuesta EXACTAMENTE con una de estas tres palabras seguida de dos puntos: \
"ALCISTA:", "BAJISTA:" o "NEUTRAL:" — según el sesgo dominante que encuentres en lo que \
leas. Si la información encontrada es mixta o insuficiente, usa "NEUTRAL:".
- Después, 100-180 palabras en español de España explicando por qué, citando hechos o \
fuentes concretas de lo que hayas encontrado — nunca generalices sin base en lo leído.
- Si la búsqueda no encuentra nada relevante o reciente sobre este activo, dilo \
explícitamente en vez de inventar contenido.
"""

SENTIMENT_RE = re.compile(r"^(ALCISTA|BAJISTA|NEUTRAL):\s*", re.IGNORECASE)


def is_configured() -> bool:
    return bool(config.ANTHROPIC_API_KEY)


def analyze_asset(symbol: str, name: str) -> dict | None:
    if not is_configured():
        return None

    try:
        client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=MODEL,
            max_tokens=800,
            system=SYSTEM_PROMPT,
            tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 5}],
            messages=[{
                "role": "user",
                "content": (
                    f"Activo: {symbol} ({name}). Busca noticias y análisis recientes sobre "
                    f"este activo y dame tu lectura del sentimiento de mercado actual."
                ),
            }],
        )
    except Exception as e:
        log.error("Error generando análisis fundamental de %s: %s", symbol, e)
        return None

    text = "\n".join(b.text for b in resp.content if b.type == "text").strip()
    if not text:
        log.warning("Análisis fundamental de %s vino vacío.", symbol)
        return None

    match = SENTIMENT_RE.match(text)
    sentiment = match.group(1).upper() if match else None
    narrative = text[match.end():].strip() if match else text

    return {"sentiment": sentiment, "narrative": narrative}
