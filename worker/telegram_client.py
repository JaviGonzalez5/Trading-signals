"""Notificaciones por Telegram. Sin token/chat_id configurados, no falla —
solo deja de avisar (la señal ya quedó guardada en Supabase igualmente)."""

import logging

import requests

from worker import config

log = logging.getLogger("worker.telegram")


def is_configured() -> bool:
    return bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID)


def send_message(text: str) -> bool:
    if not is_configured():
        log.info("Telegram no configurado (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID) — aviso omitido.")
        return False

    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={"chat_id": config.TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        log.error("Error enviando aviso a Telegram: %s", e)
        return False
