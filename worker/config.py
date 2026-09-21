"""Configuración del worker, leída de variables de entorno (nunca hardcoded)."""

import os

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

POLL_INTERVAL_MINUTES = int(os.environ.get("POLL_INTERVAL_MINUTES", "15"))

# Sin capital configurado, el worker sigue generando y guardando señales,
# pero no calcula tamaño de posición (nunca se inventa un capital).
DEFAULT_CAPITAL = float(os.environ.get("DEFAULT_CAPITAL", "0") or 0)
DEFAULT_RISK_PCT = float(os.environ.get("DEFAULT_RISK_PCT", "1.0"))

# Sin esto, el cron de revisión sigue resolviendo señales igual — solo se
# omite la narrativa diaria (ver worker/daily_review.py).
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
